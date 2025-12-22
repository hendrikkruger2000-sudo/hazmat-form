from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_service():
    creds = None
    # Check if token.json exists
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If no valid creds, run OAuth flow
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        # 🔑 Save the token.json file here
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    # Build the Gmail API service
    service = build('gmail', 'v1', credentials=creds)
    return service

if __name__ == "__main__":
    service = get_service()
    print("✅ Gmail API service created successfully, token.json saved.")