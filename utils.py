import json
import logging
import re
from uuid import uuid4

import feedparser
import markdownify
import pandas as pd

logger = logging.getLogger(__name__)


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

            news_items.append(news_item)

    return news_items


def save_to_csv(news_items: list[dict], filename: str = "news_data.csv") -> None:
    df = pd.DataFrame(news_items)
    df.to_csv(filename, index=False)


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


def generate_article_text(articles: list[dict], df: pd.DataFrame) -> str:
    parts = []
    for article in articles:
        row = df.loc[article["uuid"]]
        parts.append(f"{row['headline']}\n{row['content']}")
    return "\n\n".join(parts)


def generate_article_links(articles: list[dict], df: pd.DataFrame) -> str:
    lines = []
    for article in articles:
        row = df.loc[article["uuid"]]
        lines.append(f"* [{row['source']}：{row['headline']}]({row['url']})")
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
