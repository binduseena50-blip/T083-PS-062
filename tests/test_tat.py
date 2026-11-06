"""Unit tests for Promised TAT and delayed-report credits (BR-04, BR-10, EC-04, EC-08)."""

from datetime import datetime
from decimal import Decimal
import unittest

from engine.models import LabTier, Priority, SampleType, TestMaster, TubeType
from engine.rules import compute_delay_credit, compute_promised_tat, round_up_to_next_hour


class TestTurnaroundTime(unittest.TestCase):
    def setUp(self):
        self.l1_4h_test = TestMaster(
            test_code="TST-TROP",
            test_name="Troponin I",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.SST,
            fasting_hours=0,
            std_tat_hours=4,
            lab_tier=LabTier.L1,
            price=Decimal("900.00"),
        )
        self.ref_72h_test = TestMaster(
            test_code="TST-TACRO",
            test_name="Tacrolimus",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.EDTA,
            fasting_hours=0,
            std_tat_hours=72,
            lab_tier=LabTier.REFERENCE,
            price=Decimal("2500.00"),
        )
        self.l1_6h_test = TestMaster(
            test_code="TST-CALC",
            test_name="Serum Calcium",
            sample_type=SampleType.BLOOD,
            tube_type=TubeType.SST,
            fasting_hours=0,
            std_tat_hours=6,
            lab_tier=LabTier.L1,
            price=Decimal("200.00"),
        )

    def test_ec04_stat_minimum_tat(self):
        """
        EC-04: STAT with 0.25x of 4h standard TAT gives 1h, raised to 2h minimum.
        Collected 02:14 -> 04:14 rounds up to 05:00.
        """
        collected = datetime(2026, 10, 8, 2, 14, 0)
        promised = compute_promised_tat(collected, self.l1_4h_test, Priority.STAT)
        self.assertEqual(promised, datetime(2026, 10, 8, 5, 0, 0))

    def test_reference_courier_addition(self):
        """REFERENCE tier tests add 24 hours courier transit time."""
        collected = datetime(2026, 10, 7, 10, 0, 0)
        # 72h * 1.0 (ROUTINE) + 24h = 96h (4 days exact)
        promised = compute_promised_tat(collected, self.ref_72h_test, Priority.ROUTINE)
        self.assertEqual(promised, datetime(2026, 10, 11, 10, 0, 0))

    def test_ec08_delay_exactly_2_hours(self):
        """
        EC-08: Delayed by exactly 2 hours (120 minutes) gets 0% credit.
        More than 2 hours gets 10% credit.
        """
        # Exactly 120 minutes: No credit
        pct, amt = compute_delay_credit(
            delay_minutes=120, test_price=Decimal("200.00"), is_exempt_from_credit=False
        )
        self.assertEqual(pct, Decimal("0.0"))
        self.assertEqual(amt, Decimal("0.00"))

        # 121 minutes: 10% credit
        pct, amt = compute_delay_credit(
            delay_minutes=121, test_price=Decimal("200.00"), is_exempt_from_credit=False
        )
        self.assertEqual(pct, Decimal("10.0"))
        self.assertEqual(amt, Decimal("20.00"))

        # > 24 hours (1441 min): 50% credit
        pct, amt = compute_delay_credit(
            delay_minutes=1441, test_price=Decimal("200.00"), is_exempt_from_credit=False
        )
        self.assertEqual(pct, Decimal("50.0"))
        self.assertEqual(amt, Decimal("100.00"))

    def test_delay_credit_exemptions(self):
        """Delay caused by recollection or waived fasting breach is exempt from credit."""
        pct, amt = compute_delay_credit(
            delay_minutes=300, test_price=Decimal("200.00"), is_exempt_from_credit=True
        )
        self.assertEqual(pct, Decimal("0.0"))
        self.assertEqual(amt, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
