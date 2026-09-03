# Calendar overlay contract

The local server accepts one JSON object with this shape:

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

## Field rules

- `label`: Human-readable source label. Use the calendar or account name when known.
- `timezone`: Valid IANA timezone name for interpreting timestamps without offsets.
- `busy`: At most 2,000 events.
- `title`: Optional, non-empty string. The server substitutes `Busy` and limits it to 200 characters.
- `start` and `end`: ISO 8601 date-times. Include an explicit UTC offset whenever the connector supplies one. `end` must be later than `start`.

The overlay endpoint normalizes times to the availability calendar's display timezone. Exact conflict checks use the selected Calendly event type's duration.

## Privacy boundary

Only title and temporal bounds belong in this payload. Exclude event IDs, descriptions, attendees, email addresses, locations, conferencing URLs, organizer details, notes, recurrence data, and provider tokens.

Use the host's temporary-directory mechanism to create a unique file outside the repository, restrict it to mode `0600`, and remove it in a cleanup/finally step whether the push succeeds or fails.

Do not use a committed example payload as evidence that a live calendar was loaded. After pushing, verify the returned count and the overlay stored at `/api/state`.
