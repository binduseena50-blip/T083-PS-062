"""Domain models, enumerations, and data structures for PS-062 Diagnostic Lab TAT Engine."""

from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class SampleType(str, Enum):
    BLOOD = "BLOOD"
    URINE = "URINE"
    SWAB = "SWAB"
    TISSUE = "TISSUE"


class TubeType(str, Enum):
    SST = "SST"
    EDTA = "EDTA"
    CITRATE = "CITRATE"
    FLUORIDE = "FLUORIDE"
    URINE_CUP = "URINE_CUP"
    SWAB_TUBE = "SWAB_TUBE"
    FORMALIN_JAR = "FORMALIN_JAR"


class LabTier(str, Enum):
    L1 = "L1"
    L2 = "L2"
    REFERENCE = "REFERENCE"

    @property
    def rank(self) -> int:
        if self == LabTier.L1:
            return 1
        elif self == LabTier.L2:
            return 2
        return 3

    def can_process(self, test_tier: "LabTier") -> bool:
        return self.rank >= test_tier.rank


class Priority(str, Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    STAT = "STAT"

    @property
    def tat_multiplier(self) -> float:
        if self == Priority.ROUTINE:
            return 1.0
        elif self == Priority.URGENT:
            return 0.5
        elif self == Priority.STAT:
            return 0.25
        return 1.0

    @property
    def surcharge_multiplier(self) -> float:
        if self == Priority.ROUTINE:
            return 0.0
        elif self == Priority.URGENT:
            return 0.5
        elif self == Priority.STAT:
            return 1.0
        return 0.0


class TestStatus(str, Enum):
    CREATED = "CREATED"
    NEEDS_RESCHEDULE = "NEEDS_RESCHEDULE"
    COLLECTED = "COLLECTED"
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    RESULTED = "RESULTED"
    VERIFIED = "VERIFIED"
    REPORTED = "REPORTED"
    REJECTED_SAMPLE = "REJECTED_SAMPLE"
    CANCELLED = "CANCELLED"


class BreachType(str, Enum):
    TAT = "TAT"
    CRITICAL = "CRITICAL"


class RoutingReason(str, Enum):
    LOCAL = "LOCAL"
    TIER_REQUIREMENT = "TIER_REQUIREMENT"
    CAPACITY_OVERFLOW = "CAPACITY_OVERFLOW"


@dataclass
class TestMaster:
    test_code: str
    test_name: str
    sample_type: SampleType
    tube_type: TubeType
    fasting_hours: int
    std_tat_hours: int
    lab_tier: LabTier
    price: Decimal
    critical_low: Optional[Decimal] = None
    critical_high: Optional[Decimal] = None
    unit: str = ""

    def is_critical(self, value: Optional[Decimal]) -> bool:
        if value is None:
            return False
        if self.critical_low is not None and value < self.critical_low:
            return True
        if self.critical_high is not None and value > self.critical_high:
            return True
        return False


@dataclass
class Panel:
    panel_id: str
    panel_name: str
    price: Decimal
    member_tests: List[str] = field(default_factory=list)


@dataclass
class Lab:
    lab_id: str
    lab_name: str
    tier: LabTier
    open_time: time
    close_time: time
    stat_24x7: bool
    latitude: float
    longitude: float
    daily_capacities: Dict[SampleType, int] = field(default_factory=dict)


@dataclass
class CourierRoute:
    from_lab_id: str
    to_lab_id: str
    cutoff_time: time
    departure_time: time
    transit_minutes: int


@dataclass
class Phlebotomist:
    phleb_id: str
    phleb_name: str
    base_lab_id: str
    shift_start: time
    shift_end: time
    max_visits_per_day: int


@dataclass
class OrderItem:
    order_id: str
    item_type: str  # TEST or PANEL
    item_code: str


@dataclass
class Order:
    order_id: str
    patient_name: str
    age: int
    gender: str
    order_ts: datetime
    priority: Priority
    collection_lab_id: str
    home_collection: bool
    slot_start: datetime
    address_lat: Optional[float] = None
    address_lon: Optional[float] = None
    last_meal_ts: Optional[datetime] = None
    status: TestStatus = TestStatus.CREATED
    cancellation_reason: Optional[str] = None
    fasting_waived: bool = False
    recollection_scheduled: bool = False
    recollection_ts: Optional[datetime] = None


@dataclass
class OrderTestRecord:
    order_id: str
    test_code: str
    routed_lab_id: str
    routing_reason: RoutingReason
    collected_ts: Optional[datetime] = None
    received_ts: Optional[datetime] = None
    promised_ts: Optional[datetime] = None
    reported_ts: Optional[datetime] = None
    status: TestStatus = TestStatus.CREATED
    tat_breach_hours: Optional[Decimal] = None
    flags: Set[str] = field(default_factory=set)
    latest_result_val: Optional[Decimal] = None
    result_ts: Optional[datetime] = None
    verified_ts: Optional[datetime] = None
    doctor_verified_ts: Optional[datetime] = None
    rejection_count: int = 0
    base_price: Decimal = Decimal("0.00")
    from_panel: Optional[str] = None
    is_duplicate_removed: bool = False


@dataclass
class StatusChangeRecord:
    order_id: str
    test_code: str
    status: TestStatus
    ts: datetime


@dataclass
class BillRecord:
    order_id: str
    tests_amount: Decimal = Decimal("0.00")
    panels_amount: Decimal = Decimal("0.00")
    duplicate_removed: Decimal = Decimal("0.00")
    priority_surcharge: Decimal = Decimal("0.00")
    tube_fee: Decimal = Decimal("0.00")
    home_collection_fee: Decimal = Decimal("0.00")
    cancellation_charge: Decimal = Decimal("0.00")
    delay_credit: Decimal = Decimal("0.00")
    refund: Decimal = Decimal("0.00")
    net_amount: Decimal = Decimal("0.00")


@dataclass
class TATBreachRecord:
    order_id: str
    test_code: str
    promised_ts: datetime
    reported_ts: datetime
    delay_minutes: int
    credit_pct: Decimal
    credit_amount: Decimal
    breach_type: BreachType


@dataclass
class CapacityRecord:
    date: str
    lab_id: str
    sample_type: SampleType
    capacity: int
    used: int
    overflow_routed: int
