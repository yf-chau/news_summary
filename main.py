import json
import logging
from pathlib import Path
from datetime import datetime

import dotenv
import pandas as pd

import gemini
from gemini import MODEL
from utils import (
    generate_article_text,
    generate_article_links,
    append_summary_and_links,
    extract_news_data,
    save_to_csv,
)
from substack_api import post_substack_draft

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

TEMP_DIR = Path("temp")

# List of RSS feed URLs
RSS_FEEDS: dict[str, str] = {
    "集誌社": "https://thecollectivehk.com/feed/",
    "法庭線": "https://thewitnesshk.com/feed/",
    "庭刊": "https://hkcourtnews.com/feed/",
    "獨立媒體": "https://www.inmediahk.net/rss.xml",
    # "經濟日報": "https://www.hket.com/rss/hongkong",
    # "山下有人": "https://hillmankind.com/feed/",
    # "Hong Kong Free Press": "https://www.hongkongfp.com/feed/",
    # "Yahoo News HK": "https://hk.news.yahoo.com/rss/"
    # "Yahoo News HK": "https://hk.news.yahoo.com/rss/hong-kong/",
    # "Yahoo News HK": "https://hk.news.yahoo.com/rss/business/"
    # https://hk.news.yahoo.com/rss/world/
    # https://hk.news.yahoo.com/rss/entertainment/
    # https://hk.news.yahoo.com/rss/sports/
    # https://hk.news.yahoo.com/tech/rss.xml
    # https://news.mingpao.com/rss/pns/s00002.xml
    # https://news.google.com/rss?pz=1&cf=all&hl=zh-HK&gl=HK&ceid=HK:zh-Hant
}

BEST_OF_OPTION = 1
NUMBER_OF_TOPICS = 5


def _save_json(path: Path, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_articles(rss_feeds: dict[str, str]) -> pd.DataFrame:
    """Fetch RSS, save CSV, filter to last 7 days."""
    TEMP_DIR.mkdir(exist_ok=True)

    news_data = extract_news_data(rss_feeds)
    csv_filepath = TEMP_DIR / "news_data.csv"
    save_to_csv(news_data, str(csv_filepath))

    df = pd.read_csv(csv_filepath)
    df.set_index("uuid", inplace=True)
    df.published = pd.to_datetime(df.published)
    today = pd.Timestamp.today()
    week_ago = pd.Timestamp(today - pd.Timedelta(days=7)).tz_localize("UTC")
    return df[df.published > week_ago]


def generate_digest(df: pd.DataFrame, n_topics: int) -> tuple[str, str]:
    """Run topic generation -> summary -> subedit pipeline, return markdown."""
    topics = gemini.generate_topics(df[["headline", "summary"]], n_topics)
    articles_grouped_by_topic = gemini.generate_articles_list_by_topic(
        topics, df[["headline"]]
    )

    _save_json(TEMP_DIR / "01-topics.json", topics)
    _save_json(TEMP_DIR / "02-articles_by_topic.json", articles_grouped_by_topic)

    topics_summary: dict[str, list] = {"topics": []}
    topics_link: list[dict] = []

    for topic in articles_grouped_by_topic["topics"]:
        if topic["topic"].lower() != "others" and topic["topic"] != "其他":
            articles = topic["articles"]
            articles_text = generate_article_text(articles, df)
            articles_links = generate_article_links(articles, df)
            topics_summary["topics"].append(
                gemini.topic_summary(topic["topic"], articles_text)
            )
            topics_link.append({"topic": topic, "link": articles_links})

    formatted_summary = gemini.subedit_summary(topics_summary)

    _save_json(TEMP_DIR / "03-topics_summary.json", formatted_summary)
    _save_json(TEMP_DIR / "04-topics_link.json", topics_link)

    pre_edited_text = append_summary_and_links(topics_summary, topics_link)
    edited_text = append_summary_and_links(formatted_summary, topics_link)

    return edited_text, pre_edited_text


def run_pipeline() -> None:
    """Main entry point: load articles, generate digest, publish."""
    logging.basicConfig(level=logging.INFO)

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

    now = datetime.now()
    post_substack_draft(
        title=f"{now.year}年{now.month}月{now.day}日 香港每週新聞摘要",
        subtitle=f"本新聞摘要由 {MODEL} 自動生成。",
        content=digest_candidates[best_score["summary_id"] - 1]["text"],
    )


if __name__ == "__main__":
    run_pipeline()
