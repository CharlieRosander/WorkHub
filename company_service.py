from flask import flash, request, redirect, url_for, render_template
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from schema import db, InquiredCompany
from flask import session
from webscrape_service import scrape_website
from schema import ScrapedContent
import logging


def register_company():
    if request.method == "POST":
        if "scrape_link" in request.form:
            # Redirect scraping requests to the dedicated scraping endpoint
            return redirect(url_for("scrape_job_listing"))

        # Hantera företagsregistrering (befintlig logik)
        try:
            logging.info("Attempting to register new company")
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
            logging.info(f"Company data prepared: {company_data}")

            company = InquiredCompany(**company_data)
            db.session.add(company)
            db.session.commit()
            logging.info(f"Successfully registered company: {company_data['name']}")
            flash("Company registered successfully!", "success")
        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error while registering company: {str(e)}")
            flash(
                f"An error occurred while registering the company: {str(e)}", "danger"
            )
        except Exception as e:
            db.session.rollback()
            logging.error(f"Unexpected error while registering company: {str(e)}")
            flash(f"An unexpected error occurred: {str(e)}", "danger")
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
