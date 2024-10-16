from flask_dance.contrib.google import make_google_blueprint, google
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from flask import session, flash, redirect, url_for
from functools import wraps
import os
from schema import db, User
from werkzeug.security import generate_password_hash
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Define the scopes required for Google OAuth and Gmail API
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Create the Google OAuth blueprint
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=SCOPES,
    redirect_to="oauth_callback",
)

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

    # Försök att uppdatera token om den har gått ut
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            session["google_oauth_token"] = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
            }
        except Exception as e:
            flash("Token has expired, please login again.")
            return redirect(url_for("login"))

    service = build("gmail", "v1", credentials=creds)
    return service


def fetch_google_user_info():
    if not google.authorized:
        return None

    # Fetch the user's info from Google
    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return None

    return resp.json()


def handle_google_authorization():
    user_info = fetch_google_user_info()
    if not user_info:
        flash("Failed to fetch user info from Google.")
        return None

    # Check if the user already exists in the database
    user = User.query.filter_by(email=user_info["email"]).first()

    # If the user doesn't exist, create a new one
    if not user:
        user = User(
            name=user_info["name"],
            email=user_info["email"],
            password=generate_password_hash(
                "password", method="pbkdf2:sha256"
            ),  # Placeholder password - not used for Google login and will likely be removed/changed in the future
        )
        db.session.add(user)
        db.session.commit()

    return user


def is_google_authorized():
    return google.authorized
