from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String

db = SQLAlchemy()


class InquiredCompany(db.Model):
    __tablename__ = "inquired_companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    location = db.Column(db.String(255))
    industry = db.Column(db.String(255))
    contact_person = db.Column(db.String(255))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(255))
    date_applied = db.Column(db.Date)
    link = db.Column(db.String(255))


class User(db.Model):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String(150))
    email = Column(String(150), unique=True, nullable=False)
    password = Column(String(255), nullable=False)


class ScrapedContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raw_html = db.Column(db.Text, nullable=False)
    pretty_html = db.Column(db.Text, nullable=False)
    filtered_html = db.Column(db.Text)
    gpt_cleaned_html = db.Column(db.Text)
    scraped_url = db.Column(db.String(255), nullable=False)
