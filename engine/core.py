"""Core engine coordinator orchestrating data loading, command processing, and report generation."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from engine.billing import BillingEngine
from engine.lifecycle import OrderLifecycleManager
from engine.models import (
    BillRecord,
    CapacityRecord,
    CourierRoute,
    Lab,
    Order,
    OrderItem,
    OrderTestRecord,
    Panel,
    Phlebotomist,
    Priority,
    RoutingReason,
    SampleType,
    StatusChangeRecord,
    TATBreachRecord,
    TestMaster,
    TestStatus,
)
from engine.parser import DataLoader, parse_datetime
from engine.reporter import ReportGenerator, format_decimal_2dp, format_dt
from engine.router import LabRouter
from engine.rules import check_fasting_requirement


class DiagnosticLabEngine:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

        # Load domain master files
        self.tests: Dict[str, TestMaster] = DataLoader.load_tests(
            data_dir / "tests.csv"
        )
        self.panels: Dict[str, Panel] = DataLoader.load_panels(
            data_dir / "panels.csv", data_dir / "panel_tests.csv"
        )
        self.labs: Dict[str, Lab] = DataLoader.load_labs(
            data_dir / "labs.csv", data_dir / "lab_capacity.csv"
        )
        self.courier_routes: List[CourierRoute] = DataLoader.load_courier_routes(
            data_dir / "courier_routes.csv"
        )
        self.phlebotomists: Dict[str, Phlebotomist] = DataLoader.load_phlebotomists(
            data_dir / "phlebotomists.csv"
        )
        self.orders: Dict[str, Order] = DataLoader.load_orders(
            data_dir / "orders.csv"
        )
        self.order_items: List[OrderItem] = DataLoader.load_order_items(
            data_dir / "order_items.csv"
        )

        # Index order items by order_id
        self.order_items_map: Dict[str, List[OrderItem]] = defaultdict(list)
        for item in self.order_items:
            self.order_items_map[item.order_id].append(item)

        # Components
        self.router = LabRouter(self.labs, self.courier_routes)
        self.billing = BillingEngine(self.tests, self.panels, self.labs)

        # State storage
        self.bills: Dict[str, BillRecord] = {}
        self.test_records: Dict[Tuple[str, str], OrderTestRecord] = {}
        self.status_history: List[StatusChangeRecord] = []
        self.capacity_report_records: List[CapacityRecord] = []

        # Lifecycle manager
        self.lifecycle = OrderLifecycleManager(
            orders=self.orders,
            tests=self.tests,
            panels=self.panels,
            labs=self.labs,
            order_items_map=self.order_items_map,
            bills=self.bills,
            test_records=self.test_records,
            status_history=self.status_history,
        )

        # Initialize orders
        self._initialize_orders()

    def _initialize_orders(self):
        """Validates orders, computes initial bills, and routes tests."""
        for oid in sorted(self.orders.keys()):
            order = self.orders[oid]
            items = self.order_items_map.get(oid, [])

            bill, unique_tests, dup_removed, is_home_rejected = (
                self.billing.compute_initial_bill(order, items)
            )
            self.bills[oid] = bill

            col_date_str = order.slot_start.strftime("%Y-%m-%d")

            # Check home collection validity (e.g. ORD-0089 > 25km rejected)
            if is_home_rejected:
                order.status = TestStatus.CANCELLED
                order.cancellation_reason = "HOME_COLLECTION_BEYOND_25KM"
                for tcode in unique_tests:
                    rec = OrderTestRecord(
                        order_id=oid,
                        test_code=tcode,
                        routed_lab_id=order.collection_lab_id,
                        routing_reason=RoutingReason.LOCAL,
                        status=TestStatus.CANCELLED,
                    )
                    self.test_records[(oid, tcode)] = rec
                    self.lifecycle.record_status_change(
                        oid, tcode, TestStatus.CANCELLED, order.order_ts
                    )
                continue

            # Check fasting requirements (BR-01)
            tests_in_order = [self.tests[tc] for tc in unique_tests]
            fasting_ok, max_fasting = check_fasting_requirement(order, tests_in_order)
            if not fasting_ok:
                order.status = TestStatus.NEEDS_RESCHEDULE

            # Route each test
            for tcode in unique_tests:
                t_master = self.tests[tcode]
                routed_lab, routing_reason = self.router.route_test(
                    order, t_master, col_date_str
                )

                initial_status = (
                    TestStatus.NEEDS_RESCHEDULE
                    if order.status == TestStatus.NEEDS_RESCHEDULE
                    else TestStatus.CREATED
                )
                rec = OrderTestRecord(
                    order_id=oid,
                    test_code=tcode,
                    routed_lab_id=routed_lab,
                    routing_reason=routing_reason,
                    status=initial_status,
                    base_price=t_master.price,
                )
                self.test_records[(oid, tcode)] = rec

    def process_command_file(self, commands_path: Path):
        """Processes commands.txt line by line in strict sequential order."""
        with open(commands_path, mode="r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue

                parts = raw.split("|")
                cmd = parts[0].strip()

                if cmd == "COLLECTED":
                    oid = parts[1].strip()
                    ts = parse_datetime(parts[2])
                    self.lifecycle.handle_collected(oid, ts)

                elif cmd == "RECEIVED":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    self.lifecycle.handle_received(oid, tcode, ts)

                elif cmd == "PROCESSING":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    self.lifecycle.handle_processing(oid, tcode, ts)

                elif cmd == "RESULTED":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    val = parts[4] if len(parts) > 4 else ""
                    self.lifecycle.handle_resulted(oid, tcode, ts, val)

                elif cmd == "VERIFIED":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    verifier_id = parts[4].strip() if len(parts) > 4 else ""
                    self.lifecycle.handle_verified(oid, tcode, ts, verifier_id)

                elif cmd == "DOCTOR_VERIFY":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    doctor_id = parts[4].strip() if len(parts) > 4 else ""
                    self.lifecycle.handle_doctor_verify(oid, tcode, ts, doctor_id)

                elif cmd == "REPORTED":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    self.lifecycle.handle_reported(oid, tcode, ts)

                elif cmd == "SAMPLE_REJECTED":
                    oid = parts[1].strip()
                    tcode = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    reason = parts[4].strip() if len(parts) > 4 else ""
                    self.lifecycle.handle_sample_rejected(oid, tcode, ts, reason)

                elif cmd == "FASTING_WAIVER":
                    oid = parts[1].strip()
                    ts = parse_datetime(parts[2])
                    self.lifecycle.handle_fasting_waiver(oid, ts)

                elif cmd == "CANCEL":
                    oid = parts[1].strip()
                    item_code = parts[2].strip()
                    ts = parse_datetime(parts[3])
                    self.lifecycle.handle_cancel(oid, item_code, ts)

                elif cmd == "PRINT_CAPACITY":
                    date_str = parts[1].strip()
                    cap_records = self.router.generate_capacity_records(date_str)
                    self.capacity_report_records.extend(cap_records)
                    self.print_capacity(date_str, cap_records)

                elif cmd == "PRINT_TAT_BREACHES":
                    from_date = parts[1].strip()
                    to_date = parts[2].strip()
                    self.print_tat_breaches(from_date, to_date)

                elif cmd == "PRINT_ORDER":
                    oid = parts[1].strip()
                    self.print_order(oid)

    def print_order(self, order_id: str):
        """Prints a comprehensive, human-readable summary of order status, routing, and billing."""
        order = self.orders.get(order_id)
        if not order:
            print(f"Order {order_id} not found.")
            return

        bill = self.bills.get(order_id)
        order_tests = [
            rec for (oid, _), rec in self.test_records.items() if oid == order_id
        ]
        order_tests.sort(key=lambda r: r.test_code)

        print("\n" + "=" * 80)
        print(f" ORDER SUMMARY: {order_id}")
        print("=" * 80)
        print(f"Patient Name:    {order.patient_name:<25} Age/Gender: {order.age}/{order.gender}")
        print(f"Order Placed:    {format_dt(order.order_ts):<25} Priority:   {order.priority.value}")
        print(f"Collection Lab:  {order.collection_lab_id:<25} Home Coll:  {order.home_collection}")
        print(f"Slot Start:      {format_dt(order.slot_start):<25} Status:     {order.status.value}")
        if order.last_meal_ts:
            print(f"Last Meal:       {format_dt(order.last_meal_ts):<25} Waived:     {order.fasting_waived}")

        print("\nTESTS:")
        print(f"  {'Test':<9} {'Name':<24} {'Tier':<6} {'Routed Lab':<18} {'Status':<14} {'Promised TS':<20} {'Reported TS'}")
        print("  " + "-" * 105)
        for rec in order_tests:
            tmaster = self.tests[rec.test_code]
            routed_info = f"{rec.routed_lab_id} ({rec.routing_reason.value})"
            prom_str = format_dt(rec.promised_ts) if rec.promised_ts else "N/A"
            rep_str = format_dt(rec.reported_ts) if rec.reported_ts else "N/A"
            flags_str = f" [{';'.join(sorted(rec.flags))}]" if rec.flags else ""
            status_display = f"{rec.status.value}{flags_str}"
            print(f"  {rec.test_code:<9} {tmaster.test_name[:23]:<24} {tmaster.lab_tier.value:<6} {routed_info:<18} {status_display:<14} {prom_str:<20} {rep_str}")

        if bill:
            print("\nBILLING BREAKDOWN:")
            print(f"  Tests Base Amount:       Rs. {bill.tests_amount:>10.2f}")
            print(f"  Panels Base Amount:      Rs. {bill.panels_amount:>10.2f}")
            print(f"  Duplicate Removed:      -Rs. {bill.duplicate_removed:>10.2f}")
            print(f"  Priority Surcharge:     +Rs. {bill.priority_surcharge:>10.2f}")
            print(f"  Tube Fee:               +Rs. {bill.tube_fee:>10.2f}")
            print(f"  Home Collection Fee:    +Rs. {bill.home_collection_fee:>10.2f}")
            print(f"  Cancellation Charge:    +Rs. {bill.cancellation_charge:>10.2f}")
            print(f"  Delayed-Report Credit:  -Rs. {bill.delay_credit:>10.2f}")
            print(f"  Refunds:                -Rs. {bill.refund:>10.2f}")
            print("  " + "-" * 38)
            print(f"  Net Amount Payable:      Rs. {bill.net_amount:>10.2f}")
        print("=" * 80 + "\n")

    def print_capacity(self, date_str: str, records: List[CapacityRecord]):
        """Prints formatted daily capacity report."""
        print(f"\n--- DAILY LAB CAPACITY REPORT: {date_str} ---")
        print(f"{'Lab ID':<10} {'Sample Type':<14} {'Capacity':<10} {'Used':<10} {'Overflow Routed'}")
        print("-" * 58)
        for r in records:
            print(f"{r.lab_id:<10} {r.sample_type.value:<14} {r.capacity:<10} {r.used:<10} {r.overflow_routed}")
        print("-" * 58 + "\n")

    def print_tat_breaches(self, from_date: str, to_date: str):
        """Prints formatted TAT breach report for the specified date range."""
        breaches = [
            b for b in self.lifecycle.tat_breaches
            if from_date <= b.promised_ts.strftime("%Y-%m-%d") <= to_date
            or from_date <= b.reported_ts.strftime("%Y-%m-%d") <= to_date
        ]
        print(f"\n--- TAT BREACH REPORT: {from_date} to {to_date} ---")
        print(f"{'Order ID':<11} {'Test':<9} {'Promised TS':<20} {'Reported TS':<20} {'Delay (m)':<11} {'Credit %':<9} {'Credit Amt':<12} {'Type'}")
        print("-" * 105)
        for b in sorted(breaches, key=lambda x: (x.order_id, x.test_code)):
            print(f"{b.order_id:<11} {b.test_code:<9} {format_dt(b.promised_ts):<20} {format_dt(b.reported_ts):<20} {b.delay_minutes:<11} {b.credit_pct:<9} Rs. {b.credit_amount:<8.2f} {b.breach_type.value}")
        print("-" * 105)
        print(f"Total Breaches Reported: {len(breaches)}\n")

    def export_all_reports(self, output_dir: Path):
        """Exports all 5 mandatory evaluation CSV files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        ReportGenerator.write_order_tests_csv(
            output_dir / "order_tests.csv", self.test_records
        )
        ReportGenerator.write_status_history_csv(
            output_dir / "status_history.csv", self.status_history
        )
        ReportGenerator.write_bills_csv(output_dir / "bills.csv", self.bills)
        ReportGenerator.write_tat_breaches_csv(
            output_dir / "tat_breaches.csv", self.lifecycle.tat_breaches
        )
        ReportGenerator.write_capacity_report_csv(
            output_dir / "capacity_report.csv", self.capacity_report_records
        )
        print(f"All 5 evaluation reports successfully exported to: {output_dir}")
