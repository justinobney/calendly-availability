---
name: calendly-availability
description: Launch a unified local calendar for every public event type on a Calendly profile and optionally overlay the user's own calendar through an available calendar connector. Use when the user supplies a Calendly profile URL or asks to compare, inspect, or find bookable time across someone's Calendly links. Do not use to administer a Calendly account, create event types, or book a meeting without explicit confirmation.
---

# Calendly Availability

Use the installed `calendly-availability` CLI as the deterministic data and UI layer. Use the agent only to orchestrate the run and adapt an available calendar connector to the overlay contract.

## Start the unified calendar

1. Extract the public Calendly profile URL or slug from the request.
2. Use the user's requested range. Default to 45 days when they do not specify one.
3. Check for the CLI with `command -v calendly-availability`. If it is absent, locate a checked-out copy of this repository and use its virtual environment, or tell the user how to install it. Do not install remote code without permission.
4. Start `calendly-availability serve <profile> --days <days> --no-open` in a persistent terminal session. Do not wait for collection to finish before presenting the local page.
5. Read the emitted loopback URL and open it in the user's browser. Never expose the server on a non-loopback interface.
6. Poll `<url>/api/state` until `status` is `ready` or `error`. Report an error with its actual message. When ready, use `availability.range` as the authoritative range for any calendar query.

Do not reproduce Calendly's collection logic in the skill. The CLI discovers event types, fetches availability, merges duplicate starts, retains booking choices, and reports request counts.

## Add the user's calendar

Treat the calendar overlay as optional. If a suitable calendar connector is available and the user asked for an overlay:

1. Query the exact `availability.range`, including the end date, in the user's timezone.
2. Prefer seven-day chunks so calendar connectors with response-size or timeout limits remain reliable. Verify that each response is complete; do not silently accept truncation.
3. Keep only event title, start, and end. Do not send descriptions, attendees, locations, conferencing links, notes, or calendar credentials to the local server.
4. Deduplicate exact `(title, start, end)` triples.
5. Do not treat informational all-day events as busy unless the connector explicitly marks them busy or the user requests it. If semantics are unclear and the choice would materially change results, ask the user.
6. Build the JSON described in [references/overlay-contract.md](references/overlay-contract.md).
7. Write it to a temporary file with mode `0600`, run `calendly-availability overlay <file>`, and remove the file in a cleanup/finally step whether the push succeeds or fails. Never write real calendar data inside the repository.
8. Re-read `/api/state` and verify the overlay label and event count before saying the real calendar is present.

If no calendar connector is available, leave the Calendly calendar usable and state plainly that the personal overlay was skipped. Never substitute demo data or infer busy times.

## Help the user choose a time

- Let the browser handle duration filtering and exact conflict checks.
- When a start is covered by multiple event types, preserve the choice in the slide-out drawer rather than collapsing it to an arbitrary booking link.
- Opening a booking page is reversible; submitting a booking is an external action. Do not finalize a booking unless the user explicitly chooses the event type and confirms the time.
- For a text answer, read `/api/state` and distinguish the other person's availability from the user's calendar conflicts.

## Finish safely

Keep the server running while the user is working. When they say they are done, use the page's Done action or send `POST /api/done`, then confirm the loopback server stopped. Do not persist the overlay unless the user explicitly asks for an export.
