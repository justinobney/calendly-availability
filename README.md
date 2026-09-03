# Calendly unified availability

A dependency-free Python CLI that turns every public event type on a Calendly profile into one local weekly calendar. You see a person's actual availability once, click a time, and only then choose among the booking links that support that start.

Your own calendar can be overlaid through a small local JSON interface. Event titles, exact-duration conflict checks, and meeting-length filtering stay in the browser on your machine.

> This project uses the same unauthenticated JSON endpoints as Calendly's public booking pages. They are not a supported public Calendly API and may change.

## What it does

- Discovers all visible event types on a public Calendly profile.
- Fetches 30 to 45 days, or any requested range up to one year.
- Merges duplicate starts into continuous availability regions.
- Preserves every exact booking URL behind each start time.
- Starts a loopback server before live collection and populates the UI asynchronously.
- Accepts a titled overlay from any calendar-aware agent.
- Filters the booking drawer by the desired meeting length.
- Calculates conflicts using each booking link's actual duration.
- Exports exact data as JSON or CSV and readable windows as iCalendar.

## Requirements

- Python 3.9 or newer
- No runtime dependencies

## Install for development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Start the local calendar

```bash
calendly-availability serve https://calendly.com/your-profile --days 45
```

The server binds to `127.0.0.1` on a random free port and opens the browser immediately. The page reports completed request counts while collection runs, then records the final logical-request and retry totals in the populated calendar. Use **Done** in the browser or `Ctrl-C` to stop it.

For a stable port:

```bash
calendly-availability serve your-profile --days 45 --port 8765
```

## Overlay your calendar

An agent with calendar access should query the same date range and create this minimal shape:

```json
{
  "label": "My calendar",
  "timezone": "America/Chicago",
  "busy": [
    {
      "title": "Client check-in",
      "start": "2026-09-09T12:45:00-05:00",
      "end": "2026-09-09T13:45:00-05:00"
    }
  ]
}
```

Then push it into the active session:

```bash
calendly-availability overlay /tmp/my-calendar.json
```

The server publishes its URL in a private temporary discovery file, so the overlay command does not need a port. It refuses non-loopback destinations, and the browser notices changes within two seconds.

See [`examples/calendar-overlay.json`](examples/calendar-overlay.json) for a demo payload. Do not commit real calendar exports.

## Data commands

```bash
# Readable availability windows
calendly-availability your-profile --days 45

# Every exact start and booking URL
calendly-availability your-profile --days 45 --format csv --output availability.csv

# Calendar subscription/import format
calendly-availability your-profile --days 45 --format ics --output availability.ics

# Serve an existing exact-slot CSV without calling Calendly
calendly-availability serve your-profile --data availability.csv
```

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check src/calendly_availability/web/app.js
```

The suite covers merged availability, exact-start choices, titled overlays, loopback enforcement, runtime discovery, HTTP behavior, and the server-first loading lifecycle.

GitHub Actions runs the same checks on Python 3.9, 3.11, and 3.13 for every push and pull request.

## Privacy and security

- The HTTP server listens only on the IPv4 loopback address.
- Overlay pushes are restricted to loopback URLs.
- Runtime discovery files are created with `0600` permissions and removed on shutdown.
- Calendar descriptions, attendees, locations, and conferencing links are never required.
- Real calendar and availability exports are ignored by Git.

## Project status

This is an alpha built around public Calendly behavior. Before publishing broadly, choose an open-source license and add a remote repository URL.
