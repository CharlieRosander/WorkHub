import requests
from datetime import datetime
from bs4 import BeautifulSoup
import os
import re


def scrape_website(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            raw_html = response.text  # Raw HTML as it is
            soup = BeautifulSoup(raw_html, "html.parser")
            pretty_html = soup.prettify()  # Cleaned/Prettified HTML
            filtered_html = "\n".join(
                tag.text.strip() for tag in soup.find_all(True) if tag.text.strip()
            )
            return {
                "raw_html": raw_html,
                "pretty_html": pretty_html,
                "filtered_html": filtered_html,
                "scraped_date": datetime.now(),
            }
        else:
            return {
                "error": f"Failed to retrieve page. Status code: {response.status_code}"
            }
    except Exception as e:
        return {"error": str(e)}


def save_html_to_file(html_content, html_type, id, listing_name=None, save_path=None):
    """
    Sparar HTML-innehåll till en fil och returnerar filens sökväg.

    :param html_content: Innehållet som ska sparas.
    :param html_type: Typ av HTML (raw, pretty, filtered, gpt_cleaned).
    :param id: ID för det relaterade innehållet.
    :param listing_name: Namnet som ska användas för filnamnet (från GPT).
    :param save_path: Anpassad sökväg för filen (valfritt).
    :return: Filens sökväg.
    """
    try:
        # Om inget save_path ges, skapa en säker filväg i 'downloads'
        os.makedirs("downloads", exist_ok=True)

        # Använd listing_name för filnamn (eller "Unnamed" om inget finns)
        safe_listing_name = re.sub(
            r"[^\w\-_. ]", "_", listing_name if listing_name else "Unnamed"
        )
        filename = f"{safe_listing_name}_{html_type}.html"

        # Fullständig sökväg för filen
        file_path = os.path.join("downloads", filename)

        # Skriv HTML-innehållet till filen
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(html_content)

        return file_path
    except Exception as e:
        raise Exception(f"An error occurred while saving the file: {str(e)}")
