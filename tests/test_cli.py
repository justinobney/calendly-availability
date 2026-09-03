from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from calendly_availability import cli as MODULE

def event(name: str, slug: str, duration: int) -> MODULE.EventType:
    return MODULE.EventType(
        name=name,
        slug=slug,
        uuid=slug,
        duration_minutes=duration,
        timezone="America/Chicago",
        color="#326f93",
        description="",
        booking_url=f"https://calendly.com/example/{slug}",
    )


class AvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        zone = ZoneInfo("America/Chicago")
        short = event("Quick call", "quick", 10)
        long = event("Working session", "working", 60)
        first = datetime(2026, 9, 9, 9, 0, tzinfo=zone)
        self.slots = [
            MODULE.Slot(short, first, first + timedelta(minutes=10), 1, "https://example.test/quick-9"),
            MODULE.Slot(short, first + timedelta(minutes=15), first + timedelta(minutes=25), 1, "https://example.test/quick-915"),
            MODULE.Slot(long, first + timedelta(minutes=15), first + timedelta(minutes=75), 1, "https://example.test/working-915"),
            MODULE.Slot(short, first + timedelta(hours=2), first + timedelta(hours=2, minutes=10), 1, "https://example.test/quick-11"),
        ]
        self.zone = zone

    def test_unifies_overlapping_event_types_without_duplicate_blocks(self) -> None:
        windows = MODULE.unified_windows(self.slots, self.zone)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["start"], "2026-09-09T09:00:00-05:00")
        self.assertEqual(windows[0]["end"], "2026-09-09T10:15:00-05:00")
        self.assertEqual(windows[0]["event_slugs"], ["quick", "working"])

    def test_payload_preserves_choices_at_each_exact_start(self) -> None:
        payload = MODULE.availability_payload("example", "Example Person", self.slots, self.zone, "test")
        self.assertEqual(payload["stats"], {
            "exact_slots": 4,
            "unique_starts": 3,
            "event_types": 2,
            "available_days": 1,
        })
        self.assertEqual(len(payload["starts"][1]["choices"]), 2)

    def test_overlay_accepts_optional_titles_and_rejects_reverse_ranges(self) -> None:
        overlay = MODULE.normalize_overlay({
            "label": "My calendar",
            "timezone": "America/Chicago",
            "busy": [{"title": "Project review", "start": "2026-09-09T09:30:00-05:00", "end": "2026-09-09T10:00:00-05:00"}],
        })
        self.assertEqual(overlay["busy"][0]["start"], "2026-09-09T09:30:00-05:00")
        self.assertEqual(overlay["busy"][0]["title"], "Project review")
        with self.assertRaisesRegex(MODULE.CalendlyError, "after start"):
            MODULE.normalize_overlay({
                "busy": [{"start": "2026-09-09T10:00:00-05:00", "end": "2026-09-09T09:30:00-05:00"}],
            })

    def test_local_api_supports_health_head_and_overlay_updates(self) -> None:
        payload = MODULE.availability_payload("example", "Example Person", self.slots, self.zone, "test")
        state = MODULE.CalendarServerState(payload)
        server_ref = {"server": None}
        server = MODULE.http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            MODULE.calendar_handler(state, server_ref),
        )
        server_ref["server"] = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/api/health") as response:
                self.assertEqual(json.load(response), {"ok": True})
            head = urllib.request.Request(f"{base}/", method="HEAD")
            with urllib.request.urlopen(head) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"")
                self.assertEqual(response.headers.get_content_type(), "text/html")
            result = MODULE.push_overlay(base, {
                "label": "Live overlay",
                "timezone": "America/Chicago",
                "busy": [{"title": "Design review", "start": "2026-09-09T09:30:00-05:00", "end": "2026-09-09T10:00:00-05:00"}],
            })
            self.assertTrue(result["ok"])
            self.assertEqual(state.snapshot()["overlay"]["label"], "Live overlay")
            self.assertEqual(state.snapshot()["overlay"]["busy"][0]["title"], "Design review")
            with self.assertRaisesRegex(MODULE.CalendlyError, "loopback"):
                MODULE.overlay_endpoint("https://example.com")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_active_server_discovery_uses_a_private_runtime_file(self) -> None:
        original_path = MODULE.DISCOVERY_PATH
        with tempfile.TemporaryDirectory() as directory:
            MODULE.DISCOVERY_PATH = Path(directory) / "active-server.json"
            try:
                url = "http://127.0.0.1:54321/"
                MODULE.write_server_discovery(url, "example")
                self.assertEqual(MODULE.resolve_server_url(None), url)
                self.assertEqual(MODULE.DISCOVERY_PATH.stat().st_mode & 0o777, 0o600)
                MODULE.remove_server_discovery(url)
                self.assertFalse(MODULE.DISCOVERY_PATH.exists())
            finally:
                MODULE.DISCOVERY_PATH = original_path

    def test_server_is_reachable_before_background_collection_finishes(self) -> None:
        original_path = MODULE.DISCOVERY_PATH
        payload = MODULE.availability_payload("example", "Example Person", self.slots, self.zone, "test")
        collection_started = threading.Event()
        release_collection = threading.Event()

        def loader():
            collection_started.set()
            release_collection.wait(timeout=3)
            return payload

        with tempfile.TemporaryDirectory() as directory:
            MODULE.DISCOVERY_PATH = Path(directory) / "active-server.json"
            server_thread = threading.Thread(
                target=MODULE.serve_calendar,
                kwargs={
                    "profile": "example",
                    "availability": None,
                    "timezone_name": "America/Chicago",
                    "overlay": MODULE.normalize_overlay({"timezone": "America/Chicago", "busy": []}),
                    "port": 0,
                    "open_browser": False,
                    "loader": loader,
                },
                daemon=True,
            )
            server_thread.start()
            url = None
            try:
                self.assertTrue(collection_started.wait(timeout=2))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if MODULE.DISCOVERY_PATH.exists():
                        url = MODULE.resolve_server_url(None)
                        try:
                            with urllib.request.urlopen(f"{url}api/state") as response:
                                state = json.load(response)
                            break
                        except urllib.error.URLError:
                            pass
                    time.sleep(0.02)
                else:
                    self.fail("Local server was not reachable while collection was pending")
                self.assertEqual(state["status"], "loading")
                self.assertIsNone(state["availability"])

                release_collection.set()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    with urllib.request.urlopen(f"{url}api/state") as response:
                        state = json.load(response)
                    if state["status"] == "ready":
                        break
                    time.sleep(0.02)
                self.assertEqual(state["status"], "ready")
                self.assertEqual(state["availability"]["stats"]["exact_slots"], 4)
            finally:
                release_collection.set()
                if url:
                    try:
                        request = urllib.request.Request(f"{url}api/done", data=b"", method="POST")
                        urllib.request.urlopen(request, timeout=2).close()
                    except urllib.error.URLError:
                        pass
                server_thread.join(timeout=3)
                MODULE.DISCOVERY_PATH = original_path
            self.assertFalse((Path(directory) / "active-server.json").exists())


if __name__ == "__main__":
    unittest.main()
