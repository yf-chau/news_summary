import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import dotenv
import pandas as pd

import gemini
from gemini import MODEL
from utils import (
    generate_article_text,
    generate_article_links,
    generate_english_article_links,
    deduplicate_articles_by_url,
    append_summary_and_links,
    append_summary_and_links_en,
    extract_news_data,
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
    "SCMP": "https://www.scmp.com/rss/2/feed/",
    "HKFP": "https://hongkongfp.com/feed",
}

ENGLISH_SOURCES = {"SCMP", "HKFP"}

BEST_OF_OPTION = 1
NUMBER_OF_TOPICS = 5
MAX_LINKS_PER_TOPIC = 5


def _save_json(path: Path, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_articles(
    rss_feeds: dict[str, str],
    english_sources: set[str] | None = None,
) -> pd.DataFrame:
    """Load articles from accumulated JSONL, falling back to fresh RSS fetch."""
    TEMP_DIR.mkdir(exist_ok=True)

    if ARTICLES_PATH.exists():
        logger.info("Reading accumulated articles from %s", ARTICLES_PATH)
        df = pd.read_json(ARTICLES_PATH, lines=True)
        # Backfill language field for older articles without it
        if "language" not in df.columns:
            df["language"] = "zh"
    else:
        logger.info("No JSONL found, fetching fresh from RSS")
        news_data = extract_news_data(rss_feeds, english_sources=english_sources)
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


def _process_topic(topic_name: str, articles: list[str], df: pd.DataFrame) -> tuple[dict, dict]:
    """Process a single topic: generate summary and select representative links."""
    articles_text = generate_article_text(articles, df)
    summary = gemini.topic_summary(topic_name, articles_text)
    unique_articles = deduplicate_articles_by_url(articles, df)
    selected = gemini.select_representative_articles(
        topic_name, unique_articles, df, MAX_LINKS_PER_TOPIC
    )
    links = generate_article_links(selected, df)
    return summary, {"topic": {"topic": topic_name, "articles": articles}, "link": links}


def generate_digest(df: pd.DataFrame, n_topics: int) -> tuple[str, str, dict, list]:
    """Run topic generation -> summary -> subedit pipeline, return markdown + intermediates."""
    topics = gemini.generate_topics(df[["headline", "summary"]], n_topics)
    articles_grouped_by_topic = gemini.generate_articles_list_by_topic(
        topics, df[["headline", "summary"]]
    )

    _save_json(TEMP_DIR / "01-topics.json", topics)
    _save_json(TEMP_DIR / "02-articles_by_topic.json", articles_grouped_by_topic)

    topics = articles_grouped_by_topic["topics"]

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_process_topic, t["topic"], t["articles"], df): i
            for i, t in enumerate(topics)
        }
        results = [None] * len(topics)
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    topics_summary = {"topics": [r[0] for r in results]}
    topics_link = [r[1] for r in results]

    formatted_summary = gemini.subedit_summary(topics_summary)

    _save_json(TEMP_DIR / "03-topics_summary.json", formatted_summary)
    _save_json(TEMP_DIR / "04-topics_link.json", topics_link)

    pre_edited_text = append_summary_and_links(topics_summary, topics_link)
    edited_text = append_summary_and_links(formatted_summary, topics_link)

    return edited_text, pre_edited_text, formatted_summary, topics_link


def generate_english_digest(
    formatted_summary_zh: dict,
    topics_link_zh: list[dict],
    df: pd.DataFrame,
) -> str:
    """Translate Chinese digest to English, grounding proper nouns on English sources."""
    df_en = df[df["language"] == "en"] if "language" in df.columns else pd.DataFrame()

    # Match English articles to the same topics
    if not df_en.empty:
        topic_names = [t["topic"] for t in formatted_summary_zh["topics"]]
        en_matched = gemini.match_english_articles_to_topics(
            topic_names, df_en[["headline", "summary"]]
        )
        _save_json(TEMP_DIR / "07-en_articles_by_topic.json", en_matched)
    else:
        en_matched = {"topics": [{"topic": t["topic"], "articles": []} for t in formatted_summary_zh["topics"]]}

    # Build English reference text per topic for grounding (index-based)
    en_articles_by_index: list[list[str]] = [t["articles"] for t in en_matched["topics"]]

    # Translate digest to English
    en_reference_texts = {}
    for i, uuids in enumerate(en_articles_by_index):
        valid_uuids = [u for u in uuids if u in df.index]
        if valid_uuids:
            topic_name = formatted_summary_zh["topics"][i]["topic"]
            en_reference_texts[topic_name] = generate_article_text(valid_uuids, df)

    translated = gemini.translate_digest_to_english(formatted_summary_zh, en_reference_texts)
    _save_json(TEMP_DIR / "08-en_translated.json", translated)

    # Subedit English version
    edited_en = gemini.subedit_summary_en(translated)
    _save_json(TEMP_DIR / "09-en_subedited.json", edited_en)

    # Build English links per topic (index-based to avoid name mismatch)
    en_topics_link = []
    for i, t in enumerate(edited_en["topics"]):
        topic_name = t["topic"]
        zh_articles = topics_link_zh[i]["topic"]["articles"] if i < len(topics_link_zh) else []
        en_uuids = en_articles_by_index[i] if i < len(en_articles_by_index) else []
        valid_en = [u for u in en_uuids if u in df.index]
        valid_zh = [u for u in zh_articles if u in df.index]
        links = generate_english_article_links(valid_zh, valid_en, df, MAX_LINKS_PER_TOPIC)
        en_topics_link.append({"topic": {"topic": topic_name, "articles": en_uuids}, "link": links})

    _save_json(TEMP_DIR / "10-en_topics_link.json", en_topics_link)

    return append_summary_and_links_en(edited_en, en_topics_link)


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

    # Also verify English Substack auth if configured
    en_url = os.environ.get("SUBSTACK_EN_URL")
    if en_url:
        try:
            verify_auth(publication_url=en_url, sid_env="SUBSTACK_EN_SID",
                        email_env="SUBSTACK_EN_EMAIL", password_env="SUBSTACK_EN_PASSWORD")
        except SubstackAuthError as e:
            logger.error("English Substack auth preflight failed: %s", e)
            print(
                "ERROR: English Substack authentication failed — SUBSTACK_EN_SID cookie likely expired. "
                "Please rotate.",
                file=sys.stderr,
            )
            sys.exit(2)

    df = load_articles(RSS_FEEDS, english_sources=ENGLISH_SOURCES)

    # Filter to Chinese-only articles for the Chinese digest pipeline
    df_zh = df[df["language"] == "zh"] if "language" in df.columns else df

    digest_candidates: list[dict] = []
    # Store intermediates from last run for English pipeline
    last_formatted_summary = None
    last_topics_link = None

    for i in range(1, BEST_OF_OPTION + 1):
        logger.info("Generating try %d of %d", i, BEST_OF_OPTION)

        edited_text, pre_edited_text, formatted_summary, topics_link = generate_digest(
            df_zh, NUMBER_OF_TOPICS
        )
        digest_candidates.append({"summary_id": i, "text": edited_text})
        last_formatted_summary = formatted_summary
        last_topics_link = topics_link

        (TEMP_DIR / f"summary-{i}_pre_edited.md").write_text(pre_edited_text)
        (TEMP_DIR / f"summary-{i}_edited.md").write_text(edited_text)

    _save_json(TEMP_DIR / "05-final_text.json", digest_candidates)

    best_score = gemini.evaluate_output(BEST_OF_OPTION, digest_candidates)
    _save_json(TEMP_DIR / "06-score.json", best_score)

    earliest = df_zh.published.min()
    latest = df_zh.published.max()
    now = datetime.now()

    # Publish Chinese digest
    publish_substack_post(
        title=f"{now.year}年{now.month}月{now.day}日 香港每週新聞摘要",
        subtitle=f"本期涵蓋 {earliest.month}月{earliest.day}日 至 {latest.month}月{latest.day}日 的新聞。本新聞摘要由 {MODEL} 自動生成。",
        content=digest_candidates[best_score["summary_id"] - 1]["text"],
        draft_only=draft_only,
    )

    # Generate and publish English digest
    if en_url:
        logger.info("Generating English digest...")
        en_text = generate_english_digest(last_formatted_summary, last_topics_link, df)
        (TEMP_DIR / "summary_en.md").write_text(en_text)

        publish_substack_post(
            title=f"Hong Kong Weekly News Digest — {now.strftime('%B %d, %Y')}",
            subtitle=f"Covering news from {earliest.strftime('%B %d')} to {latest.strftime('%B %d')}. Auto-generated by {MODEL}.",
            content=en_text,
            draft_only=draft_only,
            publication_url=en_url,
            sid_env="SUBSTACK_EN_SID",
            email_env="SUBSTACK_EN_EMAIL",
            password_env="SUBSTACK_EN_PASSWORD",
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
