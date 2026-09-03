#!/usr/bin/env python3
"""Fetch public Calendly availability across every visible event type.

This uses the same unauthenticated JSON endpoints as Calendly's public booking
pages. They are not part of Calendly's supported public API and may change.

Examples:
    calendly-availability your-profile
    calendly-availability https://calendly.com/your-profile --days 30
    calendly-availability your-profile --event "45 Minute" --format json
    calendly-availability your-profile --days 45 --format csv --output /tmp/availability.csv
    calendly-availability your-profile --days 45 --format ics --output /tmp/availability.ics
    calendly-availability serve your-profile --data /tmp/availability.csv
    calendly-availability overlay /tmp/my-calendar.json --server http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.server
import importlib.resources
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


BASE_URL = "https://calendly.com"
USER_AGENT = "obney-calendly-availability/1.0"
MIN_REQUEST_INTERVAL = 0.4
ASSET_DIR = Path(str(importlib.resources.files("calendly_availability").joinpath("web")))
DISCOVERY_PATH = Path(tempfile.gettempdir()) / f"obney-calendly-availability-{os.getuid()}.json"
_request_lock = threading.Lock()
_last_request_at = 0.0


class CalendlyError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventType:
    name: str
    slug: str
    uuid: str
    duration_minutes: int
    timezone: str
    color: str
    description: str
    booking_url: str


@dataclass(frozen=True)
class Slot:
    event: EventType
    start: datetime
    end: datetime
    invitees_remaining: int | None
    booking_url: str


@dataclass(frozen=True)
class Window:
    event: EventType
    start: datetime
    end: datetime
    starts: tuple[datetime, ...]


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    command = "fetch"
    if argv and argv[0] in {"fetch", "serve", "overlay"}:
        command = argv.pop(0)

    if command == "overlay":
        parser = argparse.ArgumentParser(
            prog="calendly-availability overlay",
            description="Push a titled calendar overlay into a running local availability server.",
        )
        parser.add_argument(
            "input",
            nargs="?",
            default="-",
            help="Overlay JSON file, or - to read JSON from stdin (default: -)",
        )
        parser.add_argument(
            "--server",
            help="Local availability server URL (default: discover the active server)",
        )
        args = parser.parse_args(argv)
        args.command = command
        return args

    parser = argparse.ArgumentParser(
        prog=f"calendly-availability {command}" if command != "fetch" else "calendly-availability",
        description="Unify public availability across a Calendly profile's event types."
    )
    parser.add_argument(
        "profile",
        help="Calendly profile slug or URL, for example your-profile or https://calendly.com/your-profile",
    )
    parser.add_argument("--days", type=int, default=45, help="Days to fetch (default: 45)")
    parser.add_argument("--start", help="First date, YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--event",
        action="append",
        default=[],
        help="Include event names/slugs containing this text; repeat for more than one",
    )
    parser.add_argument(
        "--timezone",
        help="IANA timezone for output, for example America/Chicago (default: host timezone)",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv", "ics"),
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument("--output", type=Path, help="Write output to this file")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Maximum concurrent Calendly requests (default: 4)",
    )
    if command == "serve":
        parser.add_argument(
            "--data",
            type=Path,
            help="Load exact slots from an existing CSV instead of calling Calendly",
        )
        parser.add_argument(
            "--overlay",
            type=Path,
            help="Load a JSON busy-time overlay when the server starts",
        )
        parser.add_argument("--name", help="Display name for the calendar owner")
        parser.add_argument("--port", type=int, default=0, help="Loopback port (default: random)")
        parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    args = parser.parse_args(argv)
    args.command = command
    return args


def profile_slug(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        slug = value.strip("/").split("/")[0]
    else:
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc.lower() not in {"calendly.com", "www.calendly.com"}:
            raise CalendlyError("Profile URL must be on calendly.com")
        parts = [part for part in parsed.path.split("/") if part]
        slug = parts[0] if parts else ""
    if not slug:
        raise CalendlyError("Could not determine the Calendly profile slug")
    return slug


def get_json(path: str, params: dict[str, Any] | None = None, retries: int = 6) -> Any:
    global _last_request_at
    query = urllib.parse.urlencode(
        {key: str(value).lower() if isinstance(value, bool) else value for key, value in (params or {}).items() if value is not None}
    )
    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    for attempt in range(retries):
        with _request_lock:
            delay = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
            if delay > 0:
                time.sleep(delay)
            _last_request_at = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                raise CalendlyError(f"Calendly returned HTTP {exc.code} for {url}: {detail}") from exc
            retry_after = exc.headers.get("Retry-After")
            try:
                wait_seconds = float(retry_after) if retry_after else min(30, 2 ** (attempt + 1))
            except ValueError:
                wait_seconds = min(30, 2 ** (attempt + 1))
            time.sleep(wait_seconds)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise CalendlyError(f"Could not reach Calendly for {url}: {exc}") from exc
            time.sleep(min(30, 2 ** (attempt + 1)))
    raise AssertionError("unreachable")


def discover_events(slug: str, filters: list[str]) -> list[EventType]:
    summaries = get_json(f"/api/booking/profiles/{urllib.parse.quote(slug)}/event_types")
    if not isinstance(summaries, list):
        raise CalendlyError("Calendly returned an unexpected event-type response")

    wanted = [item.casefold() for item in filters]
    if wanted:
        summaries = [
            item
            for item in summaries
            if any(
                needle in f"{item.get('name', '')} {item.get('slug', '')}".casefold()
                for needle in wanted
            )
        ]
    if not summaries:
        raise CalendlyError("No visible event types matched")

    def lookup(summary: dict[str, Any]) -> EventType:
        detail = get_json(
            "/api/booking/event_types/lookup",
            {"event_type_slug": summary["slug"], "profile_slug": slug},
        )
        event_slug = detail["slug"]
        return EventType(
            name=detail["name"],
            slug=event_slug,
            uuid=detail["uuid"],
            duration_minutes=int(detail["duration"]),
            timezone=detail["availability_timezone"],
            color=detail.get("color") or summary.get("color") or "#006bff",
            description=detail.get("description") or summary.get("description") or "",
            booking_url=f"{BASE_URL}/{slug}/{event_slug}",
        )

    events: list[EventType] = []
    with ThreadPoolExecutor(max_workers=min(4, len(summaries))) as pool:
        futures = {pool.submit(lookup, item): item for item in summaries}
        for future in as_completed(futures):
            events.append(future.result())
    return sorted(events, key=lambda event: event.name.casefold())


def date_chunks(first: date, last: date, size: int = 7) -> Iterable[tuple[date, date]]:
    cursor = first
    while cursor <= last:
        chunk_end = min(last, cursor + timedelta(days=size - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def exact_booking_url(event: EventType, start: datetime) -> str:
    utc_start = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    local_date = start.date().isoformat()
    return (
        f"{event.booking_url}/{utc_start}"
        f"?month={local_date[:7]}&date={local_date}"
    )


def fetch_slots(event: EventType, first: date, last: date) -> list[Slot]:
    event_zone = ZoneInfo(event.timezone)
    slots: list[Slot] = []
    for chunk_start, chunk_end in date_chunks(first, last):
        range_start = datetime.combine(chunk_start, datetime_time.min, event_zone)
        range_end = datetime.combine(chunk_end, datetime_time.max, event_zone)
        data = get_json(
            f"/api/booking/event_types/{event.uuid}/calendar/range",
            {
                "timezone": event.timezone,
                "diagnostics": False,
                "range_start": range_start.isoformat(),
                "range_end": range_end.isoformat(),
            },
        )
        for day in data.get("days", []):
            for item in day.get("spots", []):
                if item.get("status") != "available":
                    continue
                start = datetime.fromisoformat(item["start_time"])
                slots.append(
                    Slot(
                        event=event,
                        start=start,
                        end=start + timedelta(minutes=event.duration_minutes),
                        invitees_remaining=item.get("invitees_remaining"),
                        booking_url=exact_booking_url(event, start),
                    )
                )
    unique = {(slot.event.slug, slot.start.isoformat()): slot for slot in slots}
    return sorted(unique.values(), key=lambda slot: slot.start)


def fetch_all_slots(events: list[EventType], first: date, last: date, workers: int) -> list[Slot]:
    slots: list[Slot] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(events)))) as pool:
        futures = {pool.submit(fetch_slots, event, first, last): event for event in events}
        for future in as_completed(futures):
            slots.extend(future.result())
    return sorted(slots, key=lambda slot: (slot.start, slot.event.name.casefold()))


EVENT_COLORS = (
    "#386f91",
    "#2e7d6e",
    "#8a6337",
    "#75578f",
    "#a04f5f",
    "#4f6e50",
    "#8a5550",
    "#526b8d",
)


def event_color(slug: str) -> str:
    digest = hashlib.sha256(slug.encode("utf-8")).digest()
    return EVENT_COLORS[digest[0] % len(EVENT_COLORS)]


def base_booking_url(exact_url: str, slug: str, profile: str) -> str:
    parsed = urllib.parse.urlsplit(exact_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and "T" in parts[-1]:
        parts.pop()
    path = "/" + "/".join(parts) if parts else f"/{profile}/{slug}"
    return urllib.parse.urlunsplit((parsed.scheme or "https", parsed.netloc or "calendly.com", path, "", ""))


def load_slots_csv(path: Path, profile: str, filters: list[str]) -> tuple[list[Slot], str]:
    if not path.is_file():
        raise CalendlyError(f"CSV snapshot does not exist: {path}")
    wanted = [item.casefold() for item in filters]
    slots: list[Slot] = []
    events: dict[str, EventType] = {}
    timezone_name = ""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"event_type", "event_slug", "duration_minutes", "start", "end", "booking_url"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise CalendlyError(f"CSV snapshot is missing required columns: {path}")
        for row in reader:
            haystack = f"{row['event_type']} {row['event_slug']}".casefold()
            if wanted and not any(needle in haystack for needle in wanted):
                continue
            event_slug = row["event_slug"]
            timezone_name = timezone_name or row.get("timezone") or "America/Chicago"
            event = events.get(event_slug)
            if event is None:
                event = EventType(
                    name=row["event_type"],
                    slug=event_slug,
                    uuid=event_slug,
                    duration_minutes=int(row["duration_minutes"]),
                    timezone=row.get("timezone") or timezone_name,
                    color=event_color(event_slug),
                    description="",
                    booking_url=base_booking_url(row["booking_url"], event_slug, profile),
                )
                events[event_slug] = event
            start = datetime.fromisoformat(row["start"])
            end = datetime.fromisoformat(row["end"])
            slots.append(
                Slot(
                    event=event,
                    start=start,
                    end=end,
                    invitees_remaining=int(row["invitees_remaining"]) if row.get("invitees_remaining") else None,
                    booking_url=row["booking_url"],
                )
            )
    if not slots:
        raise CalendlyError(f"CSV snapshot contains no matching slots: {path}")
    return sorted(slots, key=lambda slot: (slot.start, slot.event.name.casefold())), timezone_name


def unified_windows(slots: list[Slot], zone: ZoneInfo) -> list[dict[str, Any]]:
    starts_by_day: dict[date, dict[datetime, list[Slot]]] = {}
    for slot in slots:
        start = in_zone(slot.start, zone)
        starts_by_day.setdefault(start.date(), {}).setdefault(start, []).append(slot)

    gaps: list[timedelta] = []
    for starts in starts_by_day.values():
        ordered = sorted(starts)
        gaps.extend(later - earlier for earlier, later in zip(ordered, ordered[1:]))
    cadence = min((gap for gap in gaps if gap <= timedelta(minutes=30)), default=timedelta(minutes=15))

    result: list[dict[str, Any]] = []
    for day, grouped in sorted(starts_by_day.items()):
        ordered = sorted(grouped)
        current_starts = [ordered[0]]
        current_end = max(in_zone(slot.end, zone) for slot in grouped[ordered[0]])
        current_slugs = {slot.event.slug for slot in grouped[ordered[0]]}
        previous_start = ordered[0]
        for start in ordered[1:]:
            option_end = max(in_zone(slot.end, zone) for slot in grouped[start])
            if start <= max(current_end, previous_start + cadence):
                current_starts.append(start)
                current_end = max(current_end, option_end)
                current_slugs.update(slot.event.slug for slot in grouped[start])
            else:
                result.append(
                    {
                        "start": current_starts[0].isoformat(),
                        "end": current_end.isoformat(),
                        "starts": [item.isoformat() for item in current_starts],
                        "event_slugs": sorted(current_slugs),
                    }
                )
                current_starts = [start]
                current_end = option_end
                current_slugs = {slot.event.slug for slot in grouped[start]}
            previous_start = start
        result.append(
            {
                "start": current_starts[0].isoformat(),
                "end": current_end.isoformat(),
                "starts": [item.isoformat() for item in current_starts],
                "event_slugs": sorted(current_slugs),
            }
        )
    return result


def availability_payload(
    profile: str,
    display_name: str,
    slots: list[Slot],
    zone: ZoneInfo,
    source: str,
) -> dict[str, Any]:
    grouped: dict[datetime, list[Slot]] = {}
    for slot in slots:
        grouped.setdefault(in_zone(slot.start, zone), []).append(slot)
    starts = []
    for start, choices in sorted(grouped.items()):
        starts.append(
            {
                "start": start.isoformat(),
                "choices": [
                    {
                        "event_name": slot.event.name,
                        "event_slug": slot.event.slug,
                        "duration_minutes": slot.event.duration_minutes,
                        "end": in_zone(slot.end, zone).isoformat(),
                        "booking_url": slot.booking_url,
                    }
                    for slot in sorted(choices, key=lambda item: (item.event.duration_minutes, item.event.name))
                ],
            }
        )
    event_types = {
        slot.event.slug: {
            "name": slot.event.name,
            "slug": slot.event.slug,
            "duration_minutes": slot.event.duration_minutes,
            "color": slot.event.color,
            "booking_url": slot.event.booking_url,
        }
        for slot in slots
    }
    local_starts = [in_zone(slot.start, zone) for slot in slots]
    return {
        "owner": {"slug": profile, "name": display_name},
        "timezone": str(zone),
        "range": {
            "start": min(local_starts).date().isoformat(),
            "end": max(local_starts).date().isoformat(),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "stats": {
            "exact_slots": len(slots),
            "unique_starts": len(starts),
            "event_types": len(event_types),
            "available_days": len({value.date() for value in local_starts}),
        },
        "event_types": sorted(event_types.values(), key=lambda item: (item["duration_minutes"], item["name"])),
        "starts": starts,
        "segments": unified_windows(slots, zone),
    }


def normalize_overlay(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CalendlyError("Overlay must be a JSON object")
    timezone_name = str(data.get("timezone") or "America/Chicago")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise CalendlyError(f"Unknown overlay timezone: {timezone_name}") from exc
    raw_busy = data.get("busy", [])
    if not isinstance(raw_busy, list) or len(raw_busy) > 2000:
        raise CalendlyError("Overlay busy must be an array with at most 2000 entries")
    busy = []
    for item in raw_busy:
        if not isinstance(item, dict) or "start" not in item or "end" not in item:
            raise CalendlyError("Every busy entry needs start and end")
        start = datetime.fromisoformat(str(item["start"]))
        end = datetime.fromisoformat(str(item["end"]))
        if start.tzinfo is None:
            start = start.replace(tzinfo=zone)
        if end.tzinfo is None:
            end = end.replace(tzinfo=zone)
        if end <= start:
            raise CalendlyError("Overlay busy end must be after start")
        title = str(item.get("title") or "Busy").strip()[:200] or "Busy"
        busy.append({"start": start.isoformat(), "end": end.isoformat(), "title": title})
    return {
        "label": str(data.get("label") or "My calendar"),
        "timezone": timezone_name,
        "busy": sorted(busy, key=lambda item: item["start"]),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class CalendarServerState:
    def __init__(
        self,
        availability: dict[str, Any] | None,
        overlay: dict[str, Any] | None = None,
        timezone_name: str | None = None,
    ):
        self._lock = threading.Lock()
        self.availability = availability
        self.status = "ready" if availability else "loading"
        self.error: str | None = None
        self.timezone_name = availability["timezone"] if availability else (timezone_name or "UTC")
        self.overlay = self._align_overlay(
            overlay or normalize_overlay({"label": "My calendar", "timezone": self.timezone_name, "busy": []})
        )

    def _align_overlay(self, overlay: dict[str, Any]) -> dict[str, Any]:
        zone = ZoneInfo(self.timezone_name)
        return {
            **overlay,
            "display_timezone": str(zone),
            "busy": [
                {
                    "start": datetime.fromisoformat(item["start"]).astimezone(zone).isoformat(),
                    "end": datetime.fromisoformat(item["end"]).astimezone(zone).isoformat(),
                    "title": item.get("title") or "Busy",
                }
                for item in overlay["busy"]
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "availability": self.availability,
                "overlay": self.overlay,
                "error": self.error,
            }

    def replace_overlay(self, overlay: dict[str, Any]) -> None:
        with self._lock:
            self.overlay = self._align_overlay(overlay)

    def set_availability(self, availability: dict[str, Any]) -> None:
        with self._lock:
            self.availability = availability
            self.timezone_name = availability["timezone"]
            self.overlay = self._align_overlay(self.overlay)
            self.status = "ready"
            self.error = None

    def set_error(self, message: str) -> None:
        with self._lock:
            self.status = "error"
            self.error = message


def load_overlay(path: Path | None, timezone_name: str) -> dict[str, Any]:
    if path is None:
        return normalize_overlay({"label": "My calendar", "timezone": timezone_name, "busy": []})
    if not path.is_file():
        raise CalendlyError(f"Overlay file does not exist: {path}")
    return normalize_overlay(json.loads(path.read_text(encoding="utf-8")))


def overlay_endpoint(server_url: str) -> str:
    parsed = urllib.parse.urlsplit(server_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise CalendlyError("Overlay server must be an http:// loopback URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CalendlyError("Overlay server URL cannot contain credentials, a query, or a fragment")
    base_path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, f"{base_path}/api/overlay/me", "", ""))


def push_overlay(server_url: str, data: Any) -> dict[str, Any]:
    overlay = normalize_overlay(data)
    request = urllib.request.Request(
        overlay_endpoint(server_url),
        data=json.dumps(overlay, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise CalendlyError(f"Local calendar server returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CalendlyError(f"Could not reach the local calendar server: {exc}") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        raise CalendlyError("Local calendar server returned an unexpected response")
    return result


def read_overlay_input(value: str) -> Any:
    if value == "-":
        return json.load(sys.stdin)
    path = Path(value)
    if not path.is_file():
        raise CalendlyError(f"Overlay JSON file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_server_discovery(url: str, profile: str) -> None:
    payload = {
        "version": 1,
        "url": url,
        "pid": os.getpid(),
        "profile": profile,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = DISCOVERY_PATH.with_name(f"{DISCOVERY_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(DISCOVERY_PATH)


def remove_server_discovery(url: str) -> None:
    try:
        payload = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
        if payload.get("pid") == os.getpid() and payload.get("url") == url:
            DISCOVERY_PATH.unlink()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return


def resolve_server_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url
    try:
        payload = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
        url = payload["url"]
    except FileNotFoundError as exc:
        raise CalendlyError("No active local calendar server was found; start `calendly-availability serve` first") from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CalendlyError(f"Active-server discovery file is invalid: {DISCOVERY_PATH}") from exc
    return str(url)


def calendar_handler(state: CalendarServerState, server_ref: dict[str, http.server.ThreadingHTTPServer | None]):
    assets = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/app.css": ("app.css", "text/css; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "CalendlyAvailability/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            if os.environ.get("CALENDLY_AVAILABILITY_DEBUG"):
                super().log_message(format, *args)

        def send_content(self, status: int, body: bytes, content_type: str, *, include_body: bool = True) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def send_json(self, status: int, value: Any, *, include_body: bool = True) -> None:
            self.send_content(
                status,
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                include_body=include_body,
            )

        def serve_get(self, *, include_body: bool) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/state":
                self.send_json(200, state.snapshot(), include_body=include_body)
                return
            if path == "/api/health":
                self.send_json(200, {"ok": True}, include_body=include_body)
                return
            asset = assets.get(path)
            if asset:
                filename, content_type = asset
                asset_path = ASSET_DIR / filename
                if not asset_path.is_file():
                    self.send_json(500, {"error": f"Missing UI asset: {filename}"}, include_body=include_body)
                    return
                self.send_content(200, asset_path.read_bytes(), content_type, include_body=include_body)
                return
            self.send_json(404, {"error": "Not found"}, include_body=include_body)

        def do_GET(self) -> None:
            self.serve_get(include_body=True)

        def do_HEAD(self) -> None:
            self.serve_get(include_body=False)

        def do_POST(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/done":
                self.send_json(200, {"ok": True})
                server = server_ref.get("server")
                if server:
                    threading.Thread(target=server.shutdown, daemon=True).start()
                return
            if path != "/api/overlay/me":
                self.send_json(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 1_000_000:
                    raise CalendlyError("Overlay body must be between 1 byte and 1 MB")
                overlay = normalize_overlay(json.loads(self.rfile.read(length)))
                state.replace_overlay(overlay)
                self.send_json(200, {"ok": True, "overlay": overlay})
            except (CalendlyError, ValueError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})

    return Handler


def serve_calendar(
    profile: str,
    availability: dict[str, Any] | None,
    timezone_name: str,
    overlay: dict[str, Any],
    port: int,
    open_browser: bool,
    loader: Callable[[], dict[str, Any]] | None = None,
) -> int:
    missing_assets = [name for name in ("index.html", "app.css", "app.js") if not (ASSET_DIR / name).is_file()]
    if missing_assets:
        raise CalendlyError(f"Missing calendar UI assets: {', '.join(missing_assets)}")
    state = CalendarServerState(availability, overlay, timezone_name)
    server_ref: dict[str, http.server.ThreadingHTTPServer | None] = {"server": None}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), calendar_handler(state, server_ref))
    server_ref["server"] = server
    url = f"http://127.0.0.1:{server.server_port}/"
    write_server_discovery(url, profile)
    print(f"Calendly availability server: {url}", file=sys.stderr)
    print("Press Ctrl-C or use Done in the browser to stop.", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    if loader:
        def populate() -> None:
            try:
                state.set_availability(loader())
            except Exception as exc:
                state.set_error(str(exc))

        threading.Thread(target=populate, name="calendly-collector", daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nStopping server.", file=sys.stderr)
    finally:
        server.server_close()
        remove_server_discovery(url)
    return 0


def in_zone(value: datetime, zone: ZoneInfo) -> datetime:
    return value.astimezone(zone)


def availability_windows(slots: list[Slot], zone: ZoneInfo) -> list[Window]:
    cadence_by_event: dict[str, timedelta] = {}
    for event_slug in {slot.event.slug for slot in slots}:
        event_slots = sorted(
            (slot for slot in slots if slot.event.slug == event_slug),
            key=lambda slot: slot.start,
        )
        gaps = [
            later.start - earlier.start
            for earlier, later in zip(event_slots, event_slots[1:])
            if in_zone(earlier.start, zone).date() == in_zone(later.start, zone).date()
        ]
        short_gaps = [gap for gap in gaps if gap <= timedelta(minutes=30)]
        cadence_by_event[event_slug] = min(short_gaps, default=timedelta(0))

    grouped: dict[tuple[str, date], list[Slot]] = {}
    for slot in slots:
        local_start = in_zone(slot.start, zone)
        grouped.setdefault((slot.event.slug, local_start.date()), []).append(slot)

    windows: list[Window] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda slot: slot.start)
        current = [ordered[0]]
        for slot in ordered[1:]:
            previous = current[-1]
            # Calendly often offers short meetings on a 15-minute grid, leaving
            # a tiny gap between choices. Treat that grid as one readable window.
            cadence_end = previous.start + cadence_by_event[slot.event.slug]
            if slot.start <= max(previous.end, cadence_end):
                current.append(slot)
            else:
                windows.append(
                    Window(
                        event=current[0].event,
                        start=current[0].start,
                        end=current[-1].end,
                        starts=tuple(item.start for item in current),
                    )
                )
                current = [slot]
        windows.append(
            Window(
                event=current[0].event,
                start=current[0].start,
                end=current[-1].end,
                starts=tuple(item.start for item in current),
            )
        )
    return sorted(windows, key=lambda window: (window.start, window.event.name.casefold()))


def table_output(slots: list[Slot], zone: ZoneInfo) -> str:
    windows = availability_windows(slots, zone)
    if not windows:
        return "No availability found.\n"

    rows: list[tuple[str, str, str, str, str]] = []
    for window in windows:
        start = in_zone(window.start, zone)
        end = in_zone(window.end, zone)
        rows.append(
            (
                start.strftime("%a %b %-d"),
                f"{start.strftime('%-I:%M%p').lower()}–{end.strftime('%-I:%M%p').lower()}",
                f"{window.event.duration_minutes}m",
                str(len(window.starts)),
                window.event.name,
            )
        )
    headers = ("Date", "Available window", "Length", "Starts", "Event type")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    line = "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
    divider = "  ".join("-" * width for width in widths)
    body = ["  ".join(row[i].ljust(widths[i]) for i in range(len(headers))) for row in rows]
    return "\n".join([line, divider, *body]) + "\n"


def json_output(slug: str, first: date, last: date, slots: list[Slot], zone: ZoneInfo) -> str:
    payload = {
        "profile": slug,
        "range": {"start": first.isoformat(), "end": last.isoformat()},
        "timezone": str(zone),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "slots": [
            {
                "event_type": slot.event.name,
                "event_slug": slot.event.slug,
                "duration_minutes": slot.event.duration_minutes,
                "start": in_zone(slot.start, zone).isoformat(),
                "end": in_zone(slot.end, zone).isoformat(),
                "invitees_remaining": slot.invitees_remaining,
                "booking_url": slot.booking_url,
            }
            for slot in slots
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def csv_output(slots: list[Slot], zone: ZoneInfo) -> str:
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        ("event_type", "event_slug", "duration_minutes", "start", "end", "timezone", "invitees_remaining", "booking_url")
    )
    for slot in slots:
        writer.writerow(
            (
                slot.event.name,
                slot.event.slug,
                slot.event.duration_minutes,
                in_zone(slot.start, zone).isoformat(),
                in_zone(slot.end, zone).isoformat(),
                str(zone),
                "" if slot.invitees_remaining is None else slot.invitees_remaining,
                slot.booking_url,
            )
        )
    return output.getvalue()


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_ics(line: str) -> list[str]:
    # RFC 5545 limits content lines to 75 octets. This keeps the common ASCII
    # case compliant and avoids splitting UTF-8 continuation bytes.
    parts: list[str] = []
    current = ""
    limit = 75
    for char in line:
        proposed = current + char
        if len(proposed.encode("utf-8")) > limit:
            parts.append(current)
            current = " " + char
            limit = 75
        else:
            current = proposed
    parts.append(current)
    return parts


def ics_output(slots: list[Slot], zone: ZoneInfo) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//obney.ai//Calendly Availability//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Calendly Availability",
    ]
    for window in availability_windows(slots, zone):
        local_start = in_zone(window.start, zone)
        local_end = in_zone(window.end, zone)
        identity = f"{window.event.uuid}|{window.start.isoformat()}|{window.end.isoformat()}"
        uid = hashlib.sha256(identity.encode()).hexdigest()[:24] + "@obney.ai"
        cadence = "one selectable start" if len(window.starts) == 1 else f"{len(window.starts)} selectable start times"
        description = (
            f"{window.event.duration_minutes}-minute Calendly event with {cadence}. "
            f"Open the booking page to choose an exact start."
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now}",
                f"DTSTART:{local_start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{local_end.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"SUMMARY:{ics_escape('Available: ' + window.event.name)}",
                f"DESCRIPTION:{ics_escape(description)}",
                f"URL:{window.event.booking_url}",
                "STATUS:TENTATIVE",
                "TRANSP:TRANSPARENT",
                f"CATEGORIES:{ics_escape('Calendly Availability')}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in fold_ics(line)) + "\r\n"


def output_text(args: argparse.Namespace, slug: str, first: date, last: date, slots: list[Slot], zone: ZoneInfo) -> str:
    if args.format == "json":
        return json_output(slug, first, last, slots, zone)
    if args.format == "csv":
        return csv_output(slots, zone)
    if args.format == "ics":
        return ics_output(slots, zone)
    return table_output(slots, zone)


def main() -> int:
    args = parse_args()
    try:
        if args.command == "overlay":
            result = push_overlay(resolve_server_url(args.server), read_overlay_input(args.input))
            overlay = result["overlay"]
            print(f"Updated {overlay['label']}: {len(overlay['busy'])} calendar events")
            return 0

        if args.days < 1 or args.days > 366:
            raise CalendlyError("--days must be between 1 and 366")
        if args.workers < 1 or args.workers > 16:
            raise CalendlyError("--workers must be between 1 and 16")

        slug = profile_slug(args.profile)
        data_path = getattr(args, "data", None)
        if args.command == "serve" and not data_path:
            initial_timezone = args.timezone or "UTC"
            try:
                ZoneInfo(initial_timezone)
            except ZoneInfoNotFoundError as exc:
                raise CalendlyError(f"Unknown timezone: {initial_timezone}") from exc
            overlay = load_overlay(getattr(args, "overlay", None), initial_timezone)
            display_name = getattr(args, "name", None) or slug

            def load_live_availability() -> dict[str, Any]:
                events = discover_events(slug, args.event)
                zone_name = args.timezone or events[0].timezone
                try:
                    zone = ZoneInfo(zone_name)
                except ZoneInfoNotFoundError as exc:
                    raise CalendlyError(f"Unknown timezone: {zone_name}") from exc
                first = date.fromisoformat(args.start) if args.start else datetime.now(zone).date()
                last = first + timedelta(days=args.days - 1)
                slots = fetch_all_slots(events, first, last, args.workers)
                if not slots:
                    raise CalendlyError(f"No availability found between {first} and {last}")
                return availability_payload(slug, display_name, slots, zone, f"calendly:{slug}")

            return serve_calendar(
                profile=slug,
                availability=None,
                timezone_name=initial_timezone,
                overlay=overlay,
                port=args.port,
                open_browser=not args.no_open,
                loader=load_live_availability,
            )

        if args.command == "serve" and data_path:
            slots, detected_timezone = load_slots_csv(data_path, slug, args.event)
            zone_name = args.timezone or detected_timezone
            source = f"csv:{data_path.resolve()}"
        else:
            events = discover_events(slug, args.event)
            zone_name = args.timezone or events[0].timezone
            slots = []
            source = f"calendly:{slug}"
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError as exc:
            raise CalendlyError(f"Unknown timezone: {zone_name}") from exc

        first = date.fromisoformat(args.start) if args.start else datetime.now(zone).date()
        last = first + timedelta(days=args.days - 1)
        if not slots:
            slots = fetch_all_slots(events, first, last, args.workers)
        else:
            slots = [
                slot
                for slot in slots
                if first <= in_zone(slot.start, zone).date() <= last
            ]
            if not slots:
                raise CalendlyError(f"CSV snapshot has no slots between {first} and {last}")

        if args.command == "serve":
            overlay = load_overlay(getattr(args, "overlay", None), str(zone))
            display_name = getattr(args, "name", None) or slug
            return serve_calendar(
                profile=slug,
                availability=availability_payload(slug, display_name, slots, zone, source),
                timezone_name=str(zone),
                overlay=overlay,
                port=args.port,
                open_browser=not args.no_open,
            )

        rendered = output_text(args, slug, first, last, slots, zone)

        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
            print(
                f"Wrote {len(slots)} exact slots across {len(events)} event types "
                f"to {args.output}",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(rendered)
        return 0
    except (CalendlyError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
