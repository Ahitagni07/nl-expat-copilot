from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
CALENDAR_DIR = DATA_DIR / 'calendar'

def _ics_escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace(',', '\\,').replace(';', '\\;')

def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed

def _utc_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def create_calendar_artifact(title: str, start: str, end: str, location: str | None = None, notes: str | None = None) -> dict[str, str | None]:
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)
    if end_dt <= start_dt:
        raise ValueError('Calendar event end time must be after start time.')

    event_id = uuid4().hex
    path = CALENDAR_DIR / f'{event_id}.ics'
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Handle It//Life Admin Agent//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'BEGIN:VEVENT',
        f'UID:{event_id}@handle-it.local',
        f'DTSTAMP:{_utc_stamp(datetime.now(timezone.utc))}',
        f'DTSTART:{_utc_stamp(start_dt)}', f'DTEND:{_utc_stamp(end_dt)}',
        f'SUMMARY:{_ics_escape(title)}',
    ]
    if location:
        lines.append(f'LOCATION:{_ics_escape(location)}')
    if notes:
        lines.append(f'DESCRIPTION:{_ics_escape(notes)}')
    lines += ['END:VEVENT', 'END:VCALENDAR', '']
    path.write_text('\r\n'.join(lines), encoding='utf-8')

    query = {'action': 'TEMPLATE', 'text': title, 'dates': f'{_utc_stamp(start_dt)}/{_utc_stamp(end_dt)}'}
    if location:
        query['location'] = location
    if notes:
        query['details'] = notes

    return {
        'event_id': event_id, 'title': title,
        'start': start_dt.isoformat(), 'end': end_dt.isoformat(),
        'location': location, 'notes': notes,
        'ics_url': f'/api/calendar/{event_id}.ics',
        'google_calendar_url': 'https://calendar.google.com/calendar/render?' + urlencode(query),
    }
