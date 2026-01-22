from datetime import datetime, timedelta, time
from dateutil.parser import isoparse
import pytz
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# -------------------------------
# CONFIG
# -------------------------------
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TIMEZONE = pytz.timezone("Asia/Kolkata")

WORK_START = time(10, 0)   # 10:00 AM
WORK_END = time(18, 0)     # 6:00 PM

SLOTS_REQUIRED = 3
SLOT_STEP_MINUTES = 15     # sliding window step

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
# FETCH BUSY SLOTS (FIXED)
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

    # 🔑 CRITICAL FIX: normalize to local timezone
    busy_slots = [
        (
            isoparse(b["start"]).astimezone(TIMEZONE),
            isoparse(b["end"]).astimezone(TIMEZONE)
        )
        for b in busy
    ]

    return busy_slots

# -------------------------------
# AVAILABILITY ENGINE (CORRECT)
# -------------------------------
def generate_free_slots(
    busy_slots,
    start_date,
    end_date,
    duration_minutes
):
    free_slots = []
    current_date = start_date

    while current_date <= end_date and len(free_slots) < SLOTS_REQUIRED:
        day_start = TIMEZONE.localize(datetime.combine(current_date, WORK_START))
        day_end = TIMEZONE.localize(datetime.combine(current_date, WORK_END))
    
        slot_start = day_start
        while slot_start + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = slot_start + timedelta(minutes=duration_minutes)

            # overlap check
            overlap = False
            for busy_start, busy_end in busy_slots:
                if slot_start < busy_end and slot_end > busy_start:
                    overlap = True
                    break

            if not overlap:
                free_slots.append((slot_start, slot_end))
                if len(free_slots) == SLOTS_REQUIRED:
                    return free_slots

            # move by small step, not duration
            slot_start += timedelta(minutes=SLOT_STEP_MINUTES)

        current_date += timedelta(days=1)

    return free_slots

# -------------------------------
# FORMAT OUTPUT
# -------------------------------
def format_slots(slots):
    return [
        f"{start.strftime('%A, %d %b %Y — %I:%M %p')} "
        f"to {end.strftime('%I:%M %p')} IST"
        for start, end in slots
    ]

# -------------------------------
# MAIN FLOW
# -------------------------------
def suggest_meeting_slots(from_date_str, to_date_str, duration_minutes):
    service = get_calendar_service()

    from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()

    start_dt = TIMEZONE.localize(datetime.combine(from_date, time.min))
    end_dt = TIMEZONE.localize(datetime.combine(to_date, time.max))

    busy_slots = get_busy_slots(service, start_dt, end_dt)

    # 🔍 DEBUG (optional – remove later)
    print("\nDEBUG: Busy slots from calendar")
    for bs, be in busy_slots:
        print("BUSY:", bs.strftime("%H:%M"), "-", be.strftime("%H:%M"))

    free_slots = generate_free_slots(
        busy_slots,
        from_date,
        to_date,
        duration_minutes
    )

    return format_slots(free_slots)

# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    from_date = input("Enter FROM date (YYYY-MM-DD): ")
    to_date = input("Enter TO date (YYYY-MM-DD): ")
    duration = int(input("Enter meeting duration (minutes): "))

    slots = suggest_meeting_slots(from_date, to_date, duration)

    print("\nSuggested meeting slots:\n")
    for s in slots:
        print("•", s)
