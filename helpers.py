from dateparser import parse as parse_date
from datetime import datetime
from googleapiclient.discovery import build
from functools import wraps
from flask import redirect, url_for
import os
import pickle
import calendar

TOKEN_PICKLE = 'token.pickle'

def resolve_relative_date(text, base_datetime=None):
    """
    Parses natural language date/time like 'next Friday at 2pm'
    into a (YYYY-MM-DD, HH:MM) tuple.
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

def has_calendar_conflict(date, start_time, end_time):
    """
    Checks if there's a Google Calendar event that conflicts
    with the given time range.
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
    Adds a new event to the user's Google Calendar.
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

def get_calendar_data(month: int, year: int):
    """
    Generates the calendar grid structure for the given month and year.
    """
    cal = calendar.Calendar()
    month_days = list(cal.itermonthdays(year, month))
    blanks = month_days[:month_days.index(1)] if 1 in month_days else []
    days = [d for d in month_days if d != 0]

    return {
        "month": month,
        "year": year,
        "month_name": calendar.month_name[month],
        "blanks": blanks,
        "days": days,
        "week_days": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    }
