from google_oauth import get_gmail_service
from email.mime.text import MIMEText
import base64
from flask import flash


def handle_error(error_message):
    """Centralized error handling to improve reusability and consistency."""
    flash(f"An error occurred: {error_message}")
    print(error_message)
    return False


def prepare_email_data(email_id=None, subject=None, gpt_response=None):
    """Prepares email data with optional email and GPT response."""
    email = (
        get_gmail_email_by_id(email_id)
        if email_id
        else {"from": "", "subject": "", "body": ""}
    )
    return {"email": email, "subject": subject, "gpt_response": gpt_response}


def send_gmail_email(to, subject, message_text):
    """Sends an email using Gmail API."""
    service = get_gmail_service()
    if not service:
        return handle_error("Failed to initialize Gmail service.")

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
        return handle_error(f"Failed to send email: {str(e)}")


def get_gmail_emails():
    """Fetches the list of received emails from Gmail."""
    service = get_gmail_service()
    if not service:
        return handle_error("Failed to initialize Gmail service.")

    try:
        # Fetch the list of received messages (only from inbox) using the Gmail API
        results = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=20)
            .execute()
        )
        messages = results.get("messages", [])

        if not messages:
            flash("No messages found.")
            return []

        email_list = []
        for message in messages:
            msg = (
                service.users().messages().get(userId="me", id=message["id"]).execute()
            )

            # Extract headers and provide defaults if missing
            headers = msg["payload"].get("headers", [])

            subject = next(
                (header["value"] for header in headers if header["name"] == "Subject"),
                "(No Subject)",
            )
            from_email = next(
                (header["value"] for header in headers if header["name"] == "From"),
                "(No Sender)",
            )

            email_list.append(
                {
                    "id": message["id"],
                    "snippet": msg.get("snippet", ""),
                    "subject": subject,
                    "from": from_email,
                }
            )

        return email_list
    except Exception as e:
        return handle_error(f"Failed to fetch emails: {str(e)}")


def get_gmail_email_by_id(email_id):
    """Fetches a specific email by its ID."""
    service = get_gmail_service()
    if not service:
        return handle_error("Failed to initialize Gmail service.")

    try:
        # Fetch the email message using the Gmail API
        email = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )

        headers = email.get("payload", {}).get("headers", [])
        parts = email.get("payload", {}).get("parts", [])

        def get_body_from_parts(parts):
            """Extracts the body of the email from its parts."""
            for part in parts:
                if part.get("mimeType") == "text/plain" and "data" in part.get(
                    "body", {}
                ):
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
                elif part.get("parts"):
                    return get_body_from_parts(part["parts"])
            return "(No body content found)"

        # Extract the email body
        body = get_body_from_parts(parts)

        return {
            "body": body,
            "subject": next(
                (header["value"] for header in headers if header["name"] == "Subject"),
                "(No Subject)",
            ),
            "from": next(
                (header["value"] for header in headers if header["name"] == "From"),
                "(No Sender)",
            ),
        }
    except Exception as e:
        return handle_error(f"Failed to fetch email by ID: {str(e)}")
