from dateparser import parse as parse_date
from datetime import datetime
from googleapiclient.discovery import build
from functools import wraps
import os
from flask import redirect, url_for
import pickle

TOKEN_PICKLE = 'token.pickle'

def resolve_relative_date(text, base_datetime=None):
    """
    Parses natural language date/time expressions like 'next Friday at 2pm'
    and returns a tuple (YYYY-MM-DD, HH:MM). Returns (None, None) if parsing fails.

    Args:
        text (str): Natural language input.
        base_datetime (datetime, optional): Base datetime to resolve from. Defaults to now.

    Returns:
        tuple: (resolved_date: str, resolved_time: str)
    """
    base = base_datetime or datetime.now()
    dt = parse_date(text, settings={'RELATIVE_BASE': base})
    if dt:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    return None, None

def login_required(f):
    """
    Decorator that redirects the user to the Google OAuth flow if they aren't authenticated.

    Args:
        f (function): The Flask view function being protected.

    Returns:
        function: Wrapped view function.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not os.path.exists(TOKEN_PICKLE):
            return redirect(url_for("authorize"))
        return f(*args, **kwargs)
    return decorated_function

def has_calendar_conflict(date, start_time, end_time):
    """
    Checks if the user has any events that overlap with the given time window.

    Args:
        date (str): The date in YYYY-MM-DD format.
        start_time (str): Start time in HH:MM (24h) format.
        end_time (str): End time in HH:MM (24h) format.

    Returns:
        bool: True if there is a conflict, False otherwise.
    """
    if not os.path.exists(TOKEN_PICKLE):
        return False
    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

        service = build('calendar', 'v3', credentials=credentials)

        start = f"{date}T{start_time}:00-07:00"
        end = f"{date}T{end_time}:00-07:00"

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return len(events) > 0

    except Exception as e:
        print(f"Error checking conflicts: {e}")
        return False

def add_to_my_calendar(title, date, start_time, end_time, location=None, notes=None, recurrence=None):
    """
    Creates a new event on the user's primary Google Calendar.

    Args:
        title (str): Event title.
        date (str): Event date (YYYY-MM-DD).
        start_time (str): Event start time (HH:MM, 24h).
        end_time (str): Event end time (HH:MM, 24h).
        location (str, optional): Location of the event.
        notes (str, optional): Description/notes.
        recurrence (str, optional): Recurrence rule (RRULE format).

    Returns:
        str: Link to the created event or error string.
    """
    if not os.path.exists(TOKEN_PICKLE):
        return "Authorization required"

    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

        service = build('calendar', 'v3', credentials=credentials)

        start = f"{date}T{start_time}:00-07:00"
        end = f"{date}T{end_time}:00-07:00"

        new_event = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": end, "timeZone": "America/Los_Angeles"},
            "location": location,
            "description": notes,
        }

        if recurrence:
            new_event["recurrence"] = [recurrence]

        new_event = {k: v for k, v in new_event.items() if v is not None}

        result = service.events().insert(calendarId="primary", body=new_event).execute()
        return result.get('htmlLink')

    except Exception as e:
        print(f"Error adding event: {e}")
        return "Failed to add event to calendar"

def delete_event(event_id):
    """
    Deletes a Google Calendar event by its event ID.

    Args:
        event_id (str): The unique identifier of the calendar event.

    Returns:
        str: "Deleted" on success, or error message on failure.
    """
    if not os.path.exists(TOKEN_PICKLE):
        return "Authorization required"

    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)
        service = build('calendar', 'v3', credentials=credentials)
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return "Deleted"
    except Exception as e:
        print(f"Error deleting event: {e}")
        return "Failed"

def find_event_id(date, start_time):
    """
    Locates the first Google Calendar event ID starting at a specific date and time.

    Args:
        date (str): Date in YYYY-MM-DD format.
        start_time (str): Time in HH:MM (24h) format.

    Returns:
        str or None: Event ID if found, else None.
    """
    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

        service = build('calendar', 'v3', credentials=credentials)

        start = f"{date}T{start_time}:00-07:00"
        end = f"{date}T{start_time}:59-07:00"

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if events:
            return events[0].get("id")

        return None

    except Exception as e:
        print(f"Error finding event ID: {e}")
        return None