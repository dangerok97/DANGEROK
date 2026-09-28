"""The day tapped in Home must be the day saved, even at a DST boundary."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "home_manual_event", Path(__file__).resolve().parents[1] / "home" / "manual_event.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
home_event_times = module.home_event_times


class HomeEventTimesTest(unittest.TestCase):
    def test_local_date_and_duration(self):
        start, end = home_event_times("2026-09-28", "09:30", "Europe/Rome")
        self.assertEqual(start, "2026-09-28T09:30:00+02:00")
        self.assertEqual(end, "2026-09-28T10:30:00+02:00")

    def test_clock_jump_rejects_missing_hour(self):
        with self.assertRaises(ValueError):
            home_event_times("2026-03-29", "02:30", "Europe/Rome")

    def test_duration_crosses_autumn_clock_change(self):
        start, end = home_event_times("2026-10-25", "02:30", "Europe/Rome")
        self.assertEqual(start, "2026-10-25T02:30:00+02:00")
        self.assertEqual(end, "2026-10-25T02:30:00+01:00")

    def test_invalid_day_and_time(self):
        for day, clock in [("2026-02-30", "10:00"), ("2026-09-28", "25:00"), ("2026-09-28", "9:30")]:
            with self.assertRaises(ValueError):
                home_event_times(day, clock, "Europe/Rome")


if __name__ == "__main__":
    unittest.main()
