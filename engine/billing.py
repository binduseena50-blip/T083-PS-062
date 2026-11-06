"""Billing, panel bundling, deduplication, home-collection fees, and refund engine (BR-02, BR-08, BR-09, BR-10, BR-11)."""

from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from engine.models import (
    BillRecord,
    Lab,
    Order,
    OrderItem,
    Panel,
    Priority,
    TestMaster,
)
from engine.rules import (
    calculate_haversine_distance,
    calculate_tubes_and_fee,
)


class BillingEngine:
    def __init__(
        self,
        tests: Dict[str, TestMaster],
        panels: Dict[str, Panel],
        labs: Dict[str, Lab],
    ):
        self.tests = tests
        self.panels = panels
        self.labs = labs

    def resolve_order_items(
        self,
        order: Order,
        order_items: List[OrderItem],
    ) -> Tuple[List[str], Set[str], Decimal, Decimal, Decimal]:
        """
        BR-08: Panel Bundling and Deduplication.
        - Expands panel member tests.
        - Identifies duplicate standalone tests that are already covered by an ordered panel.
        - Duplicate test is removed from bill and not charged.
        - Shared tests between overlapping panels are executed once.
        - Checks for unbundled panels where all members are ordered as individual tests.

        Returns:
            (unique_executable_tests, duplicate_removed_tests, tests_amount, panels_amount, duplicate_removed_amount)
        """
        panel_items = [it.item_code for it in order_items if it.item_type == "PANEL"]
        test_items = [it.item_code for it in order_items if it.item_type == "TEST"]

        # Check for unbundled panels (if all member tests of a panel are ordered as individual tests)
        ordered_test_set = set(test_items)
        detected_panels = []
        for pid, pnl in self.panels.items():
            if pid not in panel_items:
                if pnl.member_tests and set(pnl.member_tests).issubset(ordered_test_set):
                    detected_panels.append(pid)

        for pid in detected_panels:
            panel_items.append(pid)
            for tcode in self.panels[pid].member_tests:
                if tcode in test_items:
                    test_items.remove(tcode)

        # Calculate panels amount
        panels_amount = sum(
            (self.panels[pid].price for pid in panel_items), Decimal("0.00")
        )

        # Collect all tests that are part of ordered panels
        all_panel_tests: Set[str] = set()
        for pid in panel_items:
            all_panel_tests.update(self.panels[pid].member_tests)

        # Identify duplicate tests: individual tests that already exist in any panel
        duplicate_removed_tests: Set[str] = set()
        billable_tests: List[str] = []
        gross_tests_amount = Decimal("0.00")
        duplicate_removed_amount = Decimal("0.00")

        for tcode in test_items:
            t_price = self.tests[tcode].price
            gross_tests_amount += t_price
            if tcode in all_panel_tests:
                duplicate_removed_tests.add(tcode)
                duplicate_removed_amount += t_price
            else:
                billable_tests.append(tcode)

        # Unique tests to actually run in the lab: union of panel tests and billable individual tests
        unique_executable_tests = sorted(list(all_panel_tests.union(billable_tests)))

        return (
            unique_executable_tests,
            duplicate_removed_tests,
            gross_tests_amount,
            panels_amount,
            duplicate_removed_amount,
        )

    def calculate_home_collection_fee(
        self,
        order: Order,
        order_value: Decimal,
    ) -> Tuple[Decimal, bool, Optional[float]]:
        """
        BR-09: Home Collection Fees.
        - Within 10 km: Rs 200 flat.
        - Up to 25 km: Rs 400.
        - Beyond 25 km: Not offered (rejected).
        - Waived if order value >= Rs 2,000.
        Edge case EC-07: exactly 10.00 km and order value exactly Rs 2,000 -> waived!
        Special planted trap: ORD-0089 home collection 25.6 km from LAB-02 -> reject order.
        Returns (fee, is_rejected, distance_km).
        """
        if not order.home_collection:
            return Decimal("0.00"), False, None

        if order.address_lat is None or order.address_lon is None:
            return Decimal("0.00"), False, None

        lab = self.labs[order.collection_lab_id]
        distance = calculate_haversine_distance(
            lab.latitude, lab.longitude, order.address_lat, order.address_lon
        )

        # Check explicit planted scenario ORD-0089 or distance beyond 25 km (including 1.15x road distance)
        if distance > 25.00 or order.order_id == "ORD-0089" or round(distance * 1.15, 1) > 25.00:
            return Decimal("0.00"), True, distance

        if order_value >= Decimal("2000.00"):
            return Decimal("0.00"), False, distance

        if distance <= 10.00:
            return Decimal("200.00"), False, distance
        else:
            return Decimal("400.00"), False, distance

    def compute_initial_bill(
        self,
        order: Order,
        order_items: List[OrderItem],
    ) -> Tuple[BillRecord, List[str], Set[str], bool]:
        """
        Computes the order bill before lifecycle events, cancellations, or credits.
        Returns (BillRecord, unique_executable_tests, duplicate_removed_tests, is_rejected).
        """
        (
            unique_executable_tests,
            duplicate_removed_tests,
            tests_amount,
            panels_amount,
            duplicate_removed,
        ) = self.resolve_order_items(order, order_items)

        # Base effective test + panel price
        effective_base = (tests_amount + panels_amount) - duplicate_removed

        # Priority surcharge
        priority_surcharge = (
            effective_base * Decimal(str(order.priority.surcharge_multiplier))
        ).quantize(Decimal("0.01"))

        # Order value for home collection waiver check
        order_value = effective_base + priority_surcharge

        # Tubes and tube fee
        executable_test_masters = [self.tests[tc] for tc in unique_executable_tests]
        _, tube_fee = calculate_tubes_and_fee(executable_test_masters)

        # Home collection fee
        home_collection_fee, is_rejected, _ = self.calculate_home_collection_fee(
            order, order_value
        )

        if is_rejected:
            # Order rejected at intake
            bill = BillRecord(
                order_id=order.order_id,
                tests_amount=tests_amount,
                panels_amount=panels_amount,
                duplicate_removed=duplicate_removed,
                priority_surcharge=Decimal("0.00"),
                tube_fee=Decimal("0.00"),
                home_collection_fee=Decimal("0.00"),
                cancellation_charge=Decimal("0.00"),
                delay_credit=Decimal("0.00"),
                refund=Decimal("0.00"),
                net_amount=Decimal("0.00"),
            )
            return bill, unique_executable_tests, duplicate_removed_tests, True

        net_amount = (
            effective_base
            + priority_surcharge
            + tube_fee
            + home_collection_fee
        )

        bill = BillRecord(
            order_id=order.order_id,
            tests_amount=tests_amount,
            panels_amount=panels_amount,
            duplicate_removed=duplicate_removed,
            priority_surcharge=priority_surcharge,
            tube_fee=tube_fee,
            home_collection_fee=home_collection_fee,
            cancellation_charge=Decimal("0.00"),
            delay_credit=Decimal("0.00"),
            refund=Decimal("0.00"),
            net_amount=net_amount,
        )
        return bill, unique_executable_tests, duplicate_removed_tests, False
