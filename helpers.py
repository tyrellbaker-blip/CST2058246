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
    Takes a natural language time expression like 'next Friday at 2pm' and resolves it
    into a concrete (YYYY-MM-DD, HH:MM) tuple using the current datetime.
    """
    base = base_datetime or datetime.now()
    dt = parse_date(text, settings={'RELATIVE_BASE': base})
    if dt:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    return None, None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not os.path.exists(TOKEN_PICKLE):
            return redirect(url_for("authorize"))
        return f(*args, **kwargs)
    return decorated_function

# --- Calendar Conflict Check ---
def has_calendar_conflict(date, start_time, end_time):
    if not os.path.exists(TOKEN_PICKLE):
        return False
    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

        service = build('calendar', 'v3', credentials=credentials)

        # Google API requires timezone-aware ISO format with Z or timezone offset
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

# --- Calendar Event Creation ---
def add_to_my_calendar(title, date, start_time, end_time, location=None, notes=None, recurrence=None):
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