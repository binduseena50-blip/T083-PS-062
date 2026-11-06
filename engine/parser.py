"""CSV and command file parser for PS-062 Diagnostic Lab TAT Engine."""

import csv
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engine.models import (
    CourierRoute,
    Lab,
    LabTier,
    Order,
    OrderItem,
    Panel,
    Phlebotomist,
    Priority,
    SampleType,
    TestMaster,
    TubeType,
)


def parse_time_hh_mm(val: str) -> time:
    parts = val.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def parse_datetime(val: str) -> Optional[datetime]:
    v = val.strip()
    if not v:
        return None
    return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")


def parse_decimal(val: str) -> Optional[Decimal]:
    v = val.strip()
    if not v:
        return None
    return Decimal(v)


def parse_bool(val: str) -> bool:
    v = val.strip().lower()
    return v in ("true", "1", "yes", "t")


class DataLoader:
    @staticmethod
    def load_tests(filepath: Path) -> Dict[str, TestMaster]:
        tests = {}
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tcode = row["test_code"].strip()
                tests[tcode] = TestMaster(
                    test_code=tcode,
                    test_name=row["test_name"].strip(),
                    sample_type=SampleType(row["sample_type"].strip()),
                    tube_type=TubeType(row["tube_type"].strip()),
                    fasting_hours=int(row["fasting_hours"].strip()),
                    std_tat_hours=int(row["std_tat_hours"].strip()),
                    lab_tier=LabTier(row["lab_tier"].strip()),
                    price=Decimal(row["price"].strip()),
                    critical_low=parse_decimal(row.get("critical_low", "")),
                    critical_high=parse_decimal(row.get("critical_high", "")),
                    unit=row.get("unit", "").strip(),
                )
        return tests

    @staticmethod
    def load_panels(
        panels_filepath: Path, panel_tests_filepath: Path
    ) -> Dict[str, Panel]:
        panels = {}
        with open(panels_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row["panel_id"].strip()
                panels[pid] = Panel(
                    panel_id=pid,
                    panel_name=row["panel_name"].strip(),
                    price=Decimal(row["price"].strip()),
                    member_tests=[],
                )
        with open(panel_tests_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row["panel_id"].strip()
                tcode = row["test_code"].strip()
                if pid in panels:
                    panels[pid].member_tests.append(tcode)
        return panels

    @staticmethod
    def load_labs(
        labs_filepath: Path, capacity_filepath: Path
    ) -> Dict[str, Lab]:
        labs = {}
        with open(labs_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lid = row["lab_id"].strip()
                labs[lid] = Lab(
                    lab_id=lid,
                    lab_name=row["lab_name"].strip(),
                    tier=LabTier(row["tier"].strip()),
                    open_time=parse_time_hh_mm(row["open_time"]),
                    close_time=parse_time_hh_mm(row["close_time"]),
                    stat_24x7=parse_bool(row["stat_24x7"]),
                    latitude=float(row["latitude"].strip()),
                    longitude=float(row["longitude"].strip()),
                    daily_capacities={},
                )
        with open(capacity_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lid = row["lab_id"].strip()
                stype = SampleType(row["sample_type"].strip())
                cap = int(row["daily_capacity"].strip())
                if lid in labs:
                    labs[lid].daily_capacities[stype] = cap
        return labs

    @staticmethod
    def load_courier_routes(filepath: Path) -> List[CourierRoute]:
        routes = []
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                routes.append(
                    CourierRoute(
                        from_lab_id=row["from_lab_id"].strip(),
                        to_lab_id=row["to_lab_id"].strip(),
                        cutoff_time=parse_time_hh_mm(row["cutoff_time"]),
                        departure_time=parse_time_hh_mm(row["departure_time"]),
                        transit_minutes=int(row["transit_minutes"].strip()),
                    )
                )
        return routes

    @staticmethod
    def load_phlebotomists(filepath: Path) -> Dict[str, Phlebotomist]:
        phlebs = {}
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row["phleb_id"].strip()
                phlebs[pid] = Phlebotomist(
                    phleb_id=pid,
                    phleb_name=row["phleb_name"].strip(),
                    base_lab_id=row["base_lab_id"].strip(),
                    shift_start=parse_time_hh_mm(row["shift_start"]),
                    shift_end=parse_time_hh_mm(row["shift_end"]),
                    max_visits_per_day=int(row["max_visits_per_day"].strip()),
                )
        return phlebs

    @staticmethod
    def load_orders(filepath: Path) -> Dict[str, Order]:
        orders = {}
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                oid = row["order_id"].strip()
                lat_str = row.get("address_lat", "").strip()
                lon_str = row.get("address_lon", "").strip()
                orders[oid] = Order(
                    order_id=oid,
                    patient_name=row["patient_name"].strip(),
                    age=int(row["age"].strip()),
                    gender=row["gender"].strip(),
                    order_ts=parse_datetime(row["order_ts"]),
                    priority=Priority(row["priority"].strip()),
                    collection_lab_id=row["collection_lab_id"].strip(),
                    home_collection=parse_bool(row["home_collection"]),
                    slot_start=parse_datetime(row["slot_start"]),
                    address_lat=float(lat_str) if lat_str else None,
                    address_lon=float(lon_str) if lon_str else None,
                    last_meal_ts=parse_datetime(row.get("last_meal_ts", "")),
                )
        return orders

    @staticmethod
    def load_order_items(filepath: Path) -> List[OrderItem]:
        items = []
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(
                    OrderItem(
                        order_id=row["order_id"].strip(),
                        item_type=row["item_type"].strip(),
                        item_code=row["item_code"].strip(),
                    )
                )
        return items
