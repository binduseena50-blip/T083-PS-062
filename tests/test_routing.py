"""Unit tests for Multi-tier Routing and operating hours (BR-03, BR-05, EC-03, EC-05)."""

from datetime import datetime, time
from decimal import Decimal
import unittest

from engine.models import CourierRoute, Lab, LabTier, Order, Priority, RoutingReason, SampleType, TestMaster, TubeType
from engine.router import LabRouter
from engine.rules import get_next_opening_time


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.lab1 = Lab(
            lab_id="LAB-01",
            lab_name="Collection Lab 1",
            tier=LabTier.L1,
            open_time=time(7, 0),
            close_time=time(21, 0),
            stat_24x7=True,
            latitude=12.9250,
            longitude=77.5830,
            daily_capacities={SampleType.BLOOD: 10, SampleType.URINE: 2},
        )
        self.lab2 = Lab(
            lab_id="LAB-02",
            lab_name="Collection Lab 2",
            tier=LabTier.L1,
            open_time=time(7, 0),
            close_time=time(21, 0),
            stat_24x7=True,
            latitude=12.9698,
            longitude=77.7500,
            daily_capacities={SampleType.BLOOD: 5, SampleType.URINE: 1},
        )
        self.lab3 = Lab(
            lab_id="LAB-03",
            lab_name="Regional Lab",
            tier=LabTier.L2,
            open_time=time(6, 0),
            close_time=time(23, 0),
            stat_24x7=False,
            latitude=12.9352,
            longitude=77.6245,
            daily_capacities={SampleType.BLOOD: 50, SampleType.URINE: 20},
        )
        self.lab4 = Lab(
            lab_id="LAB-04",
            lab_name="Reference Lab",
            tier=LabTier.REFERENCE,
            open_time=time(8, 0),
            close_time=time(20, 0),
            stat_24x7=False,
            latitude=13.0355,
            longitude=77.5970,
            daily_capacities={SampleType.BLOOD: 100, SampleType.URINE: 50},
        )
        self.labs = {
            "LAB-01": self.lab1,
            "LAB-02": self.lab2,
            "LAB-03": self.lab3,
            "LAB-04": self.lab4,
        }
        self.routes = [
            CourierRoute("LAB-01", "LAB-03", time(16, 0), time(16, 30), 50),
            CourierRoute("LAB-01", "LAB-04", time(17, 0), time(17, 30), 75),
        ]
        self.router = LabRouter(self.labs, self.routes)

    def test_ec03_courier_cutoff_exact_time(self):
        """EC-03: Collected at exactly cut-off time (16:00:00) departs on the same day's 16:30 courier."""
        collected = datetime(2026, 10, 7, 16, 0, 0)
        dep, arr = self.router.get_courier_departure_and_arrival("LAB-01", "LAB-03", collected)
        self.assertEqual(dep, datetime(2026, 10, 7, 16, 30, 0))
        self.assertEqual(arr, datetime(2026, 10, 7, 17, 20, 0))

    def test_courier_cutoff_one_minute_late(self):
        """Trap 1: Collected 1 min after cut-off (16:01:00) departs next day."""
        collected = datetime(2026, 10, 7, 16, 1, 0)
        dep, arr = self.router.get_courier_departure_and_arrival("LAB-01", "LAB-03", collected)
        self.assertEqual(dep, datetime(2026, 10, 8, 16, 30, 0))
        self.assertEqual(arr, datetime(2026, 10, 8, 17, 20, 0))

    def test_ec05_sample_received_one_minute_before_closing(self):
        """
        EC-05: Sample reaches at 20:59, 1 minute before 21:00 close.
        It is RECEIVED immediately, not postponed to next opening.
        """
        dt = datetime(2026, 10, 9, 20, 59, 0)
        effective_received = get_next_opening_time(dt, self.lab2)
        self.assertEqual(effective_received, dt)

    def test_sample_received_after_closing_opens_next_morning(self):
        """Sample arriving outside operating hours is received next morning at opening."""
        dt = datetime(2026, 10, 9, 21, 5, 0)
        effective_received = get_next_opening_time(dt, self.lab2)
        self.assertEqual(effective_received, datetime(2026, 10, 10, 7, 0, 0))

    def test_capacity_overflow_routing(self):
        """When local lab capacity is reached, test overflows to LAB-03 with reason CAPACITY_OVERFLOW."""
        order = Order(
            order_id="ORD-CAP-1",
            patient_name="P1",
            age=30,
            gender="M",
            order_ts=datetime(2026, 10, 13, 8, 0, 0),
            priority=Priority.ROUTINE,
            collection_lab_id="LAB-02",
            home_collection=False,
            slot_start=datetime(2026, 10, 13, 8, 30, 0),
        )
        urine_test = TestMaster(
            test_code="TST-URINE",
            test_name="Urine Routine",
            sample_type=SampleType.URINE,
            tube_type=TubeType.URINE_CUP,
            fasting_hours=0,
            std_tat_hours=4,
            lab_tier=LabTier.L1,
            price=Decimal("150.00"),
        )
        # LAB-02 capacity for URINE is 1
        lab_routed, reason = self.router.route_test(order, urine_test, "2026-10-13")
        self.assertEqual(lab_routed, "LAB-02")
        self.assertEqual(reason, RoutingReason.LOCAL)

        # Second test on same day should overflow!
        lab_routed2, reason2 = self.router.route_test(order, urine_test, "2026-10-13")
        self.assertEqual(lab_routed2, "LAB-03")
        self.assertEqual(reason2, RoutingReason.CAPACITY_OVERFLOW)


if __name__ == "__main__":
    unittest.main()
