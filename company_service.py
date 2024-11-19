from flask import flash, request, redirect, url_for, render_template
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from schema import db, InquiredCompany
from flask import session
from webscrape_service import scrape_website
from schema import ScrapedContent


def register_company():
    if request.method == "POST":
        if "scrape_link" in request.form:
            url = request.form.get("scrape_link")
            if not url:
                flash("Please provide a valid URL.")
            else:
                scrape_result = scrape_website(url)
                if "error" in scrape_result:
                    flash(scrape_result["error"])
                else:
                    # Spara resultatet i databasen
                    try:
                        scraped_content = ScrapedContent(
                            raw_html=scrape_result.get("raw_html"),
                            pretty_html=scrape_result.get("pretty_html"),
                            filtered_html=scrape_result.get("filtered_html"),
                            scraped_url=url,
                        )
                        db.session.add(scraped_content)
                        db.session.commit()
                        flash("Website scraped and saved successfully!")
                    except SQLAlchemyError as e:
                        db.session.rollback()
                        flash(f"An error occurred while saving: {str(e)}")
            return redirect(url_for("register_company_route"))

        # Hantera företagsregistrering (befintlig logik)
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
        return redirect(url_for("register_company_route"))

    # Skicka data till frontend (om tillämpligt)
    scraped_data = ScrapedContent.query.all()
    return render_template("register_company.html", scraped_data=scraped_data)


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


def edit_company(id):
    company = db.session.get(InquiredCompany, id)
    if request.method == "POST":
        try:
            company.name = request.form["name"]
            company.date_applied = (
                datetime.strptime(request.form.get("date_applied"), "%Y-%m-%d")
                if request.form.get("date_applied")
                else company.date_applied
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
