"""Unit tests for Tube Sharing and tube fees (BR-02, EC-02)."""

from decimal import Decimal
import unittest

from engine.models import LabTier, SampleType, TestMaster, TubeType
from engine.rules import calculate_tubes_and_fee


class TestTubeSharing(unittest.TestCase):
    def setUp(self):
        self.sst_test_factory = lambda code: TestMaster(
            test_code=code,
            test_name=f"SST Test {code}",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.SST,
            fasting_hours=0,
            std_tat_hours=4,
            lab_tier=LabTier.L1,
            price=Decimal("150.00"),
        )
        self.edta_test = TestMaster(
            test_code="TST-EDTA",
            test_name="EDTA Test",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.EDTA,
            fasting_hours=0,
            std_tat_hours=4,
            lab_tier=LabTier.L1,
            price=Decimal("200.00"),
        )

    def test_ec02_fifth_test_same_tube(self):
        """EC-02: 5 SST tests require 2 tubes; 1 EDTA test requires 1 tube -> Total 3 tubes -> Rs 50 fee."""
        tests = [
            self.sst_test_factory("T1"),
            self.sst_test_factory("T2"),
            self.sst_test_factory("T3"),
            self.sst_test_factory("T4"),
            self.sst_test_factory("T5"),
            self.edta_test,
        ]
        tubes, fee = calculate_tubes_and_fee(tests)
        self.assertEqual(tubes, 3)
        self.assertEqual(fee, Decimal("50.00"))

    def test_two_tubes_free(self):
        """Up to 2 tubes are free (no collection fee)."""
        tests = [
            self.sst_test_factory("T1"),
            self.sst_test_factory("T2"),
            self.edta_test,
        ]
        tubes, fee = calculate_tubes_and_fee(tests)
        self.assertEqual(tubes, 2)
        self.assertEqual(fee, Decimal("0.00"))

    def test_four_tests_single_tube(self):
        """4 tests of same sample and tube type share exactly 1 tube."""
        tests = [
            self.sst_test_factory("T1"),
            self.sst_test_factory("T2"),
            self.sst_test_factory("T3"),
            self.sst_test_factory("T4"),
        ]
        tubes, fee = calculate_tubes_and_fee(tests)
        self.assertEqual(tubes, 1)
        self.assertEqual(fee, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
