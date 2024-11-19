import requests
from bs4 import BeautifulSoup


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
            }
        else:
            return {
                "error": f"Failed to retrieve page. Status code: {response.status_code}"
            }
    except Exception as e:
        return {"error": str(e)}


import os


def save_html_to_file(html_content, html_type, id, save_path=None):
    """
    Sparar HTML-innehåll till en fil och returnerar filens sökväg.

    :param html_content: Innehållet som ska sparas.
    :param html_type: Typ av HTML (raw, pretty, filtered, gpt_cleaned).
    :param id: ID för det relaterade innehållet.
    :param save_path: Anpassad sökväg för filen.
    :return: Filens sökväg.
    """
    try:
        # Skapa anpassad sökväg eller använd standard
        if not save_path:
            os.makedirs("downloads", exist_ok=True)
            filename = f"{html_type}_html_{id}.html"
            save_path = os.path.join("downloads", filename)

        # Spara innehållet till filen
        with open(save_path, "w", encoding="utf-8") as file:
            file.write(html_content)

        return save_path
    except Exception as e:
        raise Exception(f"An error occurred while saving the file: {str(e)}")

