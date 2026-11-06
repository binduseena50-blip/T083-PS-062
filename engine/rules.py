"""Core business rule implementations (BR-01 through BR-12) for PS-062."""

from datetime import datetime, time, timedelta
from decimal import Decimal
import math
from typing import Dict, List, Optional, Set, Tuple

from engine.models import (
    BreachType,
    Lab,
    LabTier,
    Order,
    OrderItem,
    Panel,
    Priority,
    SampleType,
    TestMaster,
    TubeType,
)


def calculate_haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Computes straight-line Haversine distance in km using R = 6371.0 km, rounded to 2 decimal places."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    # Numerical safeguard
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    dist = R * c
    return round(dist, 2)


def check_fasting_requirement(
    order: Order, tests_in_order: List[TestMaster]
) -> Tuple[bool, int]:
    """
    BR-01: Fasting Validation.
    If any ordered test requires fasting of N hours, the collection slot must be at least N hours
    after the patient's stated last-meal time; the longest fasting requirement governs.
    Edge case EC-01: Slot exactly N hours after last meal is valid (slot >= last_meal + N).
    Returns (is_valid, max_fasting_hours).
    """
    max_fasting = max((t.fasting_hours for t in tests_in_order), default=0)
    if max_fasting == 0:
        return True, 0

    if order.last_meal_ts is None:
        return False, max_fasting

    required_slot_time = order.last_meal_ts + timedelta(hours=max_fasting)
    if order.slot_start >= required_slot_time:
        return True, max_fasting
    return False, max_fasting


def calculate_tubes_and_fee(tests_in_order: List[TestMaster]) -> Tuple[int, Decimal]:
    """
    BR-02: Tube Sharing.
    Tests with same sample type and tube type share one tube.
    A tube may serve at most 4 tests.
    Order's tube count drives collection fee: Rs 50 per tube beyond the second.
    Edge case EC-02: 5 tests of same type require 2 tubes.
    Returns (total_tubes, tube_fee).
    """
    groups: Dict[Tuple[SampleType, TubeType], int] = {}
    for t in tests_in_order:
        key = (t.sample_type, t.tube_type)
        groups[key] = groups.get(key, 0) + 1

    total_tubes = 0
    for count in groups.values():
        total_tubes += math.ceil(count / 4.0)

    if total_tubes > 2:
        extra_tubes = total_tubes - 2
        tube_fee = Decimal(str(extra_tubes * 50))
    else:
        tube_fee = Decimal("0.00")

    return total_tubes, tube_fee


def round_up_to_next_hour(dt: datetime) -> datetime:
    """Rounds up a datetime to the next full hour if not already an exact hour."""
    if dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def compute_promised_tat(
    collected_ts: datetime,
    test: TestMaster,
    priority: Priority,
) -> datetime:
    """
    BR-04: Promised TAT Computation.
    Standard TAT by priority multiplier: ROUTINE 1.0x, URGENT 0.5x, STAT 0.25x (minimum 2 hours).
    TAT clock starts at COLLECTED.
    For REFERENCE-tier tests, add 24 hours courier time.
    Promised report time rounds up to the next hour.
    Edge case EC-04: STAT with 0.25x of 4h = 1h, raised to 2h minimum.
    """
    base_tat = test.std_tat_hours * priority.tat_multiplier
    effective_tat = max(2.0, base_tat)

    if test.lab_tier == LabTier.REFERENCE:
        effective_tat += 24.0

    raw_target = collected_ts + timedelta(hours=effective_tat)
    return round_up_to_next_hour(raw_target)


def get_next_opening_time(target_dt: datetime, lab: Lab) -> datetime:
    """
    BR-05: Lab Operating Hours.
    If a sample is received outside operating hours (and not STAT at 24x7 L1 lab),
    it is received at the next opening time.
    """
    t = target_dt.time()
    if lab.open_time <= t < lab.close_time:
        return target_dt

    if t < lab.open_time:
        # Same day opening time
        return target_dt.replace(
            hour=lab.open_time.hour,
            minute=lab.open_time.minute,
            second=0,
            microsecond=0,
        )
    else:
        # Next day opening time
        next_day = target_dt + timedelta(days=1)
        return next_day.replace(
            hour=lab.open_time.hour,
            minute=lab.open_time.minute,
            second=0,
            microsecond=0,
        )


def compute_delay_credit(
    delay_minutes: int,
    test_price: Decimal,
    is_exempt_from_credit: bool,
) -> Tuple[Decimal, Decimal]:
    """
    BR-10: Delayed-Report Credits.
    If actual REPORTED time exceeds promised by more than 2 hours (> 120 min),
    credit 10% of that test's price; more than 24 hours (> 1440 min), credit 50%.
    Credits are capped at the test price and are not issued if delay was caused by:
    - patient-side recollection, OR
    - waived fasting breach.
    Edge case EC-08: Delayed by exactly 2 hours (120 min) gets 0% credit.
    Returns (credit_pct, credit_amount).
    """
    if delay_minutes <= 120 or is_exempt_from_credit:
        return Decimal("0.0"), Decimal("0.00")

    if delay_minutes > 1440:
        pct = Decimal("50.0")
    else:
        pct = Decimal("10.0")

    credit_amount = (test_price * (pct / Decimal("100.0"))).quantize(
        Decimal("0.01")
    )
    if credit_amount > test_price:
        credit_amount = test_price

    return pct, credit_amount
