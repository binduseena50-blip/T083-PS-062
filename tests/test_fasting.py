"""Unit tests for Fasting validation & waivers (BR-01, EC-01)."""

from datetime import datetime
from decimal import Decimal
import unittest

from engine.models import LabTier, Order, Priority, SampleType, TestMaster, TubeType
from engine.rules import check_fasting_requirement


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
        """EC-01: Collection slot exactly N hours after last meal is valid."""
        order = Order(
            order_id="ORD-TEST-01",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 8, 30, 0),
            last_meal_ts=datetime(2026, 10, 5, 20, 30, 0),  # exactly 12 hours
        )
        is_valid, max_fasting = check_fasting_requirement(
            order, [self.fasting_12h_test, self.non_fasting_test]
        )
        self.assertTrue(is_valid)
        self.assertEqual(max_fasting, 12)

    def test_fasting_breach(self):
        """Slot less than N hours after last meal violates requirement."""
        order = Order(
            order_id="ORD-TEST-02",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 7, 0, 0),  # only 10.5 hours
            last_meal_ts=datetime(2026, 10, 5, 20, 30, 0),
        )
        is_valid, max_fasting = check_fasting_requirement(
            order, [self.fasting_12h_test]
        )
        self.assertFalse(is_valid)
        self.assertEqual(max_fasting, 12)

    def test_no_fasting_required(self):
        """Order with 0 fasting hours requires no fasting check."""
        order = Order(
            order_id="ORD-TEST-03",
            patient_name="Test Patient",
            age=45,
            gender="M",
            order_ts=datetime(2026, 10, 5, 8, 0, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-01",
            home_collection=False,
            slot_start=datetime(2026, 10, 6, 8, 0, 0),
            last_meal_ts=None,
        )
        is_valid, max_fasting = check_fasting_requirement(
            order, [self.non_fasting_test]
        )
        self.assertTrue(is_valid)
        self.assertEqual(max_fasting, 0)


if __name__ == "__main__":
    unittest.main()
