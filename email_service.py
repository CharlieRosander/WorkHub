from google_oauth import get_gmail_service
from email.mime.text import MIMEText
import base64
from flask import flash


def send_gmail_email(to, subject, message_text):
    service = get_gmail_service()
    if not service:
        return False  # If Gmail service couldn't be initialized, abort

    try:
        # Create the email
        message = MIMEText(message_text)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Send the email
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception as e:
        flash(f"An error occurred while sending the email: {str(e)}")
        return False


def get_gmail_emails():
    service = get_gmail_service()
    if not service:
        flash("Could not initialize Gmail service.")
        print("Could not initialize Gmail service")
        return []

    try:
        # Fetch the list of messages using the Gmail API
        results = service.users().messages().list(userId="me", maxResults=10).execute()
        messages = results.get("messages", [])

        if not messages:
            flash("No messages found.")
            print("No messages found")
            return []

        email_list = []
        for message in messages:
            msg = (
                service.users().messages().get(userId="me", id=message["id"]).execute()
            )

            # Extract the headers and provide defaults if missing
            headers = msg["payload"]["headers"]

            subject = next(
                (header["value"] for header in headers if header["name"] == "Subject"),
                "(No Subject)",
            )
            from_email = next(
                (header["value"] for header in headers if header["name"] == "From"),
                "(No Sender)",
            )

            email_data = {
                "id": message["id"],  # Include the email's unique ID
                "snippet": msg["snippet"],
                "subject": subject,
                "from": from_email,
            }
            email_list.append(email_data)

        return email_list
    except Exception as e:
        flash(f"An error occurred while fetching emails: {e}")
        print(f"Error fetching emails: {e}")
        return []
