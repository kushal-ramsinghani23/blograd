from urllib.parse import urlparse
from ..models.website import Website

def validate_website(website):
    if not website.get("name"): return False, "Name is not present"
    if not website.get("url"): return False, "URL is not present"

    url = website.get("url")

    result = urlparse(url)
    if result.scheme == "" or result.netloc == "":
        return False, "URL is not valid"

    website_in_db = Website.query.filter_by(url=url).first()
    if website_in_db: return False, "URL already exists"

    return True, None
