from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g,
    request,
)
from schema import db, InquiredCompany, User
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import google.auth.transport.requests
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from flask_dance.contrib.google import make_google_blueprint, google
from functools import wraps
import dotenv
import base64
import os

app = Flask(__name__, static_url_path="/static")
dotenv.load_dotenv()

# Set secret key and database URI configuration
app.secret_key = "secret"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('DATABASE_PATH')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Set the environment variable to allow insecure transport for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Initialize the database application
db.init_app(app)

# Add the scope for Gmail API
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
TOKEN_FILE = os.getenv("AUTH_TOKEN_PATH")

google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=SCOPES,
    redirect_to="google_authorized",
)
app.register_blueprint(google_bp)


# En decorator för att skydda routes som kräver inloggning
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
@login_required
def index():
    try:
        # Fetch data from the database
        companies = InquiredCompany.query.all()
        return render_template("index.html", companies=companies)
    except SQLAlchemyError as e:
        flash("An error occurred while fetching data from the database.")
        return render_template("index.html", companies=[])


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Kryptera lösenordet innan det sparas
        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")

        # Skapa användare
        new_user = User(email=email, password=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Registrering lyckades!")
            return redirect(url_for("login"))
        except:
            db.session.rollback()
            flash("Användaren finns redan.")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            flash("Inloggning lyckades!")
            return redirect(url_for("index"))
        else:
            flash("Ogiltig email eller lösenord.")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/reset")
def reset():
    session.clear()
    flash("Session reset. Please log in again.")
    return redirect(url_for("login"))


@app.route("/google_authorized")
def google_authorized():
    if not google.authorized:
        flash("Authorization failed.")
        return redirect(url_for("login"))

    resp = google.get("/oauth2/v2/userinfo")

    if not resp.ok:
        flash("Failed to fetch user info from Google.")
        return redirect(url_for("login"))

    user_info = resp.json()
    print(user_info)
    name = user_info["name"]

    # Check if the user exists in your database
    user = User.query.filter_by(name=name).first()
    if not user:
        # Optionally, create a new user
        user = User(name=name)
        user.password = generate_password_hash("password", method="pbkdf2:sha256")
        db.session.add(user)
        db.session.commit()

    # Log the user in by setting the session
    session["user_id"] = user.id
    flash("Inloggning lyckades!")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    # Ta bort användarens session
    session.pop("user_id", None)
    flash("Du har loggats ut.")
    return redirect(url_for("login"))


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = db.session.get(User, user_id)


@app.context_processor
def inject_user():
    return dict(current_user=g.user)


# New route to send email
@app.route("/send_email", methods=["GET", "POST"])
@login_required
def send_email():
    if request.method == "POST":
        try:
            to = request.form["to"]
            subject = request.form["subject"]
            message_text = request.form["message"]

            # Check if we already have token
            if os.path.exists(TOKEN_FILE):
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            else:
                # Authenticate and get a new token
                flow = InstalledAppFlow.from_client_secrets_file(
                    os.getenv("CLIENT_SECRET_PATH"), SCOPES
                )
                creds = flow.run_local_server(port=8080)

                # Save the credentials for the next run
                with open(TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())

            service = build("gmail", "v1", credentials=creds)

            message = MIMEText(message_text)
            message["to"] = to
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            message_body = {"raw": raw}

            service.users().messages().send(userId="me", body=message_body).execute()

            flash("Email sent successfully!")
            return redirect(url_for("send_email"))

        except Exception as e:
            flash(f"An error occurred while sending the email: {str(e)}")
            return redirect(url_for("send_email"))

    return render_template("send_email.html")


@app.route("/register_company", methods=["GET", "POST"])
@login_required
def register_company():
    if request.method == "POST":
        try:
            name = request.form["name"]
            date_applied_str = request.form["date_applied"]
            location = request.form["location"]
            industry = request.form["industry"]
            contact_person = request.form["contact_person"]
            email = request.form["email"]
            phone = request.form["phone"]
            link = request.form["link"]

            # Convert the string from the form to a datetime object
            if date_applied_str:
                date_applied = datetime.strptime(date_applied_str, "%Y-%m-%d")
            else:
                date_applied = None

            company = InquiredCompany(
                name=name,
                date_applied=date_applied,
                location=location,
                industry=industry,
                contact_person=contact_person,
                email=email,
                phone=phone,
                link=link,
            )

            db.session.add(company)
            db.session.commit()

            flash("Company registered successfully!")
            return redirect(url_for("register_company"))

        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"An error occurred: {str(e)}")
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
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"An error occurred: {str(e)}")
    return redirect(url_for("index"))


@app.route("/edit_company/<int:id>", methods=["GET", "POST"])
@login_required
def edit_company(id):
    company = db.session.get(InquiredCompany, id)
    if request.method == "POST":
        try:
            company.name = request.form["name"]
            date_applied_str = request.form["date_applied"]
            company.location = request.form["location"]
            company.industry = request.form["industry"]
            company.contact_person = request.form["contact_person"]
            company.email = request.form["email"]
            company.phone = request.form["phone"]
            company.link = request.form["link"]

            # Convert the string from the form to a datetime object
            if date_applied_str:
                company.date_applied = datetime.strptime(date_applied_str, "%Y-%m-%d")
            else:
                company.date_applied = None

            db.session.commit()
            flash("Company updated successfully!")
            return redirect(url_for("index"))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"An error occurred: {str(e)}")
            return redirect(url_for("edit_company", id=id))
    return render_template("edit_company.html", company=company)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", debug=True)
