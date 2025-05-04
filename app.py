import json
import os
import pickle
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_bootstrap import Bootstrap5
from dotenv import load_dotenv
from googleapiclient.discovery import build
from openai import OpenAI
from google_auth_oauthlib.flow import Flow

# 🧠 Imported from your helper module
from helpers import (
    login_required,
    add_to_my_calendar,
    resolve_relative_date,
    has_calendar_conflict,
    delete_event,
    find_event_id
)

# --- App & Bootstrap ---
app = Flask(__name__)
bootstrap = Bootstrap5(app)

# --- Environment Setup ---
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
client = OpenAI()

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]
CREDENTIALS_FILE = 'credentials.json'
TOKEN_PICKLE = 'token.pickle'

# --- GPT Tool Definitions ---
schedule_event_tool = {
    "type": "function",
    "function": {
        "name": "schedule_event",
        "description": "Add an event to the user's calendar.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "Start time (24h HH:MM)"},
                "end_time": {"type": "string", "description": "End time (24h HH:MM)"},
                "location": {"type": "string", "description": "Where the event takes place"},
                "notes": {"type": "string", "description": "Additional notes"},
                "recurrence": {"type": "string", "description": "RRULE for repeating events (optional)"}
            },
            "required": ["title", "date", "start_time", "end_time"]
        }
    }
}

delete_event_tool = {
    "type": "function",
    "function": {
        "name": "delete_event",
        "description": "Delete an existing calendar event at a specific date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date of the event in YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "Start time of the event in HH:MM (24h) format"}
            },
            "required": ["date", "start_time"]
        }
    }
}

# --- Routes ---

@app.route('/')
@login_required
def index():
    """
    Render the main application page after login.
    """
    with open(TOKEN_PICKLE, 'rb') as token:
        credentials = pickle.load(token)
    user_info_service = build('oauth2', 'v2', credentials=credentials)
    user_info = user_info_service.userinfo().get().execute()
    user_email = user_info.get("email")
    return render_template('index.html', calendar_id=user_email)


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    """
    Handle incoming chat messages. Use OpenAI to interpret user intent and either
    schedule or delete events on their Google Calendar.
    """
    data = request.json
    user_input = data.get("message")
    if not user_input:
        return jsonify({"response": "I didn't catch that. Can you say it again?", "structured": None})

    now = datetime.now()
    today_info = now.strftime("%A, %B %d, %Y at %H:%M")

    try:
        response = client.chat.completions.create(
            model='gpt-3.5-turbo-1106',
            messages=[
                {"role": "system", "content": (
                    "You are a helpful, informal scheduling assistant. Respond to scheduling requests naturally. "
                    f"Today is {today_info}. Use this to interpret dates given to you without a specific date. "
                    "If you have enough information, call the appropriate function like `schedule_event` or `delete_event`. "
                    "Otherwise, ask follow-up questions. Not every answer needs to schedule something — you can help the user clarify."
                )},
                {"role": "user", "content": user_input}
            ],
            tools=[schedule_event_tool, delete_event_tool],
            tool_choice="auto"
        )

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            tool_name = tool_call.function.name

            if tool_name == "schedule_event":
                conflict_exists = has_calendar_conflict(
                    date=args["date"],
                    start_time=args["start_time"],
                    end_time=args["end_time"]
                )
                if conflict_exists:
                    return jsonify({
                        "response": "conflict",
                        "message": "⚠️ You already have something scheduled at this time. Please choose another slot.",
                        "structured": args
                    })
                try:
                    link = add_to_my_calendar(**args)
                    return jsonify({
                        "response": "success",
                        "message": f"✅ Event added to your calendar. [View it here]({link})",
                        "structured": args
                    })
                except Exception as e:
                    print(f"Error scheduling event: {e}")
                    return jsonify({
                        "response": "error",
                        "message": "Something went wrong when trying to schedule the event.",
                        "structured": args
                    })

            elif tool_name == "delete_event":
                event_id = find_event_id(args["date"], args["start_time"])
                if event_id:
                    result = delete_event(event_id)
                    if result == "Deleted":
                        return jsonify({
                            "response": "success",
                            "message": "🗑️ Event deleted successfully.",
                            "structured": args
                        })
                return jsonify({
                    "response": "error",
                    "message": "⚠️ Could not find or delete the event.",
                    "structured": args
                })

        resolved_date, resolved_time = resolve_relative_date(user_input)
        structured = {"resolved_date": resolved_date, "resolved_time": resolved_time} if resolved_date else None

        return jsonify({
            "response": "followup",
            "message": message.content,
            "structured": structured
        })

    except Exception as e:
        print(f"GPT or server error: {e}")
        return jsonify({
            "response": "error",
            "message": "Something went wrong on my end. Try again in a sec!",
            "structured": None
        })


@app.route('/authorize')
def authorize():
    """
    Start the OAuth 2.0 authorization flow with Google.
    """
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://127.0.0.1:5000/oauth2callback'
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)


@app.route('/oauth2callback')
def oauth2callback():
    """
    Handle the OAuth callback and save the user's credentials.
    """
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://127.0.0.1:5000/oauth2callback'
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    with open(TOKEN_PICKLE, 'wb') as token:
        pickle.dump(credentials, token)
    return redirect(url_for("index"))


@app.route('/logout')
def logout():
    """
    Clear saved OAuth credentials and redirect to re-authenticate.
    """
    if os.path.exists(TOKEN_PICKLE):
        os.remove(TOKEN_PICKLE)
    return redirect(url_for("authorize"))


@app.route('/events')
@login_required
def get_events():
    """
    Fetch upcoming calendar events from the user's Google Calendar.
    """
    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)
        service = build('calendar', 'v3', credentials=credentials)

        now = datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        formatted_events = []
        for event in events:
            formatted_events.append({
                "id": event.get("id"),
                "title": event.get("summary"),
                "start": event["start"].get("dateTime", event["start"].get("date")),
                "end": event["end"].get("dateTime", event["end"].get("date"))
            })

        return jsonify(formatted_events)

    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify([])


@app.route('/delete-event', methods=['POST'])
@login_required
def delete_event_route():
    """
    Delete a specific event from the user's calendar using the provided event ID.
    """
    data = request.json
    event_id = data.get("event_id")
    if not event_id:
        return jsonify({"status": "error", "message": "Missing event ID"})

    result = delete_event(event_id)
    if result == "Deleted":
        return jsonify({"status": "success", "message": "Event deleted"})
    else:
        return jsonify({"status": "error", "message": "Failed to delete event"})


if __name__ == '__main__':
    app.run(debug=True)