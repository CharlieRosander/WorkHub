from flask import Flask, render_template, redirect, url_for, session, flash, request, g
from schema import db, User, InquiredCompany
from google_oauth import (
    google_bp,
    login_required,
    handle_google_authorization,
    is_google_authorized,
)
from email_service import send_gmail_email, get_gmail_emails
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
import os
from company_service import register_company, delete_company, edit_company
from gpt_service import send_to_gpt  # Add your GPT service function
from email_service import get_gmail_email_by_id

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('DATABASE_PATH')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Register Google OAuth blueprint
app.register_blueprint(google_bp)


@app.route("/")
def index():
    if "user_id" in session:
        companies = InquiredCompany.query.all()  # Hämtar alla företag från databasen
        return render_template("index.html", companies=companies)
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


@app.route("/view_emails")
@login_required
def view_emails():
    emails = get_gmail_emails()
    return render_template("view_emails.html", emails=emails)


@app.route("/oauth_callback")
def oauth_callback():
    if not is_google_authorized():
        flash("Authorization failed.")
        return redirect(url_for("login"))

    user = handle_google_authorization()
    if not user:
        return redirect(url_for("login"))

    session["user_id"] = user.id
    flash("Google login successful!")
    return redirect(url_for("index"))


@app.route("/process_email_for_gpt/<email_id>", methods=["POST"])
@login_required
def process_email_for_gpt(email_id):
    # Fetch the full email content
    full_email = get_gmail_email_by_id(email_id)

    if not full_email:
        flash("Error: Could not retrieve the full email content.")
        return redirect(url_for("view_emails"))

    # Send the email content to the GPT service
    gpt_response = send_to_gpt(
        full_email["snippet"]
    )  # Assuming the snippet is the email body

    # Redirect to the send_email view and show the GPT response
    return render_template(
        "send_email.html", gpt_response=gpt_response, email=full_email
    )


@app.route("/register_company", methods=["GET", "POST"])
@login_required
def register_company_route():
    return register_company()


@app.route("/delete_company/<int:id>", methods=["POST"])
@login_required
def delete_company_route(id):
    return delete_company(id)


@app.route("/edit_company/<int:id>", methods=["GET", "POST"])
@login_required
def edit_company_route(id):
    return edit_company(id)


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
