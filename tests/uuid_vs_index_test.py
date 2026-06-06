"""Compare UUID-copy vs integer-index grouping reliability on real data.

Runs N trials of each variant against the same article list + topic list,
then reports hallucination, intra-method stability, and cross-method agreement.
"""

import json
import logging
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemini
from response_model import ArticlesByTopic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

N_TRIALS = 5
N_TOPICS = 5
ARTICLES_PATH = Path("data/articles.jsonl")
OUT_DIR = Path("temp/uuid_vs_index")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_zh_articles() -> pd.DataFrame:
    df = pd.read_json(ARTICLES_PATH, lines=True)
    if "language" not in df.columns:
        df["language"] = "zh"
    df["language"] = df["language"].fillna("zh")
    df = df[df["language"] == "zh"].set_index("uuid")
    return df[["headline", "summary"]]


def make_uuid_prompt(themes: dict, df: pd.DataFrame) -> str:
    article_list = df.reset_index().to_dict(orient="records")
    return f"""
    You are a news editor for a Hong Kong news website. These are a number of major themes that we will cover.

    Major Themes:
    {themes}

    Here are a list of headlines and summaries with the article uuid. Try to group them under the major themes provided. Only include articles that fit the major themes. Skip articles that do not fit any theme or are purely international news with no direct Hong Kong relevance.

    Headlines, summaries & uuid:
    {article_list}

    Your output should be in JSON format.
    Schema:
    {ArticlesByTopic.model_json_schema()}
    """


def make_index_prompt(themes: dict, df: pd.DataFrame) -> tuple[str, dict[str, str]]:
    """Build prompt using sequential integer IDs; return prompt + id→uuid map."""
    idx_to_uuid: dict[str, str] = {}
    article_list = []
    for i, (uuid_, row) in enumerate(df.iterrows(), start=1):
        sid = str(i)
        idx_to_uuid[sid] = uuid_
        article_list.append({"id": sid, "headline": row.headline, "summary": row.summary})
    prompt = f"""
    You are a news editor for a Hong Kong news website. These are a number of major themes that we will cover.

    Major Themes:
    {themes}

    Here are a list of headlines and summaries with the article id. Try to group them under the major themes provided. Only include articles that fit the major themes. Skip articles that do not fit any theme or are purely international news with no direct Hong Kong relevance.

    Headlines, summaries & id:
    {article_list}

    Your output should be in JSON format. The "articles" field for each topic should be a list of id strings.
    Schema:
    {ArticlesByTopic.model_json_schema()}
    """
    return prompt, idx_to_uuid


def run_trial(prompt: str, label: str, trial: int) -> dict:
    logger.info("[%s] Trial %d/%d", label, trial, N_TRIALS)
    return gemini.generate_response(prompt=prompt, validation_class=ArticlesByTopic)


def evaluate(output: dict, valid_ids: set[str], label: str) -> dict:
    """Return per-trial stats: hallucination count, valid assignments per topic."""
    total_ids = 0
    hallucinated = 0
    valid_assignments: dict[str, list[str]] = {}
    for t in output["topics"]:
        topic = t["topic"]
        valid_for_topic = []
        for a in t["articles"]:
            total_ids += 1
            if a in valid_ids:
                valid_for_topic.append(a)
            else:
                hallucinated += 1
        valid_assignments[topic] = valid_for_topic
    return {
        "label": label,
        "total_ids": total_ids,
        "hallucinated": hallucinated,
        "hallucination_rate": hallucinated / total_ids if total_ids else 0.0,
        "valid_assignments": valid_assignments,
    }


def majority_topic_per_article(trials: list[dict], all_ids: set[str]) -> dict[str, str | None]:
    """For each article id, the topic it was assigned to in a majority of trials.

    Returns id -> topic_name (or None if no majority / never assigned).
    """
    per_id: dict[str, Counter] = {aid: Counter() for aid in all_ids}
    for trial in trials:
        for topic, ids in trial["valid_assignments"].items():
            for aid in ids:
                per_id[aid][topic] += 1
    out: dict[str, str | None] = {}
    for aid, c in per_id.items():
        if not c:
            out[aid] = None
            continue
        top_topic, top_count = c.most_common(1)[0]
        # require strict majority of trials that mentioned the article
        out[aid] = top_topic if top_count > len(trials) / 2 else None
    return out


def main():
    df = load_zh_articles()
    logger.info("Loaded %d Chinese articles", len(df))

    topics_cache = OUT_DIR / "topics.json"
    if topics_cache.exists():
        themes = json.loads(topics_cache.read_text())
        logger.info("Reusing cached topics")
    else:
        logger.info("Generating topics (one-time)")
        themes = gemini.generate_topics(df, N_TOPICS)
        topics_cache.write_text(json.dumps(themes, ensure_ascii=False, indent=2))
    logger.info("Topics: %s", themes)

    # Prepare both variants
    uuid_prompt = make_uuid_prompt(themes, df)
    uuid_valid = set(df.index)
    idx_prompt, idx_to_uuid = make_index_prompt(themes, df)
    idx_valid = set(idx_to_uuid.keys())

    # Identify uncached trials and run them in parallel
    pending: list[tuple[str, int, str]] = []  # (label, trial, prompt)
    for i in range(1, N_TRIALS + 1):
        if not (OUT_DIR / f"uuid_trial_{i}.json").exists():
            pending.append(("UUID", i, uuid_prompt))
        if not (OUT_DIR / f"idx_trial_{i}.json").exists():
            pending.append(("INDEX", i, idx_prompt))

    logger.info("Pending trials: %d (running in parallel)", len(pending))
    with ThreadPoolExecutor(max_workers=max(1, len(pending))) as pool:
        futures = {
            pool.submit(run_trial, prompt, label, i): (label, i)
            for label, i, prompt in pending
        }
        for fut in as_completed(futures):
            label, i = futures[fut]
            cache_name = f"uuid_trial_{i}.json" if label == "UUID" else f"idx_trial_{i}.json"
            try:
                raw = fut.result()
                (OUT_DIR / cache_name).write_text(json.dumps(raw, ensure_ascii=False, indent=2))
                logger.info("[%s] Trial %d done", label, i)
            except Exception as e:
                logger.error("[%s] Trial %d failed: %s", label, i, e)

    # Load all results from cache
    uuid_results = []
    for i in range(1, N_TRIALS + 1):
        cache = OUT_DIR / f"uuid_trial_{i}.json"
        if cache.exists():
            uuid_results.append(evaluate(json.loads(cache.read_text()), uuid_valid, "UUID"))
    idx_results = []
    for i in range(1, N_TRIALS + 1):
        cache = OUT_DIR / f"idx_trial_{i}.json"
        if cache.exists():
            idx_results.append(evaluate(json.loads(cache.read_text()), idx_valid, "INDEX"))

    # Map INDEX results back to UUIDs for comparison
    for stats in idx_results:
        stats["valid_assignments"] = {
            topic: [idx_to_uuid[aid] for aid in ids]
            for topic, ids in stats["valid_assignments"].items()
        }

    # Aggregate metrics
    def avg(field, results):
        return sum(r[field] for r in results) / max(len(results), 1)

    summary = {
        "n_trials_uuid": len(uuid_results),
        "n_trials_idx": len(idx_results),
        "uuid_avg_total": avg("total_ids", uuid_results),
        "uuid_avg_hallucinated": avg("hallucinated", uuid_results),
        "uuid_avg_halluc_rate": avg("hallucination_rate", uuid_results),
        "idx_avg_total": avg("total_ids", idx_results),
        "idx_avg_hallucinated": avg("hallucinated", idx_results),
        "idx_avg_halluc_rate": avg("hallucination_rate", idx_results),
    }

    # Intra-method stability: % of articles with strict-majority topic
    uuid_majority = majority_topic_per_article(uuid_results, uuid_valid)
    idx_majority = majority_topic_per_article(idx_results, uuid_valid)
    summary["uuid_articles_with_majority"] = sum(1 for v in uuid_majority.values() if v is not None)
    summary["idx_articles_with_majority"] = sum(1 for v in idx_majority.values() if v is not None)

    # Cross-method agreement: of articles with majority in BOTH, % same topic
    both = [aid for aid in uuid_valid if uuid_majority.get(aid) and idx_majority.get(aid)]
    agree = [aid for aid in both if uuid_majority[aid] == idx_majority[aid]]
    summary["cross_method_overlap_articles"] = len(both)
    summary["cross_method_agree"] = len(agree)
    summary["cross_method_agreement_rate"] = len(agree) / len(both) if both else 0.0

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
