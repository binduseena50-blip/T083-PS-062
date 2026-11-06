"""Unit tests for Sample Lifecycle, Rejections, Critical values, and Release (BR-06, BR-07, BR-11, BR-12)."""

from datetime import datetime, timedelta
from decimal import Decimal
import unittest

from engine.lifecycle import OrderLifecycleManager
from engine.models import (
    BillRecord,
    BreachType,
    Lab,
    LabTier,
    Order,
    OrderItem,
    OrderTestRecord,
    Panel,
    Priority,
    RoutingReason,
    SampleType,
    StatusChangeRecord,
    TestMaster,
    TestStatus,
    TubeType,
)


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.t_cbc = TestMaster("TST-CBC", "CBC", SampleType.BLOOD, TubeType.EDTA, 0, 4, LabTier.L1, Decimal("350.00"))
        self.t_k = TestMaster(
            "TST-K", "Potassium", SampleType.BLOOD, TubeType.SST, 0, 4, LabTier.L1, Decimal("180.00"),
            critical_low=Decimal("2.8"), critical_high=Decimal("6.2")
        )
        self.tests = {"TST-CBC": self.t_cbc, "TST-K": self.t_k}
        self.panels = {}
        self.labs = {}

        self.order = Order(
            order_id="ORD-0018",
            patient_name="Prakash",
            age=38,
            gender="M",
            order_ts=datetime(2026, 10, 6, 12, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-02",
            home_collection=False,
            slot_start=datetime(2026, 10, 7, 9, 0),
        )
        self.orders = {"ORD-0018": self.order}
        self.order_items_map = {
            "ORD-0018": [
                OrderItem("ORD-0018", "TEST", "TST-CBC"),
                OrderItem("ORD-0018", "TEST", "TST-K"),
            ]
        }
        self.bills = {
            "ORD-0018": BillRecord(
                order_id="ORD-0018",
                tests_amount=Decimal("530.00"),
                net_amount=Decimal("530.00"),
            )
        }
        self.test_records = {
            ("ORD-0018", "TST-CBC"): OrderTestRecord("ORD-0018", "TST-CBC", "LAB-02", RoutingReason.LOCAL, base_price=Decimal("350.00")),
            ("ORD-0018", "TST-K"): OrderTestRecord("ORD-0018", "TST-K", "LAB-02", RoutingReason.LOCAL, base_price=Decimal("180.00")),
        }
        self.status_history = []
        self.lifecycle = OrderLifecycleManager(
            self.orders, self.tests, self.panels, self.labs,
            self.order_items_map, self.bills, self.test_records, self.status_history
        )

    def test_double_rejection_cancels_and_refunds(self):
        """
        BR-06 & Trap 4: First rejection schedules recollection; second rejection cancels
        the affected test with full refund and remaining tests are released.
        """
        # First collection
        t1 = datetime(2026, 10, 7, 9, 5)
        self.lifecycle.handle_collected("ORD-0018", t1)
        self.assertEqual(self.test_records[("ORD-0018", "TST-K")].status, TestStatus.COLLECTED)

        # First rejection: Haemolysed
        t_rej1 = datetime(2026, 10, 7, 9, 40)
        self.lifecycle.handle_sample_rejected("ORD-0018", "TST-K", t_rej1, "HAEMOLYSED")
        self.assertEqual(self.test_records[("ORD-0018", "TST-K")].status, TestStatus.REJECTED_SAMPLE)
        self.assertTrue(self.order.recollection_scheduled)

        # Second collection (Recollection)
        t2 = datetime(2026, 10, 8, 8, 10)
        self.lifecycle.handle_collected("ORD-0018", t2)
        self.assertEqual(self.test_records[("ORD-0018", "TST-K")].status, TestStatus.COLLECTED)
        self.assertFalse(self.order.recollection_scheduled)

        # Second rejection
        t_rej2 = datetime(2026, 10, 8, 8, 50)
        self.lifecycle.handle_sample_rejected("ORD-0018", "TST-K", t_rej2, "HAEMOLYSED")
        self.assertEqual(self.test_records[("ORD-0018", "TST-K")].status, TestStatus.CANCELLED)

        # Full refund of 180.00 for TST-K
        bill = self.bills["ORD-0018"]
        self.assertEqual(bill.refund, Decimal("180.00"))
        self.assertEqual(bill.net_amount, Decimal("350.00"))

    def test_critical_value_requires_doctor_verification(self):
        """
        BR-07: Value outside critical range sets CRITICAL flag, holds standard verification,
        and requires DOCTOR_VERIFY.
        """
        rec_k = self.test_records[("ORD-0018", "TST-K")]
        rec_k.status = TestStatus.PROCESSING

        # Result is 6.8 (above critical high 6.2)
        t_res = datetime(2026, 10, 7, 10, 0)
        self.lifecycle.handle_resulted("ORD-0018", "TST-K", t_res, "6.8")
        self.assertIn("CRITICAL", rec_k.flags)

        # Standard pathologist verification is held
        t_ver = datetime(2026, 10, 7, 10, 15)
        self.lifecycle.handle_verified("ORD-0018", "TST-K", t_ver, "PATH-01")
        self.assertEqual(rec_k.status, TestStatus.RESULTED)  # Not moved to VERIFIED!

        # Doctor verify succeeds
        t_doc = datetime(2026, 10, 7, 10, 30)
        self.lifecycle.handle_doctor_verify("ORD-0018", "TST-K", t_doc, "DR-01")
        self.assertEqual(rec_k.status, TestStatus.VERIFIED)

        # If reported within 1 hour: no critical breach
        t_rep = datetime(2026, 10, 7, 11, 0)  # 30 min later
        self.lifecycle.handle_reported("ORD-0018", "TST-K", t_rep)
        crit_breaches = [b for b in self.lifecycle.tat_breaches if b.breach_type == BreachType.CRITICAL]
        self.assertEqual(len(crit_breaches), 0)

    def test_cancel_before_collection_full_refund(self):
        self.lifecycle.handle_cancel(
            "ORD-0018", "TST-K", datetime(2026, 10, 7, 8, 0)
        )

        bill = self.bills["ORD-0018"]
        self.assertEqual(bill.refund, Decimal("180.00"))
        self.assertEqual(bill.cancellation_charge, Decimal("0.00"))
        self.assertEqual(bill.net_amount, Decimal("350.00"))

    def test_cancel_after_collection_fifty_percent_refund(self):
        self.test_records[("ORD-0018", "TST-K")].status = TestStatus.COLLECTED

        self.lifecycle.handle_cancel(
            "ORD-0018", "TST-K", datetime(2026, 10, 7, 10, 0)
        )

        bill = self.bills["ORD-0018"]
        self.assertEqual(bill.refund, Decimal("90.00"))
        self.assertEqual(bill.cancellation_charge, Decimal("90.00"))
        self.assertEqual(bill.net_amount, Decimal("440.00"))

    def test_cancel_after_processing_no_refund(self):
        self.test_records[("ORD-0018", "TST-K")].status = TestStatus.PROCESSING

        self.lifecycle.handle_cancel(
            "ORD-0018", "TST-K", datetime(2026, 10, 7, 11, 0)
        )

        bill = self.bills["ORD-0018"]
        self.assertEqual(bill.refund, Decimal("0.00"))
        self.assertEqual(bill.cancellation_charge, Decimal("180.00"))
        self.assertEqual(bill.net_amount, Decimal("530.00"))

if __name__ == "__main__":
    unittest.main()
