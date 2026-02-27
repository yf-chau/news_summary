import requests
import xml.etree.ElementTree as ET


def is_valid_rss_feed(url):
    """
    Checks if a given URL is a valid RSS feed.

    Args:
        url: The URL to check (string).

    Returns:
        True if the URL is likely a valid RSS feed, False otherwise (boolean).
    """
    try:
        response = requests.get(
            url, stream=True, timeout=10
        )  # stream=True for efficiency, timeout for safety
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        # Check Content-Type header (optional but good practice)
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            "xml" not in content_type
            and "rss+xml" not in content_type
            and "application/rss" not in content_type
        ):
            print(f"Warning: Content-Type is not XML-like: {content_type}")
            # Continue anyway, as some servers might not set it correctly

        # Attempt to parse as XML
        xml_content = response.text
        root = ET.fromstring(xml_content)

        # Check for root element <rss> and <channel>
        if root.tag.lower() == "rss" and root.find("channel") is not None:
            return True
        else:
            print("Error: Not a valid RSS structure (missing <rss> or <channel>).")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Error: Request failed for URL {url} - {e}")
        return False
    except ET.ParseError as e:
        print(f"Error: XML ParseError for URL {url} - {e}")
        return False
    except Exception as e:
        print(f"Error: An unexpected error occurred for URL {url} - {e}")
        return False


if __name__ == "__main__":
    feed_urls_to_test = [
        "https://hk.news.yahoo.com/rss/",
        "https://hk.news.yahoo.com/rss/hong-kong/",
        "https://hk.news.yahoo.com/rss/world/",
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.example.com",
    ]

    valid_rss_feeds = []
    for url in feed_urls_to_test:
        if is_valid_rss_feed(url):
            print(f"VALID: {url}")
            valid_rss_feeds.append(url)
        else:
            print(f"INVALID: {url}")
        print("-" * 30)

    print("\nValid RSS Feeds:")
    for valid_url in valid_rss_feeds:
        print(valid_url)
