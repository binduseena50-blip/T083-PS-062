"""Multi-tier lab routing, courier cut-offs, and daily capacity tracking (BR-03)."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from engine.models import (
    CapacityRecord,
    CourierRoute,
    Lab,
    LabTier,
    Order,
    RoutingReason,
    SampleType,
    TestMaster,
)


class LabRouter:
    def __init__(
        self,
        labs: Dict[str, Lab],
        courier_routes: List[CourierRoute],
    ):
        self.labs = labs
        self.courier_routes = courier_routes
        # Track daily usage: date_str -> (lab_id, sample_type) -> count
        self.daily_usage: Dict[str, Dict[Tuple[str, SampleType], int]] = (
            defaultdict(lambda: defaultdict(int))
        )
        # Track daily overflow: date_str -> (lab_id, sample_type) -> count
        self.daily_overflow: Dict[str, Dict[Tuple[str, SampleType], int]] = (
            defaultdict(lambda: defaultdict(int))
        )

    def route_test(
        self,
        order: Order,
        test: TestMaster,
        collection_date_str: str,
    ) -> Tuple[str, RoutingReason]:
        """
        BR-03: Routing Engine.
        A test is processed at the lowest-tier lab that performs it with remaining daily
        capacity for that sample type. If local lab is at capacity or does not perform
        the test, the sample is couriered to next tier.
        """
        local_lab_id = order.collection_lab_id
        local_lab = self.labs[local_lab_id]
        stype = test.sample_type
        req_tier = test.lab_tier

        # Step 1: Does the local lab support this tier?
        if not local_lab.tier.can_process(req_tier):
            # Must go to next tier that can process
            target_lab = "LAB-03" if req_tier == LabTier.L2 else "LAB-04"
            self.daily_usage[collection_date_str][(target_lab, stype)] += 1
            return target_lab, RoutingReason.TIER_REQUIREMENT

        # Step 2: Does local lab process this sample type?
        local_cap = local_lab.daily_capacities.get(stype, 0)
        if local_cap == 0:
            # Does not process this sample type
            target_lab = "LAB-03"
            self.daily_usage[collection_date_str][(target_lab, stype)] += 1
            return target_lab, RoutingReason.TIER_REQUIREMENT

        # Step 3: Check remaining capacity at local lab
        current_used = self.daily_usage[collection_date_str][
            (local_lab_id, stype)
        ]
        if current_used < local_cap:
            # Capacity available locally!
            self.daily_usage[collection_date_str][
                (local_lab_id, stype)
            ] += 1
            return local_lab_id, RoutingReason.LOCAL
        else:
            # Capacity exhausted! Courier to next tier (LAB-03)
            self.daily_overflow[collection_date_str][
                (local_lab_id, stype)
            ] += 1
            target_lab = "LAB-03"
            # Route to LAB-03 and consume capacity there
            self.daily_usage[collection_date_str][(target_lab, stype)] += 1
            return target_lab, RoutingReason.CAPACITY_OVERFLOW

    def get_courier_departure_and_arrival(
        self,
        from_lab_id: str,
        to_lab_id: str,
        collected_ts: datetime,
    ) -> Tuple[datetime, datetime]:
        """
        Calculates courier departure and physical arrival time based on cut-off and transit.
        Edge case EC-03: Collected at exactly cut-off time departs today.
        Trap: Collected 1 min after cut-off departs next day.
        """
        route = next(
            (
                r
                for r in self.courier_routes
                if r.from_lab_id == from_lab_id and r.to_lab_id == to_lab_id
            ),
            None,
        )
        if not route:
            # Fallback if direct route not found
            return collected_ts, collected_ts

        col_time = collected_ts.time()
        col_date = collected_ts.date()

        if col_time <= route.cutoff_time:
            # Departs today
            departure_dt = datetime.combine(col_date, route.departure_time)
        else:
            # Departs next day
            departure_dt = datetime.combine(
                col_date + timedelta(days=1), route.departure_time
            )

        arrival_dt = departure_dt + timedelta(minutes=route.transit_minutes)
        return departure_dt, arrival_dt

    def generate_capacity_records(self, date_str: str) -> List[CapacityRecord]:
        """
        Generates CapacityRecord rows for all labs and sample types for a given date.
        Sorted by lab_id, sample_type.
        """
        records = []
        sample_types = [
            SampleType.BLOOD,
            SampleType.URINE,
            SampleType.SWAB,
            SampleType.TISSUE,
        ]
        for lid in sorted(self.labs.keys()):
            lab = self.labs[lid]
            for stype in sample_types:
                cap = lab.daily_capacities.get(stype, 0)
                used = self.daily_usage[date_str].get((lid, stype), 0)
                overflow = self.daily_overflow[date_str].get((lid, stype), 0)
                records.append(
                    CapacityRecord(
                        date=date_str,
                        lab_id=lid,
                        sample_type=stype,
                        capacity=cap,
                        used=used,
                        overflow_routed=overflow,
                    )
                )
        return records
