import json
import markdownify
import re
from uuid import uuid4
import feedparser
import pandas as pd


def extract_news_data(rss_feeds):
    news_items = []
    for feed_title, feed_url in rss_feeds.items():
        print(f"Extracting news data from {feed_title}...")

        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            # print("====================================")
            # print("Summary")
            # print("===============================")
            # print(entry.get("summary"))

            # print("====================================")
            # print("Marked down summary")
            # print("===============================")
            # print(html_to_markdown(entry.get("summary", "")))

            # print("====================================")
            # print("Content")
            # print("===============================")
            # print(html_to_markdown(entry.get("content", [{}])[0].get("value")))
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
                "image_links": None,
                "source": feed.feed.get("title"),
                "categories": ", ".join(
                    tag["term"] for tag in entry.get("tags", []) if "term" in tag
                ),
            }

            news_items.append(news_item)

    return news_items


# Function to save news data to a CSV file
def save_to_csv(news_items, filename="news_data.csv"):
    df = pd.DataFrame(news_items)
    df.to_csv(filename, index=False)


def html_to_markdown(html_content):
    if not html_content:
        return ""

    markdown_text = markdownify.markdownify(html_content)

    # Remove markdown links and excessive newlines
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
    markdown_text = re.sub(r"\[([^\]]*)]\([^)]*\)", r"\1", markdown_text)

    if "【獨媒報導】" in markdown_text:
        markdown_text = markdown_text.split("【獨媒報導】", 1)[1].strip()

    return markdown_text


def generate_article_text(articles, df) -> str:
    article_text = ""
    for article in articles:
        article_headline = df.loc[article["uuid"]]["headline"]
        article_content = df.loc[article["uuid"]]["content"]
        article_text += f"{article_headline}\n{article_content}\n\n"
    return article_text


def generate_article_links(articles, df) -> str:
    article_hyperlink_in_markdown = ""
    for article in articles:
        article_headline = df.loc[article["uuid"]]["headline"]
        article_link = df.loc[article["uuid"]]["url"]
        article_source = df.loc[article["uuid"]]["source"]
        article_hyperlink_in_markdown += (
            f"* [{article_source}：{article_headline}]({article_link})\n"
        )
    return article_hyperlink_in_markdown


def append_summary_and_links(formatted_summary: dict, topics_link: list) -> str:
    full_text = ""
    formatted_summary_list = formatted_summary["topics"]
    for summary, link in zip(formatted_summary_list, topics_link):
        full_text += "## " + summary["topic"] + "\n\n"
        full_text += summary["summary"]
        full_text += "\n\n"
        full_text += "#### Links\n\n"
        full_text += link["link"]
        full_text += "\n\n"

    return full_text


def extract_json_to_dict(text: str) -> dict | None:
    """
    Extracts the JSON string from a markdown code block using string methods.

    Args:
        text (str): The input string containing a markdown code block.

    Returns:
        str or None: The raw JSON string if found; otherwise, None.
    """
    # Split the text at the starting marker "```json"
    _, marker, after = text.partition("```json")
    if not marker:
        return None  # starting marker not found

    # Now split the remainder at the closing marker "```"
    json_content, _, _ = after.partition("```")
    return json.loads(json_content.strip())
