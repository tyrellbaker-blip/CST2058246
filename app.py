import json
import os
import pickle
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_bootstrap import Bootstrap5
from dotenv import load_dotenv
from openai import OpenAI
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from functools import wraps

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

# --- Login Decorator ---
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

        start = f"{date}T{start_time}:00"
        end = f"{date}T{end_time}:00"

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return len(events) > 0

    except:
        return False

# --- Calendar Event Creation ---
def add_to_my_calendar(title, date, start_time, end_time, location=None, notes=None, recurrence=None):
    if not os.path.exists(TOKEN_PICKLE):
        return "Authorization required"

    try:
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

        service = build('calendar', 'v3', credentials=credentials)

        start = f"{date}T{start_time}:00"
        end = f"{date}T{end_time}:00"

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

    except:
        return "Failed to add event to calendar"

# --- GPT Action / Tool Definition ---
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

# --- Routes ---

@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.json
    user_input = data.get("message")
    if not user_input:
        return jsonify({"response": "I didn't catch that. Can you say it again?", "structured": None})

    try:
        response = client.chat.completions.create(
            model='gpt-3.5-turbo-1106',
            messages=[
                {"role": "system", "content": (
                    "You are a helpful, informal scheduling assistant. Respond to scheduling requests naturally. "
                    "If you have enough information, call the `schedule_event` function. Otherwise, ask the user follow-up questions."
                )},
                {"role": "user", "content": user_input}
            ],
            tools=[schedule_event_tool],
            tool_choice="auto"
        )

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)

            try:
                link = add_to_my_calendar(**args)
                return jsonify({
                    "response": f"✅ Event added to your calendar. [View it here]({link})",
                    "structured": args
                })
            except:
                return jsonify({
                    "response": "Something went wrong when trying to schedule the event.",
                    "structured": args
                })

        return jsonify({
            "response": message.content,
            "structured": None
        })

    except:
        return jsonify({
            "response": "Something went wrong on my end. Try again in a sec!",
            "structured": None
        })


@app.route('/authorize')
def authorize():
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://127.0.0.1:5000/oauth2callback'
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)


@app.route('/oauth2callback')
def oauth2callback():
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
    if os.path.exists(TOKEN_PICKLE):
        os.remove(TOKEN_PICKLE)
    return redirect(url_for("authorize"))


if __name__ == '__main__':
    app.run(debug=True)
