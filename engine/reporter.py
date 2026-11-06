"""Report generator and CSV serializer matching exact evaluation specifications."""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from engine.models import (
    BillRecord,
    CapacityRecord,
    Order,
    OrderTestRecord,
    StatusChangeRecord,
    TATBreachRecord,
    TestStatus,
)


def format_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_decimal_2dp(val: Optional[Decimal]) -> str:
    if val is None:
        return ""
    return f"{val:.2f}"


def format_pct(val: Decimal) -> str:
    # Print as plain number without trailing zeroes if whole
    if val == Decimal("0.0") or val == Decimal("0"):
        return "0"
    if val == val.to_integral():
        return f"{int(val)}"
    return f"{val:.1f}"


class ReportGenerator:
    @staticmethod
    def write_order_tests_csv(
        filepath: Path,
        test_records: Dict[Tuple[str, str], OrderTestRecord],
    ):
        """
        ### order_tests.csv
        One row per unique test per order.
        Columns, in order: order_id, test_code, routed_lab_id, routing_reason,
        collected_ts, received_ts, promised_ts, reported_ts, status, tat_breach_hours, flags
        """
        sorted_keys = sorted(test_records.keys(), key=lambda k: (k[0], k[1]))
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "order_id",
                "test_code",
                "routed_lab_id",
                "routing_reason",
                "collected_ts",
                "received_ts",
                "promised_ts",
                "reported_ts",
                "status",
                "tat_breach_hours",
                "flags",
            ])
            for key in sorted_keys:
                rec = test_records[key]
                flags_str = ";".join(sorted(list(rec.flags)))
                writer.writerow([
                    rec.order_id,
                    rec.test_code,
                    rec.routed_lab_id,
                    rec.routing_reason.value if hasattr(rec.routing_reason, "value") else str(rec.routing_reason),
                    format_dt(rec.collected_ts),
                    format_dt(rec.received_ts),
                    format_dt(rec.promised_ts),
                    format_dt(rec.reported_ts),
                    rec.status.value if hasattr(rec.status, "value") else str(rec.status),
                    format_decimal_2dp(rec.tat_breach_hours),
                    flags_str,
                ])

    @staticmethod
    def write_status_history_csv(
        filepath: Path,
        status_history: List[StatusChangeRecord],
    ):
        """
        ### status_history.csv
        One row per state change.
        Columns, in order: order_id, test_code, status, ts
        """
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["order_id", "test_code", "status", "ts"])
            for rec in status_history:
                writer.writerow([
                    rec.order_id,
                    rec.test_code,
                    rec.status.value if hasattr(rec.status, "value") else str(rec.status),
                    format_dt(rec.ts),
                ])

    @staticmethod
    def write_bills_csv(
        filepath: Path,
        bills: Dict[str, BillRecord],
    ):
        """
        ### bills.csv
        One row per order.
        Columns, in order: order_id, tests_amount, panels_amount, duplicate_removed,
        priority_surcharge, tube_fee, home_collection_fee, cancellation_charge, delay_credit, refund, net_amount
        """
        sorted_oids = sorted(bills.keys())
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "order_id",
                "tests_amount",
                "panels_amount",
                "duplicate_removed",
                "priority_surcharge",
                "tube_fee",
                "home_collection_fee",
                "cancellation_charge",
                "delay_credit",
                "refund",
                "net_amount",
            ])
            for oid in sorted_oids:
                b = bills[oid]
                writer.writerow([
                    b.order_id,
                    format_decimal_2dp(b.tests_amount),
                    format_decimal_2dp(b.panels_amount),
                    format_decimal_2dp(b.duplicate_removed),
                    format_decimal_2dp(b.priority_surcharge),
                    format_decimal_2dp(b.tube_fee),
                    format_decimal_2dp(b.home_collection_fee),
                    format_decimal_2dp(b.cancellation_charge),
                    format_decimal_2dp(b.delay_credit),
                    format_decimal_2dp(b.refund),
                    format_decimal_2dp(b.net_amount),
                ])

    @staticmethod
    def write_tat_breaches_csv(
        filepath: Path,
        tat_breaches: List[TATBreachRecord],
    ):
        """
        ### tat_breaches.csv
        One row per breached test.
        Columns, in order: order_id, test_code, promised_ts, reported_ts,
        delay_minutes, credit_pct, credit_amount, breach_type
        """
        sorted_breaches = sorted(
            tat_breaches, key=lambda b: (b.order_id, b.test_code, b.breach_type.value)
        )
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "order_id",
                "test_code",
                "promised_ts",
                "reported_ts",
                "delay_minutes",
                "credit_pct",
                "credit_amount",
                "breach_type",
            ])
            for b in sorted_breaches:
                writer.writerow([
                    b.order_id,
                    b.test_code,
                    format_dt(b.promised_ts),
                    format_dt(b.reported_ts),
                    b.delay_minutes,
                    format_pct(b.credit_pct),
                    format_decimal_2dp(b.credit_amount),
                    b.breach_type.value if hasattr(b.breach_type, "value") else str(b.breach_type),
                ])

    @staticmethod
    def write_capacity_report_csv(
        filepath: Path,
        capacity_records: List[CapacityRecord],
    ):
        """
        ### capacity_report.csv
        One row per lab per sample type per PRINT_CAPACITY.
        Columns, in order: date, lab_id, sample_type, capacity, used, overflow_routed
        """
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "date",
                "lab_id",
                "sample_type",
                "capacity",
                "used",
                "overflow_routed",
            ])
            for r in capacity_records:
                writer.writerow([
                    r.date,
                    r.lab_id,
                    r.sample_type.value if hasattr(r.sample_type, "value") else str(r.sample_type),
                    r.capacity,
                    r.used,
                    r.overflow_routed,
                ])
