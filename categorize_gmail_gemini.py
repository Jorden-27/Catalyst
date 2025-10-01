import os
import base64
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.generativeai as genai

# -------------------------------
# 1. Load environment variables
# -------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# -------------------------------
# 2. Gmail API setup
# -------------------------------
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def gmail_authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# -------------------------------
# 3. Fetch emails
# -------------------------------
def get_messages(service, max_results=5):
    results = service.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = results.get("messages", [])
    email_list = []
    for msg in messages:
        txt = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = txt["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")

        body = ""
        if "data" in txt["payload"]["body"]:
            body = base64.urlsafe_b64decode(txt["payload"]["body"]["data"]).decode("utf-8", errors="ignore")

        email_list.append({"subject": subject, "body": body})
    return email_list

# -------------------------------
# 4. Categorize with Gemini 2.5 Flash
# -------------------------------
def categorize_email(subject, body):
    prompt = f"""
Categorize this email strictly as one of: High, Medium, Low.

Subject: {subject}
Body: {body[:500]}

Respond with ONLY one word: High, Medium, or Low.
"""
    response = model.generate_content(prompt)
    return response.text.strip()

# -------------------------------
# 5. Main
# -------------------------------
if __name__ == "__main__":
    service = gmail_authenticate()
    emails = get_messages(service, max_results=5)

    for idx, email in enumerate(emails, 1):
        priority = categorize_email(email["subject"], email["body"])
        print(f"\n📧 Email {idx}")
        print(f"Subject: {email['subject']}")
        print(f"Priority: {priority}")
