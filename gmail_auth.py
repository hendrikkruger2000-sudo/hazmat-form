import os, json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_service():
    token_json = os.getenv("GMAIL_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("❌ GMAIL_TOKEN_JSON not set in environment")
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    service = build('gmail', 'v1', credentials=creds)
    return service