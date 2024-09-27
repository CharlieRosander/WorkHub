from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    flash,
    request,
    g,
    jsonify,
)
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
from gpt_service import get_gpt_response
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
            request.form["to"],
            request.form["your_response_subject"],
            request.form["message"],
        )
        if success:
            flash("Email sent successfully!")
        else:
            flash("Failed to send email.")
        return redirect(url_for("send_email"))

    email_id = request.args.get("email_id")
    original_email_subject = request.args.get("original_email_subject", "")
    gpt_response_subject = request.args.get("gpt_response_subject", "")
    gpt_response = request.args.get("gpt_response", "")  # Fetch GPT response

    # Fetch the email information based on the email_id
    email = get_gmail_email_by_id(email_id) if email_id else None
    if not email:
        email = {
            "from": "",
            "subject": original_email_subject,
            "body": "",
        }

    return render_template(
        "send_email.html",
        email=email,
        original_email_subject=original_email_subject,
        your_response_subject=gpt_response_subject,
        gpt_response=gpt_response,
    )


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


@app.route("/process_email_for_gpt/<email_id>", methods=["GET", "POST"])
@login_required
def process_email_for_gpt(email_id):
    full_email = get_gmail_email_by_id(email_id)

    if not full_email:
        flash("Error: Could not retrieve the full email content.")
        return redirect(url_for("view_emails"))

    # Get the full GPT response in one call
    gpt_response = get_gpt_response(full_email["body"])

    # Bevara ämnet och skicka det till HTML-sidan
    return render_template(
        "send_email.html",
        gpt_response=gpt_response,
        email=full_email,
        original_email_subject=full_email[
            "subject"
        ],  # Bevara original email subject här
        your_response_subject=f"RE: {full_email['subject']}",  # Your response subject
    )


@app.route("/regenerate_gpt_response", methods=["POST"])
@login_required
def regenerate_gpt_response():
    email_body = request.form.get("email_body", "")
    to = request.form.get("to", "")
    your_response_subject = request.form.get("your_response_subject", "")
    original_email_subject = request.form.get("original_email_subject", "")

    if not email_body:
        flash("Original email saknas. Kunde inte regenerera GPT-svaret.")
        return redirect(url_for("send_email"))

    comment = "Please regenerate the response and provide a different draft."
    gpt_request = f"{email_body}\n\n{comment}"

    gpt_response = get_gpt_response(gpt_request)

    return render_template(
        "send_email.html",
        email={"from": to, "subject": original_email_subject, "body": email_body},
        gpt_response=gpt_response,
        original_email_subject=original_email_subject,  # Skicka tillbaka original ämnet
        your_response_subject=your_response_subject,
    )


@app.route("/generate_gpt_from_link", methods=["POST"])
@login_required
def generate_gpt_from_link():
    link_or_text = request.form.get("link", "")

    # Skicka länken eller texten till GPT för att generera ett svar
    gpt_response = get_gpt_response(link_or_text)

    # Rendera om sidan med GPT-svaret
    return render_template(
        "send_email.html",
        email={"from": "", "subject": "", "body": ""},
        gpt_response=gpt_response,
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
