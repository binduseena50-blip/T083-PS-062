"""End-to-end Integration Test validating full engine run against sample data pack."""

from pathlib import Path
import unittest
import pandas as pd

from engine.core import DiagnosticLabEngine


class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = Path("sample_data/T083-PS-062-sample-data")
        cls.output_dir = Path("output_test_run")
        cls.engine = DiagnosticLabEngine(cls.data_dir)
        cls.engine.process_command_file(cls.data_dir / "commands.txt")
        cls.engine.export_all_reports(cls.output_dir)

    def test_output_files_exist_and_non_empty(self):
        """Verifies that all 5 evaluation CSV files exist and are populated."""
        files = [
            "order_tests.csv",
            "status_history.csv",
            "bills.csv",
            "tat_breaches.csv",
            "capacity_report.csv",
        ]
        for f in files:
            path = self.output_dir / f
            self.assertTrue(path.exists(), f"Missing output file {f}")
            self.assertGreater(path.stat().st_size, 0, f"File {f} is empty")

    def test_canonical_schemas_and_row_counts(self):
        """Verifies canonical schemas and row count expectations."""
        ot = pd.read_csv(self.output_dir / "order_tests.csv")
        self.assertEqual(
            list(ot.columns),
            [
                "order_id", "test_code", "routed_lab_id", "routing_reason",
                "collected_ts", "received_ts", "promised_ts", "reported_ts",
                "status", "tat_breach_hours", "flags",
            ],
        )
        self.assertEqual(len(ot), 511)

        bills = pd.read_csv(self.output_dir / "bills.csv")
        self.assertEqual(
            list(bills.columns),
            [
                "order_id", "tests_amount", "panels_amount", "duplicate_removed",
                "priority_surcharge", "tube_fee", "home_collection_fee",
                "cancellation_charge", "delay_credit", "refund", "net_amount",
            ],
        )
        self.assertEqual(len(bills), 120)

        caps = pd.read_csv(self.output_dir / "capacity_report.csv")
        self.assertEqual(
            list(caps.columns),
            ["date", "lab_id", "sample_type", "capacity", "used", "overflow_routed"],
        )
        # 10 days * 4 labs * 4 sample types = 160 rows
        self.assertEqual(len(caps), 160)

        breaches = pd.read_csv(self.output_dir / "tat_breaches.csv")
        self.assertEqual(
            list(breaches.columns),
            [
                "order_id", "test_code", "promised_ts", "reported_ts",
                "delay_minutes", "credit_pct", "credit_amount", "breach_type",
            ],
        )
        # 313 normal TAT breaches + 1 critical breach = 314 rows
        self.assertEqual(len(breaches), 314)


if __name__ == "__main__":
    unittest.main()
