import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

import dotenv
import pandas as pd

import gemini
from gemini import MODEL
from utils import (
    generate_article_text,
    generate_article_links,
    deduplicate_articles_by_url,
    append_summary_and_links,
    extract_news_data,
    save_to_csv,
)
from substack_api import publish_substack_post, verify_auth, SubstackAuthError

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

TEMP_DIR = Path("temp")
DATA_DIR = Path("data")
ARTICLES_PATH = DATA_DIR / "articles.jsonl"

# List of RSS feed URLs
RSS_FEEDS: dict[str, str] = {
    "集誌社": "https://thecollectivehk.com/feed/",
    "法庭線": "https://thewitnesshk.com/feed/",
    "庭刊": "https://hkcourtnews.com/feed/",
    "獨立媒體": "https://www.inmediahk.net/rss.xml",
    "Yahoo 港聞": "https://hk.news.yahoo.com/rss/hong-kong/",
    "Yahoo 財經": "https://hk.news.yahoo.com/rss/business/",
}

BEST_OF_OPTION = 1
NUMBER_OF_TOPICS = 5
MAX_LINKS_PER_TOPIC = 5


def _save_json(path: Path, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_articles(rss_feeds: dict[str, str]) -> pd.DataFrame:
    """Load articles from accumulated JSONL, falling back to fresh RSS fetch."""
    TEMP_DIR.mkdir(exist_ok=True)

    if ARTICLES_PATH.exists():
        logger.info("Reading accumulated articles from %s", ARTICLES_PATH)
        df = pd.read_json(ARTICLES_PATH, lines=True)
    else:
        logger.info("No JSONL found, fetching fresh from RSS")
        news_data = extract_news_data(rss_feeds)
        df = pd.DataFrame(news_data)
        # Write JSONL for future use
        DATA_DIR.mkdir(exist_ok=True)
        with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
            for item in news_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Save CSV for debugging
    csv_filepath = TEMP_DIR / "news_data.csv"
    df.to_csv(csv_filepath, index=False)

    df.set_index("uuid", inplace=True)
    df.published = pd.to_datetime(df.published, utc=True)
    today = pd.Timestamp.today()
    week_ago = pd.Timestamp(today - pd.Timedelta(days=7)).tz_localize("UTC")
    df = df[df.published > week_ago]

    # Drop fetched_at if present — downstream doesn't need it
    if "fetched_at" in df.columns:
        df = df.drop(columns=["fetched_at"])

    return df


def generate_digest(df: pd.DataFrame, n_topics: int) -> tuple[str, str]:
    """Run topic generation -> summary -> subedit pipeline, return markdown."""
    topics = gemini.generate_topics(df[["headline", "summary"]], n_topics)
    articles_grouped_by_topic = gemini.generate_articles_list_by_topic(
        topics, df[["headline", "summary"]]
    )

    _save_json(TEMP_DIR / "01-topics.json", topics)
    _save_json(TEMP_DIR / "02-articles_by_topic.json", articles_grouped_by_topic)

    topics_summary: dict[str, list] = {"topics": []}
    topics_link: list[dict] = []

    for topic in articles_grouped_by_topic["topics"]:
        if topic["topic"].lower() != "others" and topic["topic"] != "其他":
            articles = topic["articles"]
            articles_text = generate_article_text(articles, df)
            topics_summary["topics"].append(
                gemini.topic_summary(topic["topic"], articles_text)
            )
            unique_articles = deduplicate_articles_by_url(articles, df)
            selected_articles = gemini.select_representative_articles(
                topic["topic"], unique_articles, df, MAX_LINKS_PER_TOPIC
            )
            articles_links = generate_article_links(selected_articles, df)
            topics_link.append({"topic": topic, "link": articles_links})

    formatted_summary = gemini.subedit_summary(topics_summary)

    _save_json(TEMP_DIR / "03-topics_summary.json", formatted_summary)
    _save_json(TEMP_DIR / "04-topics_link.json", topics_link)

    pre_edited_text = append_summary_and_links(topics_summary, topics_link)
    edited_text = append_summary_and_links(formatted_summary, topics_link)

    return edited_text, pre_edited_text


def run_pipeline(draft_only: bool = False) -> None:
    """Main entry point: load articles, generate digest, publish."""
    logging.basicConfig(level=logging.INFO)

    try:
        verify_auth()
    except SubstackAuthError as e:
        logger.error("Substack auth preflight failed: %s", e)
        print(
            "ERROR: Substack authentication failed — SUBSTACK_SID cookie likely expired. "
            "Please rotate.",
            file=sys.stderr,
        )
        sys.exit(2)

    df = load_articles(RSS_FEEDS)

    digest_candidates: list[dict] = []

    for i in range(1, BEST_OF_OPTION + 1):
        logger.info("Generating try %d of %d", i, BEST_OF_OPTION)

        edited_text, pre_edited_text = generate_digest(df, NUMBER_OF_TOPICS)
        digest_candidates.append({"summary_id": i, "text": edited_text})

        (TEMP_DIR / f"summary-{i}_pre_edited.md").write_text(pre_edited_text)
        (TEMP_DIR / f"summary-{i}_edited.md").write_text(edited_text)

    _save_json(TEMP_DIR / "05-final_text.json", digest_candidates)

    best_score = gemini.evaluate_output(BEST_OF_OPTION, digest_candidates)
    _save_json(TEMP_DIR / "06-score.json", best_score)

    earliest = df.published.min()
    latest = df.published.max()
    now = datetime.now()
    publish_substack_post(
        title=f"{now.year}年{now.month}月{now.day}日 香港每週新聞摘要",
        subtitle=f"本期涵蓋 {earliest.month}月{earliest.day}日 至 {latest.month}月{latest.day}日 的新聞。本新聞摘要由 {MODEL} 自動生成。",
        content=digest_candidates[best_score["summary_id"] - 1]["text"],
        draft_only=draft_only,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and publish HK news digest")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create a Substack draft without publishing or emailing",
    )
    args = parser.parse_args()
    run_pipeline(draft_only=args.draft)
