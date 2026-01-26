from datetime import datetime, timedelta, time
from dateutil.parser import isoparse
import pytz
import os
import uuid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# -------------------------------
# CONFIG
# -------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events"
]
TIMEZONE = pytz.timezone("Asia/Kolkata")

WORK_START = time(10, 0)
WORK_END = time(18, 0)

SLOTS_REQUIRED = 3
SLOT_STEP_MINUTES = 15

# -------------------------------
# AUTHENTICATION
# -------------------------------
def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

# -------------------------------
# FETCH BUSY SLOTS
# -------------------------------
def get_busy_slots(service, start_dt, end_dt):
    body = {
        "timeMin": start_dt.isoformat(),
        "timeMax": end_dt.isoformat(),
        "timeZone": TIMEZONE.zone,
        "items": [{"id": "primary"}]
    }

    response = service.freebusy().query(body=body).execute()
    busy = response["calendars"]["primary"]["busy"]

    return [
        (
            isoparse(b["start"]).astimezone(TIMEZONE),
            isoparse(b["end"]).astimezone(TIMEZONE)
        )
        for b in busy
    ]

# -------------------------------
# AVAILABILITY ENGINE
# -------------------------------
def generate_free_slots(busy_slots, start_date, end_date, duration_minutes):
    free_slots = []
    current_date = start_date

    while current_date <= end_date and len(free_slots) < SLOTS_REQUIRED:
        day_start = TIMEZONE.localize(datetime.combine(current_date, WORK_START))
        day_end = TIMEZONE.localize(datetime.combine(current_date, WORK_END))

        slot_start = day_start
        while slot_start + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = slot_start + timedelta(minutes=duration_minutes)

            if not any(
                slot_start < busy_end and slot_end > busy_start
                for busy_start, busy_end in busy_slots
            ):
                free_slots.append((slot_start, slot_end))
                if len(free_slots) == SLOTS_REQUIRED:
                    return free_slots

            slot_start += timedelta(minutes=SLOT_STEP_MINUTES)

        current_date += timedelta(days=1)

    return free_slots

# -------------------------------
# FORMAT SLOTS
# -------------------------------
def format_slots(slots):
    return [
        f"{i+1}. {start.strftime('%A, %d %b %Y — %I:%M %p')} "
        f"to {end.strftime('%I:%M %p')} IST"
        for i, (start, end) in enumerate(slots)
    ]

# -------------------------------
# CREATE CALENDAR EVENT (PHASE 2)
# -------------------------------
def create_calendar_event(service, start, end, title):
    event = {
        "summary": title,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": TIMEZONE.zone
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": TIMEZONE.zone
        },
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4())
            }
        }
    }

    created_event = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1
    ).execute()

    return created_event

# -------------------------------
# MAIN FLOW
# -------------------------------
def run_scheduler():
    service = get_calendar_service()

    from_date = input("Enter FROM date (YYYY-MM-DD): ")
    to_date = input("Enter TO date (YYYY-MM-DD): ")
    duration = int(input("Enter meeting duration (minutes): "))
    title = input("Enter meeting title: ")

    start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(to_date, "%Y-%m-%d").date()

    start_dt = TIMEZONE.localize(datetime.combine(start_date, time.min))
    end_dt = TIMEZONE.localize(datetime.combine(end_date, time.max))

    busy_slots = get_busy_slots(service, start_dt, end_dt)

    free_slots = generate_free_slots(
        busy_slots, start_date, end_date, duration
    )

    if not free_slots:
        print("❌ No available slots found.")
        return

    print("\nAvailable slots:")
    formatted = format_slots(free_slots)
    for s in formatted:
        print(s)

    choice = int(input("\nChoose slot number to confirm: ")) - 1
    selected_start, selected_end = free_slots[choice]

    event = create_calendar_event(
        service,
        selected_start,
        selected_end,
        title
    )

    print("\n✅ Event Created Successfully!")
    print("📅 Title:", event["summary"])
    print("🕒 Time:", event["start"]["dateTime"], "-", event["end"]["dateTime"])
    print("🎥 Google Meet:", event["hangoutLink"])

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_scheduler()
