"""Daily RSS article accumulator.

Fetches articles from RSS feeds and appends new ones to a JSONL file.
Deduplicates by URL and prunes articles older than 10 days.
No Gemini or Substack calls — safe to run on GitHub-hosted runners.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils import extract_news_data
from main import RSS_FEEDS

DATA_DIR = Path("data")
ARTICLES_PATH = DATA_DIR / "articles.jsonl"
PRUNE_DAYS = 10

logger = logging.getLogger(__name__)


def load_existing_urls() -> set[str]:
    """Load URLs from existing JSONL to deduplicate."""
    urls: set[str] = set()
    if not ARTICLES_PATH.exists():
        return urls
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
                if article.get("url"):
                    urls.add(article["url"])
            except json.JSONDecodeError:
                logger.warning("Skipping corrupt JSONL line")
    return urls


def append_articles(articles: list[dict]) -> None:
    """Append articles to JSONL file."""
    with open(ARTICLES_PATH, "a", encoding="utf-8") as f:
        for article in articles:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")


def prune_old_articles() -> int:
    """Remove articles older than PRUNE_DAYS. Returns number pruned."""
    if not ARTICLES_PATH.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)
    kept: list[str] = []
    pruned = 0
    with open(ARTICLES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Dropping corrupt JSONL line during prune")
                pruned += 1
                continue
            fetched_at = article.get("fetched_at")
            if fetched_at:
                try:
                    ts = datetime.fromisoformat(fetched_at)
                    if ts < cutoff:
                        pruned += 1
                        continue
                except ValueError:
                    pass
            kept.append(json.dumps(article, ensure_ascii=False))
    with open(ARTICLES_PATH, "w", encoding="utf-8") as f:
        for entry in kept:
            f.write(entry + "\n")
    return pruned


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    DATA_DIR.mkdir(exist_ok=True)

    existing_urls = load_existing_urls()
    logger.info("Existing articles: %d", len(existing_urls))

    raw_articles = extract_news_data(RSS_FEEDS)
    now = datetime.now(timezone.utc).isoformat()

    new_articles = []
    for article in raw_articles:
        if article.get("url") and article["url"] not in existing_urls:
            article["fetched_at"] = now
            new_articles.append(article)

    if new_articles:
        append_articles(new_articles)
    logger.info("Fetched %d articles, %d new", len(raw_articles), len(new_articles))

    pruned = prune_old_articles()
    if pruned:
        logger.info("Pruned %d old articles", pruned)


if __name__ == "__main__":
    main()
