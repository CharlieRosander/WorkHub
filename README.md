# WorkHub (placeholder name), a Web-Based Application for Email and Job Management

This application is a Flask-based solution for managing emails, job postings, and company records. It integrates Google OAuth and GPT to automate email processing and other data-related tasks.

This is a hobby/passion-project born out of my desire for streamlining, automating, and enhancing aspects of the job-hunting process. It also serves as an exploration of AI's potential in tackling these tasks and as an opportunity to expand my knowledge and skills.

The goal is to create a comprehensive, all-in-one platform for everything related to job searching. 

Currently a work in progress, right now for my own personal use.
## Features

- **GPT-assistants**: 
  - Utilizing multiple OpenAI GPT assistants, each tailored to handle specific tasks and provide responses in predefined, controlled formats for streamlined processing and further handling.
  - Leverage GPT assistants with access to related documents, certifications, and other personal resources to provide more context-aware and informed responses.
- **User Management**: 
  - User registration and login with password or Google OAuth. 
    - (Plans to only use OAuth in the future, other methods seems reduntant right now)
- **Email Management**:
  - Send and view Gmail messages.
  - Generate drafts for specific purposes, such as follow-ups, responses, or composing emails from source material (e.g., job listings, web pages).
  - Regenerate responses or add additional instructions if the draft is not to your liking.
  - Auto-fill recipient and subject fields using relevant context.
- **Job Postings**:
  - Web scraping of job listings and storing structured HTML data in the database.
  - Automated cleaning and formatting of scraped content using a GPT-assistant, currently used to replicate job listings for storage in the database or on disk, but easily modifiable for other use cases.
  - Optional automated file naming for scraped content using a GPT-assistant, streamlining the process and saving files to disk.
  - View the scraped content directly on the platform (ex. the replicated job-listing)
- **Company Records**:
  - Add, edit, and delete companies related to job applications.
  - Autofill-function for registering companies, using GPT-assistant to extract relevant information from job postings based on the scraped&cleaned HTML.
  - View and edit company details, including name, address, and contact information.
  - View stats on registered companies, such as total applications, unique industries, and locations.

## Technical Overview

### Frontend
- HTML5, CSS, JavaScript
### Backend

- **Language**: Python (Flask)
- **Database**: SQLite using SQLAlchemy
- **API Integrations**:
  - Google Gmail API for email management.
  - OpenAI GPT API for text processing.

## Notes

This project is just the beginning, with much more planned and an abundance of possibilities to explore and expand upon.

### Future Features and Ideas
- **Auto-logging of Applications**: Automatically record and track companies you've applied to.
- **Expanded API Integrations**: Add support for more platforms, ex. LinkedIn? Canvas for CV-related stuff?
- **Backend GPT Management**: Shift GPT-assistant functionality to the backend, enabling users to prompt, instruct, and manage assistants directly, offering greater flexibility and control.
- **Complete Overhaul of the Frontend**: Redesign and improve the user interface for a more intuitive, modern, and responsive experience.
