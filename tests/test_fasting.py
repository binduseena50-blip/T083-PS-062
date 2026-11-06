
"""Unit tests for Fasting validation & waivers (BR-01, EC-01)."""

from datetime import datetime
from decimal import Decimal
import unittest

from engine.models import (
    LabTier, Order, Priority, SampleType, TestMaster, TubeType,
    OrderTestRecord, BillRecord, RoutingReason
)
from engine.rules import check_fasting_requirement
from engine.lifecycle import OrderLifecycleManager


class TestFasting(unittest.TestCase):

    def setUp(self):
        self.fasting_12h_test = TestMaster(
            test_code="TST-LIPID",
            test_name="Lipid Test",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.SST,
            fasting_hours=12,
            std_tat_hours=6,
            lab_tier=LabTier.L1,
            price=Decimal("500.00"),
        )

        self.non_fasting_test = TestMaster(
            test_code="TST-CBC",
            test_name="CBC",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.EDTA,
            fasting_hours=0,
            std_tat_hours=4,
            lab_tier=LabTier.L1,
            price=Decimal("300.00"),
        )

    def test_ec01_exact_fasting_window(self):
        """EC-01: Collection exactly 12 hours after last meal is valid."""
        order = Order(
            order_id="ORD-TEST-01",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 8, 30),
            last_meal_ts=datetime(2026, 10, 5, 20, 30),
        )

        is_valid, max_fasting = check_fasting_requirement(
            order, [self.fasting_12h_test, self.non_fasting_test]
        )

        self.assertTrue(is_valid)
        self.assertEqual(max_fasting, 12)

    def test_fasting_breach(self):
        """Collection before required fasting hours is invalid."""
        order = Order(
            order_id="ORD-TEST-02",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 7, 0),
            last_meal_ts=datetime(2026, 10, 5, 20, 30),
        )

        is_valid, max_fasting = check_fasting_requirement(
            order, [self.fasting_12h_test]
        )

        self.assertFalse(is_valid)
        self.assertEqual(max_fasting, 12)

    def test_no_fasting_required(self):
        """Tests requiring zero fasting hours need no fasting check."""
        order = Order(
            order_id="ORD-TEST-03",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 8, 0),
            last_meal_ts=None,
        )

        is_valid, max_fasting = check_fasting_requirement(
            order, [self.non_fasting_test]
        )

        self.assertTrue(is_valid)
        self.assertEqual(max_fasting, 0)

    def test_fasting_waiver_marks_non_fasting(self):
        """Waiver flags fasting tests but not non-fasting tests."""

        order = Order(
            order_id="ORD-WAIVER",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 7, 0),
            last_meal_ts=datetime(2026, 10, 5, 20, 30),
        )

        tests = {
            "TST-LIPID": self.fasting_12h_test,
            "TST-CBC": self.non_fasting_test,
        }

        records = {
            ("ORD-WAIVER", "TST-LIPID"): OrderTestRecord(
                "ORD-WAIVER", "TST-LIPID", "LAB-01", RoutingReason.LOCAL
            ),
            ("ORD-WAIVER", "TST-CBC"): OrderTestRecord(
                "ORD-WAIVER", "TST-CBC", "LAB-01", RoutingReason.LOCAL
            ),
        }

        manager = OrderLifecycleManager(
            {"ORD-WAIVER": order},
            tests,
            {},
            {},
            {},
            {"ORD-WAIVER": BillRecord(order_id="ORD-WAIVER")},
            records,
            [],
        )

        manager.handle_fasting_waiver(
            "ORD-WAIVER", datetime(2026, 10, 6, 7, 0)
        )

        self.assertTrue(order.fasting_waived)

        self.assertIn(
            "NON_FASTING",
            records[("ORD-WAIVER", "TST-LIPID")].flags
        )

        self.assertNotIn(
            "NON_FASTING",
            records[("ORD-WAIVER", "TST-CBC")].flags
        )


if __name__ == "__main__":
    unittest.main()
