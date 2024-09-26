from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g,
)
from schema import db, InquiredCompany, User
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_dance.contrib.google import make_google_blueprint, google
from functools import wraps
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
from email.mime.text import MIMEText
import base64

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('DATABASE_PATH')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Google OAuth configuration with Flask-Dance using Flask-Sessions
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=SCOPES,
    redirect_to="google_authorized",
    reprompt_consent=True,
    offline=True,
)
app.register_blueprint(google_bp)

# Allow insecure transport for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def get_gmail_service():
    if not google.authorized:
        flash("Google is not authorized.")
        return None

    token = session.get("google_oauth_token", None)
    if not token:
        flash("No token available.")
        return None

    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    service = build("gmail", "v1", credentials=creds)
    return service


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


@app.route("/")
def index():
    if "user_id" in session:
        return render_template("index.html")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        new_user = User(email=email, password=password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful!")
            return redirect(url_for("login"))
        except SQLAlchemyError:
            db.session.rollback()
            flash("User already exists.")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session["user_id"] = user.id
            flash("Login successful!")
            return redirect(url_for("index"))
        flash("Invalid credentials")
    return render_template("login.html")


@app.route("/send_email", methods=["GET", "POST"])
@login_required
def send_email():
    if request.method == "POST":
        success = send_gmail_email(
            request.form["to"], request.form["subject"], request.form["message"]
        )
        if success:
            flash("Email sent successfully!")
        else:
            flash("Failed to send email.")
        return redirect(url_for("send_email"))

    return render_template("send_email.html")


@app.route("/email_body/<email_id>")
@login_required
def email_body(email_id):
    # Fetch the full message using the Gmail API
    service = get_gmail_service()
    if not service:
        return "Gmail service unavailable", 500

    try:
        # Fetch the full email content by its ID
        msg = service.users().messages().get(userId="me", id=email_id).execute()

        # Check if the message has parts (multipart email) or is single part
        if "parts" in msg["payload"]:
            # Multipart email, extract the body from the parts
            parts = msg["payload"]["parts"]
            body = ""
            for part in parts:
                if (
                    part["mimeType"] == "text/plain"
                ):  # We are looking for plain text content
                    body += base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
        else:
            # Single part email
            body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode(
                "utf-8"
            )

        # Return the full body as a response
        return f"<pre>{body}</pre>"
    except Exception as e:
        return f"Error fetching full email: {str(e)}", 500


@app.route("/view_emails")
@login_required
def view_emails():
    emails = get_gmail_emails()
    return render_template("view_emails.html", emails=emails)


@app.route("/google_authorized")
def google_authorized():
    if not google.authorized:
        flash("Authorization failed.")
        return redirect(url_for("login"))

    # Check the granted scopes
    token = session.get("google_token", None)
    if token:
        flash(f"Granted scopes: {token['scope']}")  # Shows the granted scopes

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Failed to fetch user info from Google.")
        return redirect(url_for("login"))

    user_info = resp.json()
    user = User.query.filter_by(email=user_info["email"]).first()

    if not user:
        user = User(
            name=user_info["name"],
            email=user_info["email"],
            password=generate_password_hash("password", method="pbkdf2:sha256"),
        )
        db.session.add(user)
        db.session.commit()

    session["user_id"] = user.id
    flash("Google login successful!")
    return redirect(url_for("index"))


@app.route("/register_company", methods=["GET", "POST"])
@login_required
def register_company():
    if request.method == "POST":
        try:
            company_data = {
                "name": request.form["name"],
                "date_applied": (
                    datetime.strptime(request.form["date_applied"], "%Y-%m-%d")
                    if request.form["date_applied"]
                    else None
                ),
                "location": request.form["location"],
                "industry": request.form["industry"],
                "contact_person": request.form["contact_person"],
                "email": request.form["email"],
                "phone": request.form["phone"],
                "link": request.form["link"],
            }
            company = InquiredCompany(**company_data)
            db.session.add(company)
            db.session.commit()
            flash("Company registered successfully!")
        except SQLAlchemyError:
            db.session.rollback()
            flash("An error occurred while registering the company.")
        return redirect(url_for("register_company"))

    return render_template("register_company.html")


@app.route("/delete_company/<int:id>", methods=["POST"])
@login_required
def delete_company(id):
    try:
        company = db.session.get(InquiredCompany, id)
        db.session.delete(company)
        db.session.commit()
        flash("Company deleted successfully!")
    except SQLAlchemyError:
        db.session.rollback()
        flash("An error occurred while deleting the company.")
    return redirect(url_for("index"))


@app.route("/edit_company/<int:id>", methods=["GET", "POST"])
@login_required
def edit_company(id):
    company = db.session.get(InquiredCompany, id)
    if request.method == "POST":
        try:
            company.name = request.form["name"]
            company.date_applied = (
                datetime.strptime(request.form["date_applied"], "%Y-%m-%d")
                if request.form["date_applied"]
                else None
            )
            company.location = request.form["location"]
            company.industry = request.form["industry"]
            company.contact_person = request.form["contact_person"]
            company.email = request.form["email"]
            company.phone = request.form["phone"]
            company.link = request.form["link"]

            db.session.commit()
            flash("Company updated successfully!")
        except SQLAlchemyError:
            db.session.rollback()
            flash("An error occurred while updating the company.")
        return redirect(url_for("index"))

    return render_template("edit_company.html", company=company)


@app.route("/reset")
def reset():
    session.pop("google_token", None)  # Remove the token from the session
    session.pop("user_id", None)
    flash("Reauthorization required. Please login again.")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


@app.before_request
def load_logged_in_user():
    g.user = (
        db.session.get(User, session.get("user_id")) if "user_id" in session else None
    )


@app.context_processor
def inject_user():
    return {"current_user": g.user}


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
