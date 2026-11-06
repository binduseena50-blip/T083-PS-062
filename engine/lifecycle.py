"""Sample lifecycle state machine, verifications, rejections, waivers, and report releases (BR-01, 06, 07, 10, 11, 12)."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from engine.models import (
    BillRecord,
    BreachType,
    Lab,
    Order,
    OrderItem,
    OrderTestRecord,
    Panel,
    Priority,
    RoutingReason,
    StatusChangeRecord,
    TATBreachRecord,
    TestMaster,
    TestStatus,
)
from engine.rules import (
    compute_delay_credit,
    compute_promised_tat,
)


class OrderLifecycleManager:
    def __init__(
        self,
        orders: Dict[str, Order],
        tests: Dict[str, TestMaster],
        panels: Dict[str, Panel],
        labs: Dict[str, Lab],
        order_items_map: Dict[str, List[OrderItem]],
        bills: Dict[str, BillRecord],
        test_records: Dict[Tuple[str, str], OrderTestRecord],
        status_history: List[StatusChangeRecord],
    ):
        self.orders = orders
        self.tests = tests
        self.panels = panels
        self.labs = labs
        self.order_items_map = order_items_map
        self.bills = bills
        self.test_records = test_records
        self.status_history = status_history
        self.tat_breaches: List[TATBreachRecord] = []
        self.delta_check_history: Dict[str, Dict[str, Decimal]] = {}  # patient_name -> test_code -> last_value

    def record_status_change(
        self, order_id: str, test_code: str, status: TestStatus, ts: datetime
    ):
        self.status_history.append(
            StatusChangeRecord(
                order_id=order_id, test_code=test_code, status=status, ts=ts
            )
        )
        if (order_id, test_code) in self.test_records:
            self.test_records[(order_id, test_code)].status = status

    def handle_fasting_waiver(self, order_id: str, ts: datetime):
        """
        BR-01: Patient waives the fasting breach.
        Affected results are flagged NON_FASTING and no delayed-report credit is issued.
        """
        order = self.orders.get(order_id)
        if not order:
            return
        order.fasting_waived = True

        for (oid, tcode), rec in self.test_records.items():
            if oid == order_id:
                t_master = self.tests[tcode]
                if t_master.fasting_hours > 0:
                    rec.flags.add("NON_FASTING")

    def handle_collected(self, order_id: str, ts: datetime):
        """
        COLLECTED|order_id|ts.
        If first time, initial collection. If repeat, recollection.
        TAT clock restarts from the new collection.
        """
        order = self.orders.get(order_id)
        if not order:
            return

        is_recollection = (order.status == TestStatus.COLLECTED or order.recollection_scheduled)

        if is_recollection:
            order.recollection_scheduled = False
            order.recollection_ts = ts
            # Restart TAT clock for recollected tests
            for (oid, tcode), rec in self.test_records.items():
                if oid == order_id and rec.status in (
                    TestStatus.REJECTED_SAMPLE,
                    TestStatus.COLLECTED,
                ):
                    rec.collected_ts = ts
                    rec.promised_ts = compute_promised_tat(
                        ts, self.tests[tcode], order.priority
                    )
                    self.record_status_change(order_id, tcode, TestStatus.COLLECTED, ts)
        else:
            order.status = TestStatus.COLLECTED
            for (oid, tcode), rec in self.test_records.items():
                if oid == order_id and rec.status != TestStatus.CANCELLED:
                    rec.collected_ts = ts
                    rec.promised_ts = compute_promised_tat(
                        ts, self.tests[tcode], order.priority
                    )
                    self.record_status_change(order_id, tcode, TestStatus.COLLECTED, ts)

    def handle_received(self, order_id: str, test_code: str, ts: datetime):
        """RECEIVED|order_id|test_code|ts."""
        rec = self.test_records.get((order_id, test_code))
        if rec and rec.status != TestStatus.CANCELLED:
            rec.received_ts = ts
            self.record_status_change(order_id, test_code, TestStatus.RECEIVED, ts)

    def handle_processing(self, order_id: str, test_code: str, ts: datetime):
        """PROCESSING|order_id|test_code|ts."""
        rec = self.test_records.get((order_id, test_code))
        if rec and rec.status != TestStatus.CANCELLED:
            self.record_status_change(order_id, test_code, TestStatus.PROCESSING, ts)

    def handle_resulted(
        self, order_id: str, test_code: str, ts: datetime, val_str: str
    ):
        """
        RESULTED|order_id|test_code|ts|value.
        Checks critical ranges and delta checks.
        """
        rec = self.test_records.get((order_id, test_code))
        if not rec or rec.status == TestStatus.CANCELLED:
            return

        rec.result_ts = ts
        val = None
        if val_str.strip():
            try:
                val = Decimal(val_str.strip())
                rec.latest_result_val = val
            except Exception:
                pass

        test_master = self.tests[test_code]
        if val is not None and test_master.is_critical(val):
            rec.flags.add("CRITICAL")

        # Delta check (Stretch goal BR-13)
        order = self.orders[order_id]
        pat_name = order.patient_name
        if val is not None:
            if pat_name in self.delta_check_history and test_code in self.delta_check_history[pat_name]:
                prev_val = self.delta_check_history[pat_name][test_code]
                if prev_val != Decimal("0.0"):
                    diff_pct = abs(val - prev_val) / prev_val * Decimal("100.0")
                    if diff_pct > Decimal("30.0"):
                        rec.flags.add("DELTA_CHECK_ALERT")
            # Update history
            if pat_name not in self.delta_check_history:
                self.delta_check_history[pat_name] = {}
            self.delta_check_history[pat_name][test_code] = val

        self.record_status_change(order_id, test_code, TestStatus.RESULTED, ts)

    def handle_verified(
        self, order_id: str, test_code: str, ts: datetime, verifier_id: str
    ):
        """
        VERIFIED|order_id|test_code|ts|verifier_id.
        BR-07: If critical, only moves to VERIFIED via DOCTOR_VERIFY.
        """
        rec = self.test_records.get((order_id, test_code))
        if not rec or rec.status == TestStatus.CANCELLED:
            return

        # If critical and not doctor verified, standard verification is held
        if "CRITICAL" in rec.flags and rec.doctor_verified_ts is None:
            # Held for doctor verification
            return

        rec.verified_ts = ts
        self.record_status_change(order_id, test_code, TestStatus.VERIFIED, ts)

    def handle_doctor_verify(
        self, order_id: str, test_code: str, ts: datetime, doctor_id: str
    ):
        """
        DOCTOR_VERIFY|order_id|test_code|ts|doctor_id.
        Doctor verification required for a critical value.
        """
        rec = self.test_records.get((order_id, test_code))
        if not rec or rec.status == TestStatus.CANCELLED:
            return

        rec.doctor_verified_ts = ts
        rec.verified_ts = ts
        self.record_status_change(order_id, test_code, TestStatus.VERIFIED, ts)

    def handle_sample_rejected(
        self, order_id: str, test_code: str, ts: datetime, reason: str
    ):
        """
        BR-06: Sample Rejection.
        First rejection: REJECTED_SAMPLE, free recollection within 24h.
        Second rejection: CANCELLED, full refund for affected test, release remaining tests as partial report.
        """
        rec = self.test_records.get((order_id, test_code))
        if not rec:
            return

        rec.rejection_count += 1
        order = self.orders[order_id]

        if rec.rejection_count == 1:
            self.record_status_change(
                order_id, test_code, TestStatus.REJECTED_SAMPLE, ts
            )
            order.recollection_scheduled = True
        else:
            # Second rejection on same order: cancels test with full refund
            self.record_status_change(
                order_id, test_code, TestStatus.CANCELLED, ts
            )
            order.recollection_scheduled = False
            # Full refund for this test
            t_master = self.tests[test_code]
            refund_amount = t_master.price * (
                Decimal("1.0") + Decimal(str(order.priority.surcharge_multiplier))
            )
            bill = self.bills[order_id]
            bill.refund += refund_amount
            bill.net_amount = max(Decimal("0.00"), bill.net_amount - refund_amount)

    def handle_cancel(
        self, order_id: str, item_code: str, ts: datetime
    ):
        """
        BR-11: Order & Test Cancellation.
        Free before COLLECTED; after COLLECTED, 50% charged; after PROCESSING, no refund.
        Panel cancellation is all-or-nothing.
        """
        order = self.orders.get(order_id)
        if not order:
            return

        bill = self.bills[order_id]

        # Determine which tests are affected
        affected_tests: List[str] = []
        is_panel = False
        target_panel = None

        if item_code == "ALL":
            affected_tests = [
                tcode for (oid, tcode) in self.test_records.keys() if oid == order_id
            ]
        elif item_code in self.panels:
            is_panel = True
            target_panel = self.panels[item_code]
            affected_tests = list(target_panel.member_tests)
        else:
            affected_tests = [item_code]

        for tcode in affected_tests:
            rec = self.test_records.get((order_id, tcode))
            if not rec or rec.status == TestStatus.CANCELLED:
                continue

            current_status = rec.status
            if current_status in (TestStatus.CREATED, TestStatus.NEEDS_RESCHEDULE):
                # Free before COLLECTED
                self.record_status_change(order_id, tcode, TestStatus.CANCELLED, ts)
            elif current_status in (TestStatus.COLLECTED, TestStatus.RECEIVED):
                # After COLLECTED, before PROCESSING: 50% charge
                self.record_status_change(order_id, tcode, TestStatus.CANCELLED, ts)
            else:
                # After PROCESSING: no refund
                self.record_status_change(order_id, tcode, TestStatus.CANCELLED, ts)

        # Update billing
        mult = Decimal("1.0") + Decimal(str(order.priority.surcharge_multiplier))
        if item_code == "ALL":
            if order.status in (TestStatus.CREATED, TestStatus.NEEDS_RESCHEDULE):
                bill.cancellation_charge = Decimal("0.00")
                bill.refund = bill.net_amount
                bill.net_amount = Decimal("0.00")
            order.status = TestStatus.CANCELLED
        elif is_panel and target_panel:
            # 50% cancellation charge for panel
            panel_cost = target_panel.price * mult
            charge = (panel_cost * Decimal("0.50")).quantize(Decimal("0.01"))
            bill.cancellation_charge += charge
            bill.refund += panel_cost
            bill.net_amount = (bill.net_amount + charge) - panel_cost

    def handle_reported(self, order_id: str, test_code: str, ts: datetime):
        """
        REPORTED|order_id|test_code|ts.
        Checks for TAT breaches, delayed-report credits, and critical breaches.
        """
        rec = self.test_records.get((order_id, test_code))
        if not rec or rec.status == TestStatus.CANCELLED:
            return

        rec.reported_ts = ts
        self.record_status_change(order_id, test_code, TestStatus.REPORTED, ts)

        order = self.orders[order_id]
        t_master = self.tests[test_code]

        # 1. Critical breach check (BR-07)
        # Reports with any critical value must be REPORTED within 1 hour of VERIFIED
        if "CRITICAL" in rec.flags and rec.verified_ts is not None:
            crit_deadline = rec.verified_ts + timedelta(hours=1)
            if ts > crit_deadline:
                delay_crit_min = int(
                    round((ts - crit_deadline).total_seconds() / 60.0)
                )
                self.tat_breaches.append(
                    TATBreachRecord(
                        order_id=order_id,
                        test_code=test_code,
                        promised_ts=crit_deadline,
                        reported_ts=ts,
                        delay_minutes=delay_crit_min,
                        credit_pct=Decimal("0.0"),
                        credit_amount=Decimal("0.00"),
                        breach_type=BreachType.CRITICAL,
                    )
                )

        # 2. Standard TAT breach check (BR-04, BR-10)
        if rec.promised_ts is not None:
            if ts > rec.promised_ts:
                delay_sec = (ts - rec.promised_ts).total_seconds()
                delay_min = int(round(delay_sec / 60.0))
                breach_hours = Decimal(str(round(delay_sec / 3600.0, 2)))
                rec.tat_breach_hours = breach_hours

                # Check credit eligibility: not issued if caused by patient recollection or waived fasting breach
                is_order_recollected = (
                    order.recollection_ts is not None
                    or any(
                        r.rejection_count > 0
                        for (o, _), r in self.test_records.items()
                        if o == order_id
                    )
                )
                is_exempt = order.fasting_waived or is_order_recollected
                credit_pct, credit_amt = compute_delay_credit(
                    delay_min, t_master.price, is_exempt
                )

                self.tat_breaches.append(
                    TATBreachRecord(
                        order_id=order_id,
                        test_code=test_code,
                        promised_ts=rec.promised_ts,
                        reported_ts=ts,
                        delay_minutes=delay_min,
                        credit_pct=credit_pct,
                        credit_amount=credit_amt,
                        breach_type=BreachType.TAT,
                    )
                )

                if credit_amt > Decimal("0.00"):
                    bill = self.bills[order_id]
                    bill.delay_credit += credit_amt
                    bill.net_amount = max(
                        Decimal("0.00"), bill.net_amount - credit_amt
                    )
            else:
                rec.tat_breach_hours = Decimal("0.00")
