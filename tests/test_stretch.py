"""Unit tests for Stretch Goals: Delta-Check Engine & Batch Analyser Scheduling (BR-13 & BR-14)."""

from datetime import datetime, timedelta
from decimal import Decimal
import unittest

from engine.stretch import BatchAnalyserScheduler, DeltaCheckEngine


class TestStretchGoals(unittest.TestCase):
    def test_delta_check_alert(self):
        """
        BR-13 (Stretch Goal):
        Delta-check flags a result differing from patient's last result by > 30% for re-run.
        """
        engine = DeltaCheckEngine(threshold_pct=Decimal("30.0"))
        t1 = datetime(2026, 10, 1, 9, 0)
        t2 = datetime(2026, 10, 8, 9, 0)

        # Baseline: Potassium 4.0
        res1 = engine.evaluate("Patient John", "TST-K", Decimal("4.0"), t1)
        self.assertIsNone(res1)  # No previous result

        # Normal re-test: 4.5 (+12.5%, <= 30%)
        res2 = engine.evaluate("Patient John", "TST-K", Decimal("4.5"), t2)
        self.assertIsNotNone(res2)
        self.assertFalse(res2.is_alert)
        self.assertEqual(res2.delta_percentage, Decimal("12.50"))

        # Drastic jump: 6.5 (diff from 4.5 is 2.0 / 4.5 = 44.44% > 30%)
        t3 = datetime(2026, 10, 9, 9, 0)
        res3 = engine.evaluate("Patient John", "TST-K", Decimal("6.5"), t3)
        self.assertIsNotNone(res3)
        self.assertTrue(res3.is_alert)
        self.assertEqual(res3.delta_percentage, Decimal("44.44"))
        self.assertEqual(len(engine.alerts), 1)

    def test_batch_analyser_scheduling_capacity_trigger(self):
        """
        BR-14 (Stretch Goal):
        A batch run triggers as soon as 10 samples accumulate.
        """
        scheduler = BatchAnalyserScheduler(batch_size=10, timeout_hours=2)
        t0 = datetime(2026, 10, 5, 8, 0)

        # Enqueue 9 samples
        batch = None
        for i in range(1, 10):
            batch = scheduler.enqueue_sample(
                "LAB-01", "BLOOD", f"SAMPLE-{i:03d}", t0 + timedelta(minutes=i * 5)
            )
            self.assertIsNone(batch)

        # 10th sample arrives -> Batch triggers!
        t_10 = t0 + timedelta(minutes=50)
        batch = scheduler.enqueue_sample("LAB-01", "BLOOD", "SAMPLE-010", t_10)
        self.assertIsNotNone(batch)
        self.assertEqual(len(batch.sample_ids), 10)
        self.assertEqual(batch.trigger_reason, "CAPACITY_REACHED (10)")

    def test_batch_analyser_scheduling_timeout_trigger(self):
        """
        BR-14 (Stretch Goal):
        A batch run triggers when 2 hours have elapsed since oldest sample in queue.
        """
        scheduler = BatchAnalyserScheduler(batch_size=10, timeout_hours=2)
        t0 = datetime(2026, 10, 5, 8, 0)

        # Enqueue 3 samples starting from t0
        for i in range(3):
            scheduler.enqueue_sample(
                "LAB-01", "URINE", f"SAMPLE-{i+1:03d}", t0 + timedelta(minutes=i * 10)
            )

        # Exactly 2 hours after oldest sample t0 (10:00)
        t_timeout = t0 + timedelta(hours=2)
        expired_batches = scheduler.flush_expired_batches(t_timeout)
        self.assertEqual(len(expired_batches), 1)
        self.assertEqual(len(expired_batches[0].sample_ids), 3)
        self.assertEqual(expired_batches[0].trigger_reason, "TIMEOUT (2h)")


if __name__ == "__main__":
    unittest.main()
