from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    flash,
    request,
    g,
    send_file,
    abort,
)
from schema import db, User, InquiredCompany, ScrapedContent
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
from webscrape_service import scrape_website, save_html_to_file
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
import os
from company_service import register_company, delete_company, edit_company
from gpt_service import send_gpt_prompt, process_html_with_gpt
import io
import logging

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('DATABASE_PATH')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

response_assistant_id = os.getenv("RESPONSE_ASSISTANT_ID")
compose_assistant_id = os.getenv("COMPOSE_ASSISTANT_ID")
webscrape_assistant_id = os.getenv("WEBSCRAPE_ASSISTANT_ID")

# Register Google OAuth blueprint
app.register_blueprint(google_bp)

# Konfigurera loggning
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]",
)


@app.route("/")
def index():
    if "user_id" in session:
        companies = InquiredCompany.query.all()
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
            flash("Registration successful!", "success")
            return redirect(url_for("login"))
        except SQLAlchemyError:
            db.session.rollback()
            flash("User already exists.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            session["user_id"] = user.id
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/oauth_callback")
def oauth_callback():
    if not is_google_authorized():
        flash("Authorization failed.", "danger")
        return redirect(url_for("login"))

    user = handle_google_authorization()
    if not user:
        return redirect(url_for("login"))

    session["user_id"] = user.id
    flash("Google login successful!", "success")
    return redirect(url_for("index"))


@app.route("/send_email", methods=["GET", "POST"])
@login_required
def send_email():
    if request.method == "POST":
        if send_gmail_email(
            request.form["to"], request.form["subject"], request.form["message"]
        ):
            flash("Email sent successfully!", "success")
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


# This route is the "Response" type of the GPT call
@app.route("/process_email_for_gpt/<email_id>", methods=["POST"])
@login_required
def process_email_for_gpt(email_id):
    full_email = get_gmail_email_by_id(email_id)

    if not full_email:
        flash("Error: Could not retrieve the full email content.", "danger")
        return redirect(url_for("view_emails"))

    # Skicka e-postens innehåll till Response-assistenten för att generera ett svar
    gpt_response = send_gpt_prompt(
        full_email["body"], assistant_id=response_assistant_id
    )
    logging.info(f"GPT response for email {email_id}: {gpt_response}")

    # Bevara ämnet i formuläret
    email_data = prepare_email_data(
        email_id=email_id,
        subject="RE: " + full_email["subject"],
        gpt_response=gpt_response,
    )
    return render_template("send_email.html", **email_data)


## This route is the "Regenerate" assistant-type of the GPT call - MAYBE, currently using compose ##
@app.route("/regenerate_gpt_response", methods=["POST"])
@login_required
def regenerate_gpt_response():
    email_body = request.form.get("email_body", "")
    subject = request.form.get("subject", "")
    to = request.form.get("to", "")
    message = request.form.get("message", "")

    comment = "Please regenerate the response and provide a different draft."
    gpt_request = f"{email_body}\n\n{comment}"

    # Skickar Emailet till Compose-assistenten för att generera ett nytt svar
    gpt_response = send_gpt_prompt(gpt_request, assistant_id=compose_assistant_id)
    logging.info(f"Regenerated GPT response: {gpt_response}")

    # Bevara befintliga data och rendera formuläret med det nya GPT-svaret
    email_data = {
        "email": {"from": to, "subject": subject, "body": email_body},
        "subject": subject,
        "gpt_response": gpt_response,
    }
    return render_template("send_email.html", **email_data)


### This route is the "Compose" type of the GPT call
@app.route("/generate_gpt_from_link", methods=["POST"])
@login_required
def generate_gpt_from_link():
    source_content = request.form.get("source_content", "")
    additional_instructions = request.form.get("additional_instructions", "")

    gpt_input = f"Source Content:\n{source_content}\n\nAdditional Instructions:\n{additional_instructions}"

    gpt_response = send_gpt_prompt(gpt_input, assistant_id=compose_assistant_id)
    logging.info(f"GPT compose response: {gpt_response}")

    email_data = prepare_email_data(gpt_response=gpt_response)

    return render_template("send_email.html", **email_data)


@app.route("/scrape_job_listing", methods=["POST"])
@login_required
def scrape_job_listing():
    url = request.form.get("scrape_link")
    if not url:
        flash("Please provide a valid URL.", "danger")
        return redirect(url_for("webscraping"))

    scrape_result = scrape_website(url)
    if "error" in scrape_result:
        flash(scrape_result["error"], "danger")
        return redirect(url_for("webscraping"))

    # Spara skrapad data i databasen
    try:
        new_scraped_content = ScrapedContent(
            raw_html=scrape_result.get("raw_html"),
            pretty_html=scrape_result.get("pretty_html"),
            filtered_html=scrape_result.get("filtered_html"),
            scraped_url=url,
        )
        db.session.add(new_scraped_content)
        db.session.commit()
        flash("Website scraped and data saved successfully!", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"An error occurred while saving scraped data: {str(e)}", "danger")
        return redirect(url_for("webscraping"))

    return redirect(url_for("webscraping"))


### Process HTML with webscrape assistant ###
@app.route("/process_html/<html_type>/<int:id>", methods=["POST"])
@login_required
def process_html(html_type, id):
    # Hämta HTML från databasen baserat på typen
    scraped_content = ScrapedContent.query.get(id)
    if not scraped_content:
        flash("Error: Content not found.", "danger")
        return redirect(url_for("webscraping"))

    html_content = getattr(scraped_content, f"{html_type}_html", None)
    if not html_content:
        flash(f"Error: {html_type.capitalize()} HTML not available.", "danger")
        return redirect(url_for("webscraping"))

    gpt_response = process_html_with_gpt(
        html_content, assistant_id=webscrape_assistant_id
    )
    logging.info(f"GPT processed HTML for content {id}: {gpt_response}")

    if gpt_response.startswith("Error"):
        flash(gpt_response, "danger")
        return redirect(url_for("webscraping"))

    # Uppdatera GPT-rensad HTML och spara i databasen
    try:
        scraped_content.gpt_cleaned_html = gpt_response
        db.session.commit()
        flash(
            "HTML successfully processed with GPT! You can now view the result.",
            "success",
        )
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"An error occurred while saving GPT-cleaned HTML: {str(e)}", "danger")

    return redirect(url_for("webscraping"))


### Uppdaterad save_file-route för nedladdning ###
@app.route("/save_file", methods=["GET"])
@login_required
def save_file():
    html_type = request.args.get("html_type")
    data_id = request.args.get("id")

    # Validera att både html_type och id är närvarande
    if not html_type or not data_id:
        flash("Missing 'html_type' or 'id' parameters.", "danger")
        return redirect(url_for("webscraping"))

    # Tillåtna html_type värden
    allowed_html_types = ["raw", "pretty", "filtered", "gpt_cleaned"]
    if html_type not in allowed_html_types:
        flash("Invalid 'html_type' parameter.", "danger")
        return redirect(url_for("webscraping"))

    # Hämta den sparade datan baserat på data_id
    data = ScrapedContent.query.get(data_id)
    if not data:
        flash("Data not found.", "danger")
        return redirect(url_for("webscraping"))

    # Välj rätt HTML-innehåll baserat på html_type
    if html_type == "raw":
        html_content = data.raw_html
        filename = f"raw_html_{data.id}.html"
    elif html_type == "pretty":
        html_content = data.pretty_html
        filename = f"pretty_html_{data.id}.html"
    elif html_type == "filtered":
        html_content = data.filtered_html
        filename = f"filtered_html_{data.id}.html"
    elif html_type == "gpt_cleaned":
        if not data.gpt_cleaned_html:
            flash("GPT-cleaned HTML not available.", "danger")
            return redirect(url_for("webscraping"))
        html_content = data.gpt_cleaned_html
        filename = f"gpt_cleaned_html_{data.id}.html"
    else:
        flash("Invalid 'html_type' parameter.", "danger")
        return redirect(url_for("webscraping"))

    # Logga nedladdningsåtgärden
    logging.info(f"User {g.user.id} downloaded {html_type} HTML for content {data_id}.")

    # Skicka fil som nedladdning
    try:
        file_stream = io.BytesIO(html_content.encode("utf-8"))
        return send_file(
            file_stream,
            mimetype="text/html",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        flash(f"An error occurred while sending the file: {str(e)}", "danger")
        return redirect(url_for("webscraping"))


def get_data_by_id(data_id):
    return ScrapedContent.query.get(data_id)


def capitalize_first_letter(string):
    if not string:
        return ""
    return string[0].upper() + string[1:]


@app.route("/auto_log_company", methods=["POST"])
@login_required
def auto_log_company():
    return "Company logged successfully", 200


@app.route("/webscraping", methods=["GET", "POST"])
@login_required
def webscraping():
    scraped_data = ScrapedContent.query.all()
    return render_template("webscraping.html", scraped_data=scraped_data)


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
    session.pop("google_token", None)
    session.pop("user_id", None)
    flash("Reauthorization required. Please login again.", "warning")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
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
        database_dir = os.getenv("DATABASE_DIR")
        if not database_dir:
            database_dir = "database"
        if not os.path.exists(database_dir):
            os.makedirs(database_dir)
        db.create_all()
    app.run(debug=True)
