"""Stretch goals: Patient Delta-Check Engine & Batch-based Analyser Scheduling (BR-13 & BR-14)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


@dataclass
class DeltaCheckResult:
    patient_name: str
    test_code: str
    previous_value: Decimal
    current_value: Decimal
    delta_percentage: Decimal
    is_alert: bool
    timestamp: datetime


class DeltaCheckEngine:
    """
    BR-13 (Stretch Goal):
    Flags a result differing from the patient's last result by more than 30% for re-run.
    """
    def __init__(self, threshold_pct: Decimal = Decimal("30.0")):
        self.threshold_pct = threshold_pct
        self.patient_history: Dict[str, Dict[str, Tuple[Decimal, datetime]]] = defaultdict(dict)
        self.alerts: List[DeltaCheckResult] = []

    def evaluate(
        self, patient_name: str, test_code: str, value: Decimal, ts: datetime
    ) -> Optional[DeltaCheckResult]:
        prev_entry = self.patient_history[patient_name].get(test_code)
        self.patient_history[patient_name][test_code] = (value, ts)

        if prev_entry is None:
            return None

        prev_val, _ = prev_entry
        if prev_val == Decimal("0.0"):
            return None

        diff = abs(value - prev_val)
        delta_pct = (diff / prev_val * Decimal("100.0")).quantize(Decimal("0.01"))
        is_alert = delta_pct > self.threshold_pct

        res = DeltaCheckResult(
            patient_name=patient_name,
            test_code=test_code,
            previous_value=prev_val,
            current_value=value,
            delta_percentage=delta_pct,
            is_alert=is_alert,
            timestamp=ts,
        )
        if is_alert:
            self.alerts.append(res)
        return res


@dataclass
class SampleBatch:
    batch_id: str
    lab_id: str
    sample_type: str
    sample_ids: List[str]
    trigger_reason: str  # 'CAPACITY_REACHED (10)' or 'TIMEOUT (2h)'
    queue_start_ts: datetime
    run_start_ts: datetime


class BatchAnalyserScheduler:
    """
    BR-14 (Stretch Goal):
    Batch-based analyser scheduling where a run starts only when
    10 samples or 2 hours accumulate.
    """
    def __init__(self, batch_size: int = 10, timeout_hours: int = 2):
        self.batch_size = batch_size
        self.timeout = timedelta(hours=timeout_hours)
        # queue: (lab_id, sample_type) -> list of (sample_id, received_ts)
        self.queues: Dict[Tuple[str, str], List[Tuple[str, datetime]]] = defaultdict(list)
        self.completed_batches: List[SampleBatch] = []
        self._batch_counter = 1

    def enqueue_sample(
        self, lab_id: str, sample_type: str, sample_id: str, received_ts: datetime
    ) -> Optional[SampleBatch]:
        key = (lab_id, sample_type)
        q = self.queues[key]
        q.append((sample_id, received_ts))

        # Check triggers
        # 1. 10 samples accumulated
        if len(q) >= self.batch_size:
            return self._trigger_batch(key, received_ts, f"CAPACITY_REACHED ({self.batch_size})")

        # 2. Timeout check against oldest sample in queue
        oldest_ts = q[0][1]
        if (received_ts - oldest_ts) >= self.timeout:
            return self._trigger_batch(key, received_ts, f"TIMEOUT ({self.timeout.total_seconds()//3600:.0f}h)")

        return None

    def flush_expired_batches(self, current_ts: datetime) -> List[SampleBatch]:
        """Flushes any batches where 2 hours have elapsed since oldest sample."""
        triggered = []
        for key in list(self.queues.keys()):
            q = self.queues[key]
            if q:
                oldest_ts = q[0][1]
                if (current_ts - oldest_ts) >= self.timeout:
                    triggered.append(
                        self._trigger_batch(key, current_ts, f"TIMEOUT ({self.timeout.total_seconds()//3600:.0f}h)")
                    )
        return triggered

    def _trigger_batch(
        self, key: Tuple[str, str], current_ts: datetime, reason: str
    ) -> SampleBatch:
        q = self.queues[key]
        sample_ids = [s[0] for s in q]
        queue_start = q[0][1]
        self.queues[key] = []

        batch = SampleBatch(
            batch_id=f"BATCH-{self._batch_counter:04d}",
            lab_id=key[0],
            sample_type=key[1],
            sample_ids=sample_ids,
            trigger_reason=reason,
            queue_start_ts=queue_start,
            run_start_ts=current_ts,
        )
        self._batch_counter += 1
        self.completed_batches.append(batch)
        return batch
