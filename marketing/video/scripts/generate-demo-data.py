#!/usr/bin/env python3
"""Generate deterministic, synthetic Calendly slots for marketing captures."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "public" / "demo" / "demo-slots.csv"
ZONE = "America/Chicago"

EVENTS = {
    "quick-chat": ("Quick Chat", 15),
    "coffee-chat": ("Coffee Chat", 20),
    "advisor-call": ("Advisor Call", 25),
    "team-intro": ("Team Intro", 30),
    "working-session": ("Working Session", 45),
    "partner-session": ("Partner Session", 50),
    "deep-dive": ("Deep Dive", 60),
    "workshop": ("Workshop", 90),
}

WINDOWS = [
    ("2026-09-14", "08:00", "10:30", ("quick-chat", "coffee-chat", "team-intro")),
    ("2026-09-14", "11:00", "13:00", ("working-session",)),
    ("2026-09-14", "14:00", "16:30", ("deep-dive",)),
    ("2026-09-15", "08:30", "12:00", ("quick-chat", "advisor-call", "team-intro", "working-session")),
    ("2026-09-15", "13:30", "17:00", ("team-intro", "deep-dive")),
    ("2026-09-16", "09:00", "12:30", ("quick-chat", "working-session")),
    ("2026-09-16", "14:00", "17:00", ("team-intro", "partner-session", "deep-dive")),
    ("2026-09-17", "08:00", "17:00", tuple(EVENTS)),
    ("2026-09-18", "09:00", "12:00", ("quick-chat", "team-intro", "working-session")),
    ("2026-09-18", "13:00", "15:30", ("working-session", "deep-dive", "workshop")),
]


def local_time(day: str, clock: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}:00-05:00")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for day, window_start, window_end, event_slugs in WINDOWS:
        cursor = local_time(day, window_start)
        limit = local_time(day, window_end)
        while cursor < limit:
            for slug in event_slugs:
                name, duration = EVENTS[slug]
                end = cursor + timedelta(minutes=duration)
                if end > limit:
                    continue
                utc_stamp = cursor.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                rows.append(
                    {
                        "event_type": name,
                        "event_slug": slug,
                        "duration_minutes": duration,
                        "start": cursor.isoformat(),
                        "end": end.isoformat(),
                        "timezone": ZONE,
                        "invitees_remaining": 1,
                        "booking_url": f"https://calendly.com/demo-host/{slug}/{utc_stamp}",
                    }
                )
            cursor += timedelta(minutes=15)

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic slots to {OUTPUT}")


if __name__ == "__main__":
    main()
