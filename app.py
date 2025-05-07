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
    jsonify,
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
from werkzeug.utils import secure_filename
import os
import json
from company_service import register_company, delete_company, edit_company
from gpt_service import send_gpt_prompt, process_html_with_gpt
import io
import logging
import re
from dotenv import load_dotenv

load_dotenv(".env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")
database_path = os.getenv("DATABASE_PATH")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.getenv('DATABASE_PATH')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

response_assistant_id = os.getenv("RESPONSE_ASSISTANT_ID")
compose_assistant_id = os.getenv("COMPOSE_ASSISTANT_ID")
webscrape_assistant_id = os.getenv("WEBSCRAPE_ASSISTANT_ID")
naming_assistant_id = os.getenv("NAMING_ASSISTANT_ID")
autofill_assistant_id = os.getenv("AUTOFILL_ASSISTANT_ID")
generate_regenerate_assistant_id = os.getenv("GENERATE_REGENERATE_ASSISTANT_ID")
save_path = os.getenv("SAVE_PATH")

# Register Google OAuth blueprint
app.register_blueprint(google_bp)

# Konfigurera loggning
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]",
)


# Add custom Jinja2 test for current month
@app.template_test("month_is_current")
def is_current_month(date):
    if not date:
        return False
    return date.month == datetime.now().month and date.year == datetime.now().year


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
        try:
            # Kontrollera om det är en AJAX-förfrågan eller vanlig formulärinlämning
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            success = send_gmail_email(
                request.form["to"], request.form["subject"], request.form["message"]
            )
            
            if success:
                message = "Email sent successfully!"
                flash(message, "success")
            else:
                message = "Failed to send email"
                flash(message, "error")
                
            # Om det är en AJAX-förfrågan, returnera JSON-svar
            if is_ajax:
                return jsonify({"success": success, "message": message})
            # Annars, omdirigera till view_emails som tidigare
            else:
                return redirect(url_for("view_emails"))
        except Exception as e:
            error_message = f"Error: {str(e)}"
            flash(error_message, "error")
            
            # Om det är en AJAX-förfrågan, returnera JSON-svar
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": error_message}), 500
            # Annars, omdirigera till view_emails som tidigare
            else:  
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
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 10  # Number of emails per page
        emails, total_count = get_gmail_emails(page=page, per_page=per_page)
        total_pages = (total_count + per_page - 1) // per_page

        return render_template(
            "view_emails.html",
            emails=emails,
            page=page,
            total_pages=total_pages,
            total_count=total_count,
        )
    except Exception as e:
        flash(f"Error loading emails: {str(e)}", "danger")
        return redirect(url_for("index"))


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

    # Initialisera subject från e-postens ämne som fallback
    subject = "RE: " + full_email["subject"]
    
    # Leta efter JSON-objekt med regex (för både vanliga och enkla citattecken)
    json_pattern = r'```json\s*({.*?})\s*```|`{.*?}`|\{.*?\}'
    json_matches = re.finditer(json_pattern, gpt_response, re.DOTALL)
    
    for match in json_matches:
        json_str = match.group(0)
        # Rensa upp JSON-strängen
        if json_str.startswith("```json"):
            json_str = re.sub(r'```json\s*(.*?)\s*```', r'\1', json_str, flags=re.DOTALL)
        elif json_str.startswith("`") and json_str.endswith("`"):
            json_str = json_str[1:-1]
            
        try:
            # Försök parsa JSON-data
            json_data = json.loads(json_str)
            logging.info(f"Successfully parsed JSON in process_email_for_gpt: {json_data}")
            
            # Extrahera subject om det finns
            if "subject" in json_data:
                subject = json_data["subject"]
                
            # Ta bort JSON-objektet från svaret
            gpt_response = gpt_response.replace(match.group(0), "").strip()
            break  # Använd första matchande JSON-objektet
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse JSON match in process_email_for_gpt: {json_str}, error: {str(e)}")
            continue
    
    # Fallback till gamla regex-mönster om JSON-extraktion misslyckades
    subject_match = re.search(r"{Subject:\s*(.*?)}", gpt_response, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()
        # Ta bort ämnet från själva svaret
        gpt_response = gpt_response.replace(subject_match.group(0), "").strip()
    
    # Ta bort eventuell {email:...}-tagg från svaret
    email_match = re.search(r"{email:\s*(.*?)}", gpt_response, re.IGNORECASE)
    if email_match:
        gpt_response = gpt_response.replace(email_match.group(0), "").strip()

    # Använd från-adressen som to-adress
    to_email = full_email.get("from", "")
    
    # För att debugga: Logga värden för att se vad som faktiskt skickas
    logging.info(f"Sending to template - subject: '{subject}', to: '{to_email}'")
    
    return render_template("send_email.html", 
                          email=full_email,  
                          subject=subject, 
                          to=to_email, 
                          gpt_response=gpt_response)


## This route is the "Regenerate" assistant-type of the GPT call - MAYBE, currently using compose ##
@app.route("/regenerate_gpt_response", methods=["POST"])
@login_required
def regenerate_gpt_response():
    try:
        # Hämta data från JSON istället för form
        data = request.get_json()
        email_id = data.get("email_id")
        context_type = data.get("context_type", "email")  # email, source eller annan kontext
        additional_instruction = data.get("additional_instruction", "")
        current_response = data.get("current_response", "")
        
        # Om vi har ett email_id, hämta e-postinnehållet
        if email_id:
            email = get_gmail_email_by_id(email_id)
            if not email:
                return jsonify({"message": "Email not found"}), 404
                
            email_body = email.get("body", "")
            # Endast sätt to_email till avsändarens adress om vi svarar på ett explicit e-postmeddelande
            # Om vi svarar på ett e-postmeddelande, behåll den ursprungliga from-adressen
            to_email = email.get("from", "") if context_type == "email" else ""
            
            # Grundinstruktion för att regenerera
            gpt_request = f"Original Email:\n\n{email_body}\n\n"
            
            if current_response:
                gpt_request += f"Current Response:\n\n{current_response}\n\n"
            
            gpt_request += "Please regenerate the response with different wording and structure while maintaining the context and intent."
            
            # Lägg till eventuella ytterligare instruktioner
            if additional_instruction:
                gpt_request += f"\n\nAdditional Instructions: {additional_instruction}"
        else:
            # Om vi inte har ett email_id, använd innehållet direkt
            source_content = data.get("source_content", "")
            
            to_email = ""  # Sätt till tomt för att låta GPT extrahera e-post
            
            gpt_request = f"Original Content:\n\n{source_content}\n\n"
            
            if current_response:
                gpt_request += f"Current Response:\n\n{current_response}\n\n"
                
            gpt_request += "Please regenerate this response with different wording and structure."
            
            if additional_instruction:
                gpt_request += f"\n\nAdditional Instructions: {additional_instruction}"

        # Send to Compose-assistant for new response
        gpt_response = send_gpt_prompt(
            gpt_request, assistant_id=compose_assistant_id
        )
        
        # Logg för debugging
        logging.info(f"Raw GPT response (regenerate): {gpt_response[:100]}...")

        # Initialisera subject och to_email
        subject = ""
        if email_id and context_type == "email":
            subject = f"RE: {email.get('subject', '')}"
            
        # Försök hitta JSON-data i responsen
        json_pattern = r'```json\s*({.*?})\s*```|`{.*?}`|\{.*?\}'
        json_matches = re.finditer(json_pattern, gpt_response, re.DOTALL)
        
        for match in json_matches:
            json_str = match.group(0)
            # Rensa upp JSON-strängen
            if json_str.startswith("```json"):
                json_str = re.sub(r'```json\s*(.*?)\s*```', r'\1', json_str, flags=re.DOTALL)
            elif json_str.startswith("`") and json_str.endswith("`"):
                json_str = json_str[1:-1]
                
            try:
                # Försök parsa JSON-data
                json_data = json.loads(json_str)
                logging.info(f"Successfully parsed JSON in regenerate_gpt_response: {json_data}")
                
                # Extrahera subject och email om de finns
                if "subject" in json_data:
                    subject = json_data["subject"]
                if "email" in json_data and json_data["email"] != "No email found":
                    # Använd bara e-post från JSON om vi INTE svarar på ett explicit e-postmeddelande
                    # Om vi svarar på ett e-postmeddelande, behåll den ursprungliga from-adressen
                    if context_type != "email":
                        to_email = json_data["email"]
                    
                # Ta bort JSON-objektet från svaret
                gpt_response = gpt_response.replace(match.group(0), "").strip()
                break  # Använd första matchande JSON-objektet
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse JSON match in regenerate_gpt_response: {json_str}, error: {str(e)}")
                continue
                
        # Fallback till gamla regex-mönster om JSON-extraktion misslyckades
        if not subject or (not to_email and context_type != "email"):
            # Try pattern with brackets first for subject
            subject_match = re.search(r"{Subject:\s*(.*?)}", gpt_response, re.IGNORECASE)
            if subject_match:
                subject = subject_match.group(1).strip()
                gpt_response = gpt_response.replace(subject_match.group(0), "").strip()
            else:
                # Try pattern at beginning of text
                subject_match = re.search(r"^Subject:\s*(.*?)$", gpt_response, re.IGNORECASE | re.MULTILINE)
                if subject_match:
                    subject = subject_match.group(1).strip()
                    gpt_response = gpt_response.replace(subject_match.group(0), "").strip()
            
            # Try pattern with brackets first for email
            email_match = re.search(r"{email:\s*(.*?)}", gpt_response, re.IGNORECASE) 
            if email_match:
                extracted_email = email_match.group(1).strip()
                # Använd extraherad e-post endast om den inte är "No email found"
                # OCH om vi inte svarar på ett e-postmeddelande (där vi redan har avsändarens adress)
                if extracted_email and "no email" not in extracted_email.lower() and context_type != "email":
                    to_email = extracted_email
                gpt_response = gpt_response.replace(email_match.group(0), "").strip()
            elif context_type != "email":
                # Om vi inte kom från ett e-postmeddelande, försök hitta en e-postadress i texten
                email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', gpt_response)
                if email_match:
                    to_email = email_match.group(0)
                    
        # Logg för debugging
        logging.info(f"Filtered response (first 100 chars): {gpt_response[:100]}...")
            
        # Returnera endast GPT-svarstexten
        return jsonify({
            "response": gpt_response
        }), 200
    except Exception as e:
        logging.error(f"Error in regenerate_gpt_response: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}"}), 500


### This route is the "Compose" type of the GPT call
@app.route("/generate_gpt_from_link", methods=["POST"])
@login_required
def generate_gpt_from_link():
    try:
        data = request.get_json()
        source_content = data.get("source_content", "")
        additional_instruction = data.get("additional_instructions", "")
        
        logging.info(f"Source content length: {len(source_content)}")
        logging.info(f"Additional instruction: {additional_instruction}")
        
        if not source_content:
            return jsonify({"message": "Source content is required"}), 400
        
        # Prepare GPT prompt med instruktioner
        gpt_prompt = f"Job posting or text source:\n\n{source_content}\n\n"
        
        if additional_instruction:
            gpt_prompt += f"Additional instruction: {additional_instruction}\n\n"
        
        # Default instruktioner
        gpt_prompt += """
        Please help me draft a response to this. If this is a job opportunity, craft a personalized cover letter.
        
        If the source has an email address, please include it in the format: {email: example@example.com}
        If there's a clear subject for the response, please include it in the format: {Subject: The Subject Line}
        
        Make the response professional, personal, and compelling.
        """
        
        # Skicka till GPT för respons
        gpt_response = send_gpt_prompt(gpt_prompt, assistant_id=compose_assistant_id)
        
        # Logg för debugging
        logging.info(f"Raw GPT response: {gpt_response[:100]}...")
        
        # Försök hitta JSON-data i responsen
        subject = ""
        to_email = ""
        
        # Leta efter JSON-objekt med regex (för både vanliga och enkla citattecken)
        json_pattern = r'```json\s*({.*?})\s*```|`{.*?}`|\{.*?\}'
        json_matches = re.finditer(json_pattern, gpt_response, re.DOTALL)
        
        for match in json_matches:
            json_str = match.group(0)
            # Rensa upp JSON-strängen
            if json_str.startswith("```json"):
                json_str = re.sub(r'```json\s*(.*?)\s*```', r'\1', json_str, flags=re.DOTALL)
            elif json_str.startswith("`") and json_str.endswith("`"):
                json_str = json_str[1:-1]
                
            try:
                # Försök parsa JSON-data
                json_data = json.loads(json_str)
                logging.info(f"Successfully parsed JSON: {json_data}")
                
                # Extrahera subject och email om de finns
                if "subject" in json_data:
                    subject = json_data["subject"]
                if "email" in json_data and json_data["email"] != "No email found":
                    to_email = json_data["email"]
                    
                # Ta bort JSON-objektet från svaret
                gpt_response = gpt_response.replace(match.group(0), "").strip()
                break  # Använd första matchande JSON-objektet
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse JSON match: {json_str}, error: {str(e)}")
                continue

        # Om JSON-extraktion misslyckades, försök med de gamla regex-mönstren
        if not subject:
            # Try pattern with brackets first
            subject_match = re.search(r"{Subject:\s*(.*?)}", gpt_response, re.IGNORECASE)
            if subject_match:
                subject = subject_match.group(1).strip()
                gpt_response = gpt_response.replace(subject_match.group(0), "").strip()
            else:
                # Try pattern at beginning of text
                subject_match = re.search(r"^Subject:\s*(.*?)$", gpt_response, re.IGNORECASE | re.MULTILINE)
                if subject_match:
                    subject = subject_match.group(1).strip()
                    gpt_response = gpt_response.replace(subject_match.group(0), "").strip()
        
        if not to_email:
            # Try pattern with brackets first
            email_match = re.search(r"{email:\s*(.*?)}", gpt_response, re.IGNORECASE)
            if email_match:
                email = email_match.group(1).strip()
                to_email = "" if "no email" in email.lower() else email
                gpt_response = gpt_response.replace(email_match.group(0), "").strip()
            else:
                # Try looking for standard email pattern
                email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', gpt_response)
                if email_match:
                    to_email = email_match.group(0)
        
        # Logg för debugging efter filtrering
        logging.info(f"Extracted subject: '{subject}'")
        logging.info(f"Extracted email: '{to_email}'")
        logging.info(f"Filtered response (first 100 chars): {gpt_response[:100]}...")
        
        return jsonify({"response": gpt_response, "subject": subject, "to": to_email}), 200
    except Exception as e:
        logging.error(f"Error in generate_gpt_from_link: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}"}), 500


# Webscrape link using beautifulsoup. Save the raw, pretty and filtered html to the database
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
        logging.info(f"Attempting to save scraped content for URL: {url}")
        new_scraped_content = ScrapedContent(
            raw_html=scrape_result.get("raw_html"),
            pretty_html=scrape_result.get("pretty_html"),
            filtered_html=scrape_result.get("filtered_html"),
            scraped_url=url,
            scraped_date=scrape_result.get("scraped_date"),
        )

        db.session.add(new_scraped_content)
        db.session.commit()
        logging.info("Successfully saved scraped content to database")
        flash("Website scraped and data saved successfully!", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error while saving scraped content: {str(e)}")
        flash(f"An error occurred while saving scraped data: {str(e)}", "danger")
        return redirect(url_for("webscraping"))

    return redirect(url_for("webscraping"))


### Process HTML with webscrape assistant ###
@app.route("/process_html/<html_type>/<int:id>", methods=["POST"])
@login_required
def process_html(html_type, id):
    # Hämta HTML från databasen baserat på typen
    scraped_content = db.session.get(ScrapedContent, id)
    if not scraped_content:
        flash("Error: Content not found.", "danger")
        return redirect(url_for("webscraping"))

    html_content = getattr(scraped_content, f"{html_type}_html", None)
    if not html_content:
        flash(f"Error: {html_type.capitalize()} HTML not available.", "danger")
        return redirect(url_for("webscraping"))

    # Send HTML to GPT for processing
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


# Generate filenames for the cleaned HTMLs with the naming assistant
@app.route("/generate_filenames", methods=["POST"])
@login_required
def generate_filenames():
    try:
        # Hämta ID:n från frontend
        scraped_data_ids = request.json.get("scraped_data_ids", [])
        if not scraped_data_ids:
            return jsonify({"error": "No IDs provided"}), 400

        # Hämta skrapad data från databasen
        scraped_data = (
            db.session.query(ScrapedContent)
            .filter(ScrapedContent.id.in_(scraped_data_ids))
            .all()
        )
        if not scraped_data:
            return jsonify({"error": "No data found for provided IDs"}), 404

        filenames = []
        results = []

        for item in scraped_data:
            gpt_response = item.gpt_cleaned_html
            if not gpt_response:
                filenames.append("Unnamed.html")
                results.append({"id": item.id, "name": "Unnamed"})
                continue

            # Skicka GPT-cleaned HTML till naming-assistenten
            naming_gpt_response = process_html_with_gpt(
                gpt_response, assistant_id=naming_assistant_id
            )

            # Debug: Logga GPT-responsen
            print(f"Naming GPT response for ID {item.id}: {naming_gpt_response}")

            # Extrahera filnamnet från GPT-responsen
            match = re.search(r"listing_name\s*=\s*(\S+)", naming_gpt_response)
            if match:
                listing_name = match.group(1).strip()
                item.listing_name = listing_name
                item.generated_name = listing_name
                filenames.append(f"{listing_name}.html")
                results.append({"id": item.id, "name": listing_name})
            else:
                print(
                    f"No match found for ID {item.id} in response: {naming_gpt_response}"
                )
                filenames.append("Unnamed.html")
                results.append({"id": item.id, "name": "Unnamed"})

        # Commit till databasen
        db.session.commit()
        return jsonify({"filenames": filenames, "results": results})

    except Exception as e:
        # Debug: Logga felet
        print(f"Error in generate_filenames: {e}")
        return jsonify({"error": str(e)}), 500


### Uppdaterad save_file-route för nedladdning ###
@app.route("/save_file", methods=["GET"])
@login_required
def save_file():
    html_type = request.args.get("html_type")
    data_id = request.args.get("id")

    # Validera parametrar och html_type
    if (
        not html_type
        or not data_id
        or html_type not in ["raw", "pretty", "filtered", "gpt_cleaned"]
    ):
        flash("Invalid or missing parameters.", "danger")
        return redirect(url_for("webscraping"))

    # Hämta den sparade datan baserat på data_id
    data = db.session.get(ScrapedContent, data_id)
    if not data:
        flash("Data not found.", "danger")
        return redirect(url_for("webscraping"))

    # Välj rätt HTML-innehåll baserat på html_type
    html_content = getattr(data, f"{html_type}_html", None)
    if not html_content:
        flash(f"{html_type.capitalize()} HTML not available.", "danger")
        return redirect(url_for("webscraping"))

    # Använd listing_name eller scraped_url som fallback
    filename_base = data.listing_name or data.scraped_url
    safe_filename = re.sub(r"[^\w\-_. ]", "_", filename_base)

    try:
        # Spara filen med rätt namn och returnera den
        file_path = save_html_to_file(
            html_content,
            html_type,
            data_id,
            listing_name=safe_filename,
            save_path=save_path,
        )
        flash(f"File saved successfully as {safe_filename}.html", "success")
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"An error occurred while saving the file: {str(e)}", "danger")
        return redirect(url_for("webscraping"))


def get_data_by_id(data_id):
    return db.session.get(ScrapedContent, data_id)


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
    scraped_data = db.session.query(ScrapedContent).all()
    return render_template("webscraping.html", scraped_data=scraped_data)


@app.route("/register_company", methods=["GET", "POST"])
@login_required
def register_company_route():
    if request.method == "POST":
        return register_company()
    today = datetime.now().strftime("%Y-%m-%d")
    scraped_data = db.session.query(ScrapedContent).all()
    return render_template(
        "register_company.html", scraped_data=scraped_data, today=today
    )


@app.route("/delete_company/<int:id>", methods=["POST"])
@login_required
def delete_company_route(id):
    return delete_company(id)


@app.route("/edit_company/<int:id>", methods=["GET", "POST"])
@login_required
def edit_company_route(id):
    return edit_company(id)


@app.route("/autofill_company", methods=["POST"])
@login_required
def autofill_company():
    try:
        data_id = request.json.get("data_id")
        if not data_id:
            return jsonify({"error": "No data ID provided"}), 400

        # Get the scraped content
        scraped_content = db.session.get(ScrapedContent, data_id)
        if not scraped_content:
            return jsonify({"error": "No data found"}), 404

        # Get the content to process from gpt_cleaned_html (which contains the raw text)
        content_to_process = scraped_content.gpt_cleaned_html

        # Process with GPT to get JSON format for form filling
        gpt_response = process_html_with_gpt(
            content_to_process, autofill_assistant_id
        )

        # Clean up the response thoroughly
        gpt_response = gpt_response.strip()
        
        # Find the first { and last } to extract only the JSON part
        start = gpt_response.find("{")
        end = gpt_response.rfind("}") + 1
        if start >= 0 and end > start:
            gpt_response = gpt_response[start:end]
        else:
            raise ValueError("Could not find valid JSON in GPT response")

        # Validate that we got valid JSON back
        json.loads(gpt_response)

        return jsonify({"response": gpt_response}), 200
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON response from GPT: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/upload-job-listing", methods=["POST"])
@login_required
def upload_job_listing():
    try:
        if "job_file" not in request.files:
            flash("No file selected", "error")
            return redirect(url_for("webscraping"))

        file = request.files["job_file"]

        if file.filename == "":
            flash("No file selected", "error")
            return redirect(url_for("webscraping"))

        # Get filename without extension as listing name
        listing_name = os.path.splitext(secure_filename(file.filename))[0]

        # Read the file content
        content = file.read().decode("utf-8")

        # Create a new ScrapedContent entry - save the raw text content as is
        new_scrape = ScrapedContent(
            listing_name=listing_name,
            raw_html=content,  # Original text content
            pretty_html=content,  # Same as raw for text files
            filtered_html=content,  # Same as raw for text files
            gpt_cleaned_html=content,  # Save the raw text, will be processed during autofill
            scraped_url="file://" + secure_filename(file.filename),
            scraped_date=datetime.now(),
        )

        db.session.add(new_scrape)
        db.session.commit()

        flash("File uploaded successfully!", "success")
        return redirect(url_for("webscraping"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error uploading file: {str(e)}", "error")
        return redirect(url_for("webscraping"))


@app.route("/delete_scrape/<int:id>", methods=["POST"])
@login_required
def delete_scrape(id):
    scrape = db.session.get(ScrapedContent, id)
    if scrape:
        db.session.delete(scrape)
        db.session.commit()
        flash("Website data deleted successfully.", "success")
    return redirect(url_for("webscraping"))


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
        if not os.path.exists(database_dir):
            os.makedirs(database_dir)
        db.create_all()
    app.run(debug=True)
