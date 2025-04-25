import json
import os
import pickle
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_bootstrap import Bootstrap5
from dotenv import load_dotenv
from openai import OpenAI
from google_auth_oauthlib.flow import Flow

from helpers import (
    login_required,
    add_to_my_calendar,
    resolve_relative_date,
    has_calendar_conflict,
    get_calendar_data
)

app = Flask(__name__)
bootstrap = Bootstrap5(app)
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

# --- GPT Tool Definition ---
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

@app.route('/')
@login_required
def index():
    now = datetime.now()

    base_month = request.args.get("month", default=now.month, type=int)
    base_year = request.args.get("year", default=now.year, type=int)
    shift = request.args.get("shift", default=0, type=int)

    new_month = base_month + shift
    new_year = base_year

    while new_month > 12:
        new_month -= 12
        new_year += 1
    while new_month < 1:
        new_month += 12
        new_year -= 1

    calendar_data = get_calendar_data(month=new_month, year=new_year)

    return render_template('index.html', calendar_data=calendar_data)

@app.route('/chat', methods=['POST'])
@login_required
def chat():
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
                    f"Today is {today_info}. If a user says 'next Tuesday', understand that it's based on today. "
                    "If you have enough information, call the `schedule_event` function."
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

            conflict_exists = has_calendar_conflict(
                date=args["date"],
                start_time=args["start_time"],
                end_time=args["end_time"]
            )

            if conflict_exists:
                return jsonify({
                    "response": "conflict",
                    "message": "⚠️ You already have something scheduled at this time.",
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
                print(f"Calendar error: {e}")
                return jsonify({
                    "response": "error",
                    "message": "Failed to schedule the event.",
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
        print(f"Error: {e}")
        return jsonify({
            "response": "error",
            "message": "Something went wrong. Please try again.",
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
    return redirect(url_for("index"))

@app.route('/logout')
def logout():
    if os.path.exists(TOKEN_PICKLE):
        os.remove(TOKEN_PICKLE)
    return redirect(url_for("authorize"))

if __name__ == '__main__':
    app.run(debug=True)
