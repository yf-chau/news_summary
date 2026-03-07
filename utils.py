import json
import logging
import re
import warnings
from uuid import uuid4

import feedparser
import markdownify
import pandas as pd
import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

MIN_CONTENT_LENGTH = 100


def _scrape_article(url: str) -> str:
    """Fetch article page and extract body text as markdown."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        article = soup.find("article") or soup.find("body")
        if article is None:
            return ""
        for tag in article.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return html_to_markdown(str(article))
    except Exception as e:
        logger.warning("Failed to scrape %s: %s", url, e)
        return ""


def extract_news_data(rss_feeds: dict[str, str]) -> list[dict]:
    news_items = []
    for feed_title, feed_url in rss_feeds.items():
        logger.info("Extracting news data from %s...", feed_title)

        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            news_item = {
                "uuid": uuid4().hex,
                "headline": entry.get("title"),
                "published": entry.get("published"),
                "summary": html_to_markdown(entry.get("summary", ""))[:300],
                "content": html_to_markdown(
                    entry.get("content", [{"value": entry.get("summary", "")}])[0].get(
                        "value"
                    )
                ),
                "url": entry.get("link"),
                "source": feed.feed.get("title"),
            }

            if len(news_item["content"]) < MIN_CONTENT_LENGTH and news_item["url"]:
                scraped = _scrape_article(news_item["url"])
                if scraped:
                    news_item["content"] = scraped

            news_items.append(news_item)

    return news_items


def html_to_markdown(html_content: str) -> str:
    if not html_content:
        return ""

    markdown_text = markdownify.markdownify(html_content)

    # Remove markdown links and excessive newlines
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
    markdown_text = re.sub(r"\[([^\]]*)]\([^)]*\)", r"\1", markdown_text)

    if "【獨媒報導】" in markdown_text:
        markdown_text = markdown_text.split("【獨媒報導】", 1)[1].strip()

    return markdown_text


def generate_article_text(articles: list[str], df: pd.DataFrame) -> str:
    parts = []
    for uuid in articles:
        row = df.loc[uuid]
        parts.append(f"{row['headline']}\n{row['content']}")
    return "\n\n".join(parts)


def deduplicate_articles_by_url(articles: list[str], df: pd.DataFrame) -> list[str]:
    """Remove duplicate articles that share the same URL."""
    seen_urls: set[str] = set()
    unique: list[str] = []
    for uuid in articles:
        url = df.loc[uuid, "url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append(uuid)
    return unique


def generate_article_links(articles: list[str], df: pd.DataFrame) -> str:
    lines = []
    for uuid in articles:
        row = df.loc[uuid]
        lines.append(f"[{row['source']}：{row['headline']}]({row['url']})")
    return "\n".join(lines)


def append_summary_and_links(formatted_summary: dict, topics_link: list[dict]) -> str:
    sections = []
    for summary, link in zip(formatted_summary["topics"], topics_link):
        sections.append(
            f"## {summary['topic']}\n\n"
            f"{summary['summary']}\n\n"
            f"#### Links\n\n"
            f"{link['link']}"
        )
    return "\n\n".join(sections)


def extract_json_to_dict(text: str) -> dict | None:
    """Extract a JSON object from a markdown ```json code block."""
    _, marker, after = text.partition("```json")
    if not marker:
        return None

    json_content, _, _ = after.partition("```")
    return json.loads(json_content.strip())
