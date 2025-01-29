import requests
from datetime import datetime
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import time
from random import uniform
import logging

# Constants for scraping configuration
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}
MIN_DELAY = 1  # Minimum delay between requests in seconds
MAX_DELAY = 3  # Maximum delay between requests in seconds
TIMEOUT = 10  # Request timeout in seconds

# Keep track of last request time per domain
last_request_time = {}


def respect_rate_limits(domain):
    """Implement rate limiting for each domain"""
    current_time = time.time()
    if domain in last_request_time:
        elapsed = current_time - last_request_time[domain]
        delay = uniform(MIN_DELAY, MAX_DELAY)
        if elapsed < delay:
            time.sleep(delay - elapsed)

    last_request_time[domain] = time.time()


def scrape_website(url):
    try:
        # Parse the URL and get the base domain
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        # Check robots.txt
        rp = RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        try:
            rp.read()
        except Exception as e:
            # If robots.txt is unavailable, proceed with caution
            logging.warning(f"Could not fetch robots.txt for {base_url}: {str(e)}")

        # Check if we're allowed to fetch the URL
        if rp.can_fetch("*", url) is False:
            return {
                "error": "This URL cannot be scraped according to the site's robots.txt rules"
            }

        # Implement rate limiting
        respect_rate_limits(parsed_url.netloc)

        # Make the request with proper headers and timeout
        response = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )

        # Check for non-HTML content
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return {"error": f"URL returned non-HTML content: {content_type}"}

        # Check response status
        if response.status_code == 429:
            return {"error": "Rate limit exceeded. Please try again later."}
        elif response.status_code != 200:
            return {
                "error": f"Failed to retrieve page. Status code: {response.status_code}"
            }

        # Check response size
        if len(response.content) > 10 * 1024 * 1024:  # 10MB limit
            return {"error": "Response too large (>10MB)"}

        raw_html = response.text
        soup = BeautifulSoup(raw_html, "html.parser")

        # Remove unwanted elements that might contain private data
        for element in soup.find_all(["script", "style", "meta", "input", "button"]):
            element.decompose()

        pretty_html = soup.prettify()
        filtered_html = "\n".join(
            tag.text.strip() for tag in soup.find_all(True) if tag.text.strip()
        )

        return {
            "raw_html": raw_html,
            "pretty_html": pretty_html,
            "filtered_html": filtered_html,
            "scraped_date": datetime.now(),
        }

    except requests.Timeout:
        return {"error": "Request timed out. The site might be slow or unavailable."}
    except requests.ConnectionError:
        return {
            "error": "Failed to connect to the website. Please check the URL and try again."
        }
    except Exception as e:
        return {"error": str(e)}


def save_html_to_file(html_content, html_type, id, listing_name=None, save_path=None):
    try:
        # Om inget save_path ges, skapa en säker filväg i 'downloads'
        os.makedirs("downloads", exist_ok=True)

        # Använd listing_name för filnamn
        safe_listing_name = re.sub(
            r"[^\w\-_. ]", "_", listing_name if listing_name else "Unnamed"
        )
        filename = f"{safe_listing_name}_{html_type}.html"

        # Fullständig sökväg för filen
        file_path = os.path.join("downloads", filename)

        # Skriv HTML-innehållet till filen, save-path är satt men används inte här ännu, persmissions needed etc
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(html_content)

        return file_path
    except Exception as e:
        raise Exception(f"An error occurred while saving the file: {str(e)}")
