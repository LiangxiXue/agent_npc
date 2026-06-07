"""Tests for deterministic major event detection."""

import unittest

from src.agent.major_events import detect_major_events


class MajorEventsTest(unittest.TestCase):
    def test_relationship_tone_change_does_not_crash_detection(self) -> None:
        events = detect_major_events(
            round_num=1,
            traveler_tick={
                "relationship_changes": [
                    {
                        "npc_id": "ron",
                        "field": "last_tone",
                        "before": "neutral",
                        "after": "friendly",
                    },
                    {
                        "npc_id": "ron",
                        "field": "trust",
                        "before": 0.0,
                        "after": 0.05,
                    },
                ]
            },
            min_severity="minor",
        )

        self.assertIsInstance(events, list)


if __name__ == "__main__":
    unittest.main()
