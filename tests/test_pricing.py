"""Unit tests for Pricing, panel deduplication, and home collection fees (BR-08, BR-09, EC-06, EC-07)."""

from datetime import datetime
from decimal import Decimal
import unittest

from engine.billing import BillingEngine
from engine.models import Lab, LabTier, Order, OrderItem, Panel, Priority, SampleType, TestMaster, TubeType


class TestPricing(unittest.TestCase):
    def setUp(self):
        self.t1 = TestMaster("T1", "Test 1", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("200.00"))
        self.t2 = TestMaster("T2", "Test 2", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("300.00"))
        self.t3 = TestMaster("T3", "Test 3", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("250.00"))
        self.t4 = TestMaster("T4", "Test 4", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("150.00"))
        self.tests = {"T1": self.t1, "T2": self.t2, "T3": self.t3, "T4": self.t4}

        # Panel A: T1, T2 (Bundled 400, individual 500)
        self.pnl_a = Panel("PNL-A", "Panel A", Decimal("400.00"), ["T1", "T2"])
        # Panel B: T2, T3 (Bundled 450, individual 550) - overlaps on T2
        self.pnl_b = Panel("PNL-B", "Panel B", Decimal("450.00"), ["T2", "T3"])
        self.panels = {"PNL-A": self.pnl_a, "PNL-B": self.pnl_b}

        self.lab1 = Lab(
            lab_id="LAB-01",
            lab_name="Lab 1",
            tier=LabTier.L1,
            open_time=datetime.strptime("07:00", "%H:%M").time(),
            close_time=datetime.strptime("21:00", "%H:%M").time(),
            stat_24x7=True,
            latitude=12.9250,
            longitude=77.5830,
        )
        self.labs = {"LAB-01": self.lab1}
        self.billing = BillingEngine(self.tests, self.panels, self.labs)

    def test_ec06_panel_member_and_overlapping_panels(self):
        """
        EC-06: Panel A + member test T2 + overlapping Panel B.
        - Member test T2 is duplicate -> removed, not charged.
        - Overlapping panels A & B: both panels charged, shared tests run once.
        """
        order = Order(
            order_id="ORD-EC06",
            patient_name="P1",
            age=30,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 5, 9, 0),
        )
        items = [
            OrderItem("ORD-EC06", "PANEL", "PNL-A"),
            OrderItem("ORD-EC06", "TEST", "T2"),
            OrderItem("ORD-EC06", "PANEL", "PNL-B"),
        ]
        bill, unique_tests, dup_removed, is_rejected = self.billing.compute_initial_bill(order, items)

        self.assertFalse(is_rejected)
        # Shared test T2 and members of A (T1, T2) and B (T2, T3) -> unique tests [T1, T2, T3]
        self.assertEqual(unique_tests, ["T1", "T2", "T3"])
        self.assertIn("T2", dup_removed)
        self.assertEqual(bill.tests_amount, Decimal("300.00"))
        self.assertEqual(bill.duplicate_removed, Decimal("300.00"))
        self.assertEqual(bill.panels_amount, Decimal("850.00"))  # 400 + 450
        self.assertEqual(bill.net_amount, Decimal("850.00"))

    def test_ec07_home_collection_at_10km_and_order_value_2000(self):
        """
        EC-07: Home address at exactly 10.00 km from lab -> Rs 200 band.
        Order value exactly Rs 2,000.00 -> Fee is waived!
        """
        # Distance between (12.9250, 77.5830) and (12.934404, 77.674766) is 10.00 km
        order = Order(
            order_id="ORD-EC07",
            patient_name="P1",
            age=30,
            gender="M",
            order_ts=datetime(2026, 10, 10, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=True,
            slot_start=datetime(2026, 10, 11, 8, 0),
            address_lat=12.934404,
            address_lon=77.674766,
        )
        # Order items total 2000.00
        t_2000 = TestMaster("T2000", "Test 2000", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("2000.00"))
        self.billing.tests["T2000"] = t_2000
        items = [OrderItem("ORD-EC07", "TEST", "T2000")]

        bill, _, _, is_rejected = self.billing.compute_initial_bill(order, items)
        self.assertFalse(is_rejected)
        self.assertEqual(bill.home_collection_fee, Decimal("0.00"))
        self.assertEqual(bill.net_amount, Decimal("2000.00"))


if __name__ == "__main__":
    unittest.main()
