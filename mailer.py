import base64
from email.mime.text import MIMEText
from gmail_auth import get_service

def send_email(to, subject, body):
    service = get_service()
    message = MIMEText(body, "html")
    message['to'] = to
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={'raw': raw}).execute()

if __name__ == "__main__":
    send_email(
        to="hendrikkruger2000@gmail.com",
        subject="✅ Hazmat Global Mail Test",
        body="""
        <h2>Hazmat Global Mail System</h2>
        <p>This is a test email confirming that your Gmail API integration is working.</p>
        <p>Next step: attach waybills and automate client notifications.</p>
        """
    )
    print("✅ Test email sent successfully.")