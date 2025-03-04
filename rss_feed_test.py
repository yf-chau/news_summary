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


# Example usage with the URLs you found and some others to test:
feed_urls_to_test = [
    "https://hk.news.yahoo.com/rss/",
    "https://hk.news.yahoo.com/rss/hong-kong/",
    "https://hk.news.yahoo.com/rss/business",
    "https://hk.news.yahoo.com/rss/world/",
    "https://hk.news.yahoo.com/rss/politics/",
    "https://hk.news.yahoo.com/rss/entertainment/",
    "https://hk.news.yahoo.com/rss/sports/",
    "https://hk.news.yahoo.com/rss/tech/",
    "https://hk.news.yahoo.com/rss/style/",
    "https://hk.news.yahoo.com/rss/food/",
    "https://hk.news.yahoo.com/rss/travel/",
    "https://hk.news.yahoo.com/rss/video/",
    "https://hk.news.yahoo.com/rss/local/",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss",  # A known valid RSS feed (NASA)
    "https://www.theregister.com/headlines/feed.xml",  # Another valid RSS feed (The Register)
    "https://www.example.com",  # A URL that is NOT an RSS feed
    "invalid-url",  # An invalid URL
]

# Example usage with the URLs you found and some others to test:
feed_urls_list = [
    # Using /rss/ pattern:
    [
        "https://hk.news.yahoo.com/rss/world/",
        "https://hk.news.yahoo.com/rss/politics/",
        "https://hk.news.yahoo.com/rss/entertainment/",
        "https://hk.news.yahoo.com/rss/sports/",
        "https://hk.news.yahoo.com/rss/tech/",
        "https://hk.news.yahoo.com/rss/style/",
        "https://hk.news.yahoo.com/rss/food/",
        "https://hk.news.yahoo.com/rss/travel/",
        "https://hk.news.yahoo.com/rss/video/",
        "https://hk.news.yahoo.com/rss/local/",
        "https://hk.news.yahoo.com/rss/tv/",
    ],
    # Using /rss pattern (no trailing slash):
    [
        "https://hk.news.yahoo.com/business",
        "https://hk.news.yahoo.com/world",
        "https://hk.news.yahoo.com/politics",
        "https://hk.news.yahoo.com/entertainment",
        "https://hk.news.yahoo.com/sports",
        "https://hk.news.yahoo.com/tech",
        "https://hk.news.yahoo.com/style",
        "https://hk.news.yahoo.com/food",
        "https://hk.news.yahoo.com/travel",
        "https://hk.news.yahoo.com/video",
        "https://hk.news.yahoo.com/local",
    ],
    # Using /feed/ pattern:
    [
        "https://hk.news.yahoo.com/feed/tv/",
        "https://hk.news.yahoo.com/feed/style/",
        "https://hk.news.yahoo.com/feed/food/",
        "https://hk.news.yahoo.com/feed/travel/",
        "https://hk.news.yahoo.com/feed/local/",
        "https://hk.news.yahoo.com/feed/world/",
        "https://hk.news.yahoo.com/feed/politics/",
        "https://hk.news.yahoo.com/feed/finance/",
        "https://hk.news.yahoo.com/feed/movie/",
        "https://hk.news.yahoo.com/feed/movies/",
        "https://hk.news.yahoo.com/feed/sports/",
        "https://hk.news.yahoo.com/feed/tech/",
        "https://hk.news.yahoo.com/feed/lifestyle/",
        "https://hk.news.yahoo.com/feed/health/",
    ],
    # Using /feed pattern (no trailing slash):
    [
        "https://hk.news.yahoo.com/feed/tv",
        "https://hk.news.yahoo.com/feed/style",
        "https://hk.news.yahoo.com/feed/food",
        "https://hk.news.yahoo.com/feed/travel",
        "https://hk.news.yahoo.com/feed/local",
        "https://hk.news.yahoo.com/feed/world",
        "https://hk.news.yahoo.com/feed/politics",
        "https://hk.news.yahoo.com/feed/finance",
        "https://hk.news.yahoo.com/feed/movie",
        "https://hk.news.yahoo.com/feed/movies",
        "https://hk.news.yahoo.com/feed/sports",
        "https://hk.news.yahoo.com/feed/tech",
        "https://hk.news.yahoo.com/feed/lifestyle",
        "https://hk.news.yahoo.com/feed/health",
    ],
    # Using .xml or .rss.xml endings (less likely):
    [
        "https://hk.news.yahoo.com/rss.xml",
        "https://hk.news.yahoo.com/hong-kong/rss.xml",
        "https://hk.news.yahoo.com/business/rss.xml",
        "https://hk.news.yahoo.com/world/rss.xml",
        "https://hk.news.yahoo.com/entertainment/rss.xml",
        "https://hk.news.yahoo.com/sports/rss.xml",
        "https://hk.news.yahoo.com/tech/rss.xml",
        "https://hk.news.yahoo.com/style/rss.xml",
        "https://hk.news.yahoo.com/food/rss.xml",
        "https://hk.news.yahoo.com/travel/rss.xml",
        "https://hk.news.yahoo.com/feed.xml",
        "https://hk.news.yahoo.com/hong-kong/feed.xml",
        "https://hk.news.yahoo.com/business/feed.xml",
        "https://hk.news.yahoo.com/world/feed.xml",
        "https://hk.news.yahoo.com/entertainment/feed.xml",
        "https://hk.news.yahoo.com/sports/feed.xml",
        "https://hk.news.yahoo.com/tech/feed.xml",
        "https://hk.news.yahoo.com/style/feed.xml",
        "https://hk.news.yahoo.com/feed/food.xml",
        "https://hk.news.yahoo.com/feed/travel.xml",
    ],
]

# Flatten the list of lists into a single list:
all_feed_urls = [url for sublist in feed_urls_list for url in sublist]

valid_rss_feeds = []  # List to store valid RSS feed URLs

for url in all_feed_urls:
    if is_valid_rss_feed(url):
        print(f"✅ URL '{url}' is likely a valid RSS feed.")
        valid_rss_feeds.append(url)  # Add valid URL to the list
    else:
        print(f"❌ URL '{url}' is NOT a valid RSS feed.")
    print("-" * 30)

# Output all valid RSS feeds at the end
print("Valid RSS Feeds:")
for valid_url in valid_rss_feeds:
    print(valid_url)
