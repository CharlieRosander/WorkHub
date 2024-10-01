from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    flash,
    request,
    g,
)
from schema import db, User, InquiredCompany
from google_oauth import (
    google_bp,
    login_required,
    handle_google_authorization,
    is_google_authorized,
)
from email_service import (
    send_gmail_email,
    get_gmail_emails,
    get_gmail_email_by_id,
    prepare_email_data,
)
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
import os
from company_service import register_company, delete_company, edit_company
from gpt_service import get_gpt_response

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
        companies = InquiredCompany.query.all()  # Fetch all companies from the database
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


@app.route("/send_email", methods=["GET", "POST"])
@login_required
def send_email():
    if request.method == "POST":
        if send_gmail_email(
            request.form["to"], request.form["subject"], request.form["message"]
        ):
            flash("Email sent successfully!")
        return redirect(url_for("view_emails"))

    # Use the prepare_email_data function to get data for the template
    email_data = prepare_email_data(
        email_id=request.args.get("email_id"),
        subject=request.args.get("subject", ""),
        gpt_response=request.args.get("gpt_response", ""),
    )
    return render_template("send_email.html", **email_data)


@app.route("/view_emails")
@login_required
def view_emails():
    emails = get_gmail_emails()
    return render_template("view_emails.html", emails=emails)


@app.route("/email_body/<email_id>")
@login_required
def email_body(email_id):
    full_email = get_gmail_email_by_id(email_id)
    if not full_email:
        return "Not Found", 404
    return full_email["body"]


@app.route("/process_email_for_gpt/<email_id>", methods=["POST"])
@login_required
def process_email_for_gpt(email_id):
    full_email = get_gmail_email_by_id(email_id)

    if not full_email:
        flash("Error: Could not retrieve the full email content.")
        return redirect(url_for("view_emails"))

    gpt_response = get_gpt_response(full_email["body"])

    # Bevara ämnet i formuläret
    email_data = prepare_email_data(
        email_id=email_id,
        subject="RE: " + full_email["subject"],
        gpt_response=gpt_response,
    )
    return render_template("send_email.html", **email_data)


@app.route("/regenerate_gpt_response", methods=["GET", "POST"])
@login_required
def regenerate_gpt_response():
    email_body = request.form.get("email_body", "")
    subject = request.form.get("subject", "")
    to = request.form.get("to", "")
    message = request.form.get("message", "")

    # Lägg till en kommentar för att begära ett nytt svar
    comment = "Please regenerate the response and provide a different draft."
    gpt_request = f"{email_body}\n\n{comment}"

    # Skicka GPT-förfrågan
    gpt_response = get_gpt_response(gpt_request)

    # Bevara befintliga data och rendera formuläret med det nya GPT-svaret
    email_data = {
        "email": {"from": to, "subject": subject, "body": email_body},
        "subject": subject,
        "gpt_response": gpt_response,
    }
    return render_template("send_email.html", **email_data)


@app.route("/generate_gpt_from_link", methods=["GET", "POST"])
@login_required
def generate_gpt_from_link():
    link_or_text = request.form.get("link", "")

    # Skicka länken eller texten till GPT för att generera ett svar
    gpt_response = get_gpt_response(link_or_text)

    # Förbered e-postdata med GPT-svaret
    email_data = prepare_email_data(gpt_response=gpt_response)

    # Rendera formuläret med GPT:s svar
    return render_template("send_email.html", **email_data)


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
