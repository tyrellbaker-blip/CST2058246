import json
from flask import Flask, render_template, request, jsonify, redirect
from flask_bootstrap import Bootstrap5
import os
from dotenv import load_dotenv
from openai import OpenAI
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pickle
from datetime import datetime
from dateutil.parser import parse

app = Flask(__name__)
bootstrap = Bootstrap5(app)

# Set up environment
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
client = OpenAI()

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_PICKLE = 'token.pickle'

# Conversation + scheduling memory
conversation_history = []
partial_event = {}

# --- Helper Functions ---
def parse_event_json(raw_json):
    try:
        event = json.loads(raw_json)
        return {
            "intent": event.get("intent"),
            "title": event.get("title"),
            "date": event.get("date"),
            "start_time": event.get("start_time"),
            "end_time": event.get("end_time"),
            "recurrence": event.get("recurrence"),
            "location": event.get("location"),
            "notes": event.get("notes"),
        }
    except json.JSONDecodeError:
        return None

def is_valid_event(event):
    if not event:
        return False
    required = ["title", "date", "start_time", "end_time"]
    return all(event.get(field) for field in required)

def has_calendar_conflict(event):
    if not os.path.exists(TOKEN_PICKLE):
        return False
    with open(TOKEN_PICKLE, 'rb') as token:
        credentials = pickle.load(token)
    service = build('calendar', 'v3', credentials=credentials)
    start = f"{event['date']}T{event['start_time']}:00"
    end = f"{event['date']}T{event['end_time']}:00"
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    return len(events) > 0

def add_to_my_calendar(event):
    print("📅 Inserting event into Google Calendar:", event)
    if not os.path.exists(TOKEN_PICKLE):
        return "Authorization required"
    with open(TOKEN_PICKLE, 'rb') as token:
        credentials = pickle.load(token)
    service = build('calendar', 'v3', credentials=credentials)

    start = f"{event['date']}T{event['start_time']}:00"
    end = f"{event['date']}T{event['end_time']}:00"

    new_event = {
        "summary": event["title"],
        "start": {"dateTime": start, "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end, "timeZone": "America/Los_Angeles"},
        "location": event["location"],
        "description": event["notes"],
    }

    if event.get("recurrence"):
        new_event["recurrence"] = [event["recurrence"]]
    new_event = {k: v for k, v in new_event.items() if v is not None}
    result = service.events().insert(calendarId="primary", body=new_event).execute()
    return result.get("htmlLink")

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    global partial_event
    data = request.json
    user_input = data.get("message")

    if not user_input:
        return jsonify({"response": "I didn't catch that. Can you say it again?", "structured": None})

    if user_input.strip().lower() in ['reset', 'start over', 'clear', 'i made a mistake']:
        conversation_history.clear()
        partial_event = {}
        return jsonify({"response": "Alright! We can start over. What did you need to schedule, again?", "structured": None})

    conversation_history.append({"role": "user", "content": user_input})

    try:
        # Conversational reply
        chat_response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {"role": "system", "content": (
                    "You are a helpful, informal scheduling assistant. Respond casually to scheduling requests. "
                    "If the user provides partial info, ask follow-up questions. Confirm before scheduling. "
                    "Don't show structured data or JSON to the user."
                )},
                *conversation_history
            ],
            temperature=0.3,
            max_tokens=75
        )
        chat_reply = chat_response.choices[0].message.content.strip()
        conversation_history.append({"role": "assistant", "content": chat_reply})

        # Structured extraction
        extract_response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {"role": "system", "content": (
                    "Extract intent and scheduling info from user input. Output ONLY valid JSON:\n"
                    "{\n"
                    "  \"intent\": \"schedule\" | \"reschedule\" | \"cancel\" | \"unknown\",\n"
                    "  \"title\": string,\n"
                    "  \"date\": \"YYYY-MM-DD\",\n"
                    "  \"start_time\": \"HH:MM\",\n"
                    "  \"end_time\": \"HH:MM\",\n"
                    "  \"recurrence\": string or null,\n"
                    "  \"location\": string or null,\n"
                    "  \"notes\": string or null\n"
                    "}\n"
                    "Use null for anything missing. No extra text."
                )},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=150
        )

        raw_json = extract_response.choices[0].message.content.strip()
        parsed_event = parse_event_json(raw_json)
        print("🧠 Parsed structured event:", parsed_event)
        print("👉 Intent:", parsed_event.get("intent"))
        print("✅ Valid?", is_valid_event(parsed_event))

        # 🧠 Merge with memory (even if intent is still "schedule")
        if partial_event:
            print("🔁 Merging with previous partial event")
            for key, value in partial_event.items():
                if not parsed_event.get(key) and value:
                    parsed_event[key] = value

        if parsed_event.get("intent") == "schedule":
            partial_event = parsed_event  # Store in memory

            # Ask follow-ups
            missing = []
            if not parsed_event.get("start_time"):
                missing.append("What time does it start?")
            if not parsed_event.get("end_time"):
                missing.append("What time does it end?")
            if not parsed_event.get("recurrence"):
                missing.append("Does this repeat?")
            if not parsed_event.get("location"):
                missing.append("Where is this happening?")
            if not parsed_event.get("notes"):
                missing.append("Any notes?")

            if missing:
                followup = "Before I add this to your calendar:\n" + "\n".join(f"- {q}" for q in missing)
                return jsonify({"response": followup, "structured": parsed_event})

            if has_calendar_conflict(parsed_event):
                return jsonify({
                    "response": "⚠️ You already have something scheduled at that time. Want to pick another time?",
                    "structured": parsed_event
                })

            if is_valid_event(parsed_event):
                link = add_to_my_calendar(parsed_event)
                partial_event = {}  # Clear memory after scheduling
                return jsonify({
                    "response": f"✅ Done! I've added this to your calendar. [View it here]({link})",
                    "structured": parsed_event
                })

        return jsonify({
            "response": chat_reply,
            "structured": parsed_event if parsed_event else None
        })

    except Exception as e:
        print("OpenAI API error:", e)
        return jsonify({
            "response": "Something went wrong. Try again shortly.",
            "structured": None
        })


@app.route('/authorize')
def authorize():
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:5000/oauth2callback'
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:5000/oauth2callback'
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    with open(TOKEN_PICKLE, 'wb') as token:
        pickle.dump(credentials, token)
    return "✅ Authorized! You may now use Google Calendar."


if __name__ == '__main__':
    app.run(debug=True)
