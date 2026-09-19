import json
import logging
import os
import random
from itertools import permutations
from datetime import date

import pandas as pd
from google import genai
from google.genai import types
import dotenv
from pydantic import BaseModel
from utils import extract_json_to_dict
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_not_exception_type,
)

from response_model import (
    is_valid_response,
    TopicsList,
    TopicSummary,
    TopicsSummary,
    ArticlesByTopic,
    SelectedArticles,
)

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


class ProhibitedContentError(Exception):
    """Gemini rejected the prompt at the input stage.

    Gemini applies a non-configurable PROHIBITED_CONTENT filter that none of the
    ``safety_settings`` below can switch off. It fires on the *prompt*, before
    any generation, and it is deterministic: re-sending the same prompt always
    blocks again. Callers must shed or replace material rather than retry.
    """

    def __init__(self, block_reason, block_message: str | None = None):
        self.block_reason = block_reason
        self.block_message = block_message
        detail = f", message={block_message}" if block_message else ""
        super().__init__(
            f"Gemini blocked the prompt (block_reason={block_reason}{detail}); "
            "retrying an identical prompt cannot succeed"
        )


MODEL = "gemini-3.5-flash"

MAX_UUID_VALIDATION_ATTEMPTS = 5

# Re-orderings of the grounding text to try before shedding any of it.
TRANSLATION_SHUFFLE_ATTEMPTS = 5

GEMINI_TIMEOUT = 150_000  # milliseconds per request; heaviest calls (~18k tokens) take ~60s

generate_content_config = types.GenerateContentConfig(
    temperature=1,
    top_p=0.95,
    max_output_tokens=65536,
    response_modalities=["TEXT"],
    safety_settings=[
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(
            category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"
        ),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    ],
    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT),
)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_not_exception_type(ProhibitedContentError),
)
def generate_response(
    prompt: str,
    validation_class: type[BaseModel] | None = None,
    lang: str = "tc",
    model: str = MODEL,
) -> dict | str:
    system_prompt = {
        "tc": "**所有輸出都必須使用繁體中文。**\n\n",
        "sc": "**所有输出都必须使用简体中文。**\n\n",
        "en": "**All output should be in English only.**\n\n",
    }
    full_prompt = system_prompt[lang] + prompt
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    response = None
    try:
        response = client.models.generate_content(
            model=model,
            config=generate_content_config,
            contents=[full_prompt],
        )

        # A blocked prompt comes back with zero candidates, so prompt_feedback is
        # the only place the reason is recorded. Check it before anything else.
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None)
        if block_reason is not None:
            raise ProhibitedContentError(
                block_reason, getattr(prompt_feedback, "block_reason_message", None)
            )

        finish_reason = response.candidates[0].finish_reason if response.candidates else None
        usage = response.usage_metadata
        logger.info(
            # %s not %d: the counts are None when nothing was generated
            "Tokens — input: %s, output: %s, thinking: %s, finish: %s",
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "thoughts_token_count", None),
            finish_reason,
        )

        if response.text is None:
            safety = getattr(response.candidates[0], "safety_ratings", None) if response.candidates else None
            raise ValueError(
                f"Gemini returned no text (finish_reason={finish_reason}, safety={safety})"
            )
        result = response.text.strip()

        if validation_class is not None:
            json_result = extract_json_to_dict(result)
            if not is_valid_response(json_result, validation_class):
                raise ValueError("Invalid response format. Regenerating....")
            return json_result
        else:
            return result

    except Exception as e:
        response_text = response.text if response else "(no response)"
        feedback = getattr(response, "prompt_feedback", None) if response else None
        with open("temp/error.txt", "w", encoding="utf-8") as f:
            f.write(
                f"Prompt: {prompt}\n\n Response: {response_text}\n\n"
                f" Prompt feedback: {feedback}\n\n Error: {e}"
            )
        logger.error("Error: %s", e)
        raise


def generate_topics(df: pd.DataFrame, number_of_topics: int = 5) -> dict:
    article_list = df[["headline", "summary"]].to_dict(orient="records")

    prompt = f"""
    You are a news editor for a Hong Kong news website. These are a list of news articles headlines and content. Identify the top {number_of_topics} major topics that was reported.

    **IMPORTANT: This digest covers Hong Kong local news only.** You must:
    - Only select topics that are directly about Hong Kong — local politics, policy, courts, economy, society, housing, infrastructure, etc.
    - Exclude purely international news (e.g. US politics, Middle East conflicts, global tech policy) even if reported by Hong Kong media.
    - International stories may be included ONLY if they have a direct and specific impact on Hong Kong (e.g. a Hong Kong company's overseas operations, international sanctions affecting Hong Kong, trade policies targeting Hong Kong).

    When choosing the major topics, you should:
    1. Consider the number of articles reporting on the issue. More reporting indicates wider public interest.
    2. Consider the issue's impact on Hong Kong society and economy specifically.
    3. Policy proposals and discussion should generally be accorded higher priority. For these topics, sometime it is useful to combine several issues under an overarching theme.
    4. Do not summarise court cases for different issues into a single topic.
    5. Court cases should only be included if they have widespeard impact on Hong Kong society.
    6. In any case, there should not be more than {round(number_of_topics * 0.4)} topics related to court cases.

    Summarise each topic into a concise, news headline format.

    Articles:
    {article_list}

    Your output should be in JSON format.
    Schema:
    {TopicsList.model_json_schema()}
    """

    logger.info("Generating topics...")
    return generate_response(prompt=prompt, validation_class=TopicsList)


def generate_articles_list_by_topic(
    major_themes: dict, headlines: pd.DataFrame
) -> dict:
    # Use sequential integer IDs instead of UUIDs — verbatim copying of
    # 32-char hex UUIDs is unreliable; small integers are not.
    idx_to_uuid: dict[str, str] = {}
    article_list = []
    for i, (uuid_, row) in enumerate(headlines.iterrows(), start=1):
        sid = str(i)
        idx_to_uuid[sid] = uuid_
        article_list.append({"id": sid, "headline": row.headline, "summary": row.summary})

    prompt = f"""
    You are a news editor for a Hong Kong news website. These are a number of major themes that we will cover.

    Major Themes:
    {major_themes}

    Here are a list of headlines and summaries with the article id. Try to group them under the major themes provided. Only include articles that fit the major themes. Skip articles that do not fit any theme or are purely international news with no direct Hong Kong relevance.

    Headlines, summaries & id:
    {article_list}

    Your output should be in JSON format. The "articles" field for each topic should be a list of id strings.
    Schema:
    {ArticlesByTopic.model_json_schema()}
    """
    valid_ids = set(idx_to_uuid.keys())

    for attempt in range(1, MAX_UUID_VALIDATION_ATTEMPTS + 1):
        logger.info(
            "Generating articles list by topic (attempt %d/%d)...",
            attempt,
            MAX_UUID_VALIDATION_ATTEMPTS,
        )
        output = generate_response(prompt=prompt, validation_class=ArticlesByTopic)

        has_valid_ids = all(
            aid in valid_ids
            for topic in output["topics"]
            for aid in topic["articles"]
        )
        empty_topics = [
            topic["topic"]
            for topic in output["topics"]
            if len(topic["articles"]) == 0
        ]

        if has_valid_ids and not empty_topics:
            _map_ids_to_uuids(output, idx_to_uuid)
            return output
        if not has_valid_ids:
            logger.warning("Invalid id in output. Regenerating...")
        if empty_topics:
            logger.warning("Empty articles for topics: %s. Regenerating...", empty_topics)

    # After all retries: if ids are valid, drop empty topics and proceed
    if has_valid_ids and empty_topics:
        logger.warning(
            "Dropping %d topic(s) with no matched articles after %d attempts: %s",
            len(empty_topics),
            MAX_UUID_VALIDATION_ATTEMPTS,
            empty_topics,
        )
        output["topics"] = [
            topic
            for topic in output["topics"]
            if len(topic["articles"]) > 0
        ]
        _map_ids_to_uuids(output, idx_to_uuid)
        return output

    raise RuntimeError(
        f"Failed to generate valid article groupings after {MAX_UUID_VALIDATION_ATTEMPTS} attempts"
    )


def _map_ids_to_uuids(output: dict, idx_to_uuid: dict[str, str]) -> None:
    for topic in output["topics"]:
        topic["articles"] = [idx_to_uuid[aid] for aid in topic["articles"]]


def topic_summary(topic: str, article_text: str) -> dict:
    prompt = f"""
    You are a news editor for a Hong Kong news website. You are going to write a news summary for the topic: {topic}. You will be provided with a number of articles related to the topic, including the article headline and the article text.

    Today's date is {date.today().strftime('%Y-%m-%d')}.

    When writing the summary, you should:
    1. Only use the material available from the articles provided
    2. Provide a brief summary of the topic
    3. If the article contains quotes from people, try to include them as much as possible
    4. If a person's quote is responding to another person's quote, try to include both quotes
    5. Do not include addtional comments that is not present in the provided articles
    6. Some parts of the article might be redacted by the character ^. In this case write a summary without referencing the redacted content.
    7. You should write between 250 and 600 Chinese characters, and try to aim at writing 400 Chinese character.

    Here are the articles: {article_text}

    Your output should be in JSON format.
    Schema:
    {TopicSummary.model_json_schema()}
    """

    logger.info("Generating summary for topic %s...", topic)
    return generate_response(prompt=prompt, validation_class=TopicSummary)


def select_representative_articles(
    topic: str, articles: list[str], df: pd.DataFrame, max_links: int = 5
) -> list[str]:
    """Select the most representative articles for a topic's link section."""
    if len(articles) <= max_links:
        return articles

    article_info = []
    for uuid in articles:
        row = df.loc[uuid]
        article_info.append(
            {"uuid": uuid, "headline": row["headline"], "source": row["source"]}
        )

    prompt = f"""
    你是一位香港新聞網站的編輯。以下是關於「{topic}」的 {len(articles)} 篇報導。
    請從中選出最具代表性的 {max_links} 篇文章，作為讀者延伸閱讀的連結。

    選擇時請優先考慮：
    1. 來源多樣性：盡量選擇不同新聞來源的報導
    2. 代表性：選擇最能反映該議題核心的報導
    3. 角度覆蓋：選擇涵蓋不同面向的報導
    4. 資訊獨特性：避免選擇內容高度重複的報導

    文章列表：
    {article_info}

    Your output should be in JSON format.
    Schema:
    {SelectedArticles.model_json_schema()}
    """

    logger.info("Selecting %d representative articles for topic: %s", max_links, topic)
    result = generate_response(prompt=prompt, validation_class=SelectedArticles)

    valid_uuids = set(articles)
    selected = [a["uuid"] for a in result["selected"] if a["uuid"] in valid_uuids]

    # Pad with remaining articles if Gemini returned fewer valid UUIDs
    if len(selected) < max_links:
        selected_uuids = set(selected)
        for uuid in articles:
            if uuid not in selected_uuids:
                selected.append(uuid)
                if len(selected) >= max_links:
                    break

    return selected[:max_links]


def subedit_summary(topics_summary: dict) -> dict:
    prompt = f"""
    Please act as a news subeditor. Your goal is to edit the following news summary for consistent style and presentation, while strictly adhering to the following guidelines. It's important to maintain the original information and avoid adding any new content or rewriting the core meaning.

    **Style Guidelines:**
    1. ** Character Set:** Use Traditional Chinese characters primarily. English is acceptable for proper nouns lacking direct Traditional Chinese translations. No other languages should be used and you should delete / translate non-compliant characters.
    2. ** Topic title:** Does the topic title make sense and matches the summary? Is the language concise and written in a news headline style?
    3. **Person Titles:** Ensure consistent titling for individuals throughout the summary.
    4. **Title Usage:** Avoid unnecessary honorifics like 先生, 女士. Use concise and professional titles where appropriate.
    5. **Date Format:** Today's date is {date.today().strftime('%Y-%m-%d')}. Replace general terms like "today", "yesterday", "tomorrow" with specific dates.
    6. **Summary Length:**  Aim for each topic summary to be approximately 250-600 words. Focus on conciseness and information density within this range.

    **Input Summary (Markdown):**
    {topics_summary}

    Your output should be in JSON format.
    Schema:
    {TopicsSummary.model_json_schema()}
    """

    logger.info("Editing summary...")
    return generate_response(prompt=prompt, validation_class=TopicsSummary)


def match_english_articles_to_topics(
    topic_names: list[str], en_headlines: pd.DataFrame
) -> dict:
    """Match English articles to existing Chinese-identified topics."""
    article_list = en_headlines.reset_index().to_dict(orient="records")

    prompt = f"""
    You are a news editor. Below are topics identified from Hong Kong news this week, and a list of English-language articles with their UUIDs.

    Assign each English article to the most relevant topic. An article may only be assigned to one topic. Skip articles that don't clearly fit any topic.

    Topics:
    {topic_names}

    English articles (headline, summary, uuid):
    {article_list}

    Your output should be in JSON format.
    Schema:
    {ArticlesByTopic.model_json_schema()}
    """

    valid_uuids = set(en_headlines.index)

    for attempt in range(1, MAX_UUID_VALIDATION_ATTEMPTS + 1):
        logger.info(
            "Matching English articles to topics (attempt %d/%d)...",
            attempt,
            MAX_UUID_VALIDATION_ATTEMPTS,
        )
        output = generate_response(prompt=prompt, validation_class=ArticlesByTopic, lang="en")

        has_valid_uuids = all(
            uuid in valid_uuids
            for topic in output["topics"]
            for uuid in topic["articles"]
        )
        if has_valid_uuids:
            return output
        logger.warning("Invalid UUID in English article matching. Regenerating...")

    # Return whatever we have, filtering invalid UUIDs
    for topic in output["topics"]:
        topic["articles"] = [u for u in topic["articles"] if u in valid_uuids]
    return output


def _shuffled_orders(names: list[str], rng: random.Random, limit: int) -> list[list[str]]:
    """Up to ``limit`` distinct reorderings of ``names``, excluding the original.

    Distinct matters: re-sending an ordering that already blocked wastes an
    attempt, and with few reference blocks there are few orderings to draw from
    (3 blocks allow only 5 alternatives). Small inputs are enumerated so the
    orderings are exactly distinct; larger ones fall back to sampling.
    """
    n = len(names)
    if n < 2:
        return []
    if n <= 7:
        candidates = [list(p) for p in permutations(names) if list(p) != names]
        rng.shuffle(candidates)
        return candidates[:limit]

    seen: set[tuple[str, ...]] = set()
    out: list[list[str]] = []
    draws = 0
    while len(out) < limit and draws < limit * 20:
        draws += 1
        order = names[:]
        rng.shuffle(order)
        key = tuple(order)
        if order == names or key in seen:
            continue
        seen.add(key)
        out.append(order)
    return out


def _build_translation_prompt(
    zh_summary: dict, en_reference_texts: dict[str, str]
) -> str:
    """Render the translation prompt for a given set of topics and grounding text."""
    reference_section = ""
    if en_reference_texts:
        parts = []
        for topic, text in en_reference_texts.items():
            parts.append(f"### {topic}\n{text[:3000]}")
        reference_section = "\n\n".join(parts)

    return f"""
    You are a professional translator and news editor. Translate the following Hong Kong news digest from Traditional Chinese to English.

    **Translation guidelines:**
    1. Maintain the same topic structure and order.
    2. For proper nouns (people, organizations, places, legislation):
       - Use the official English spelling found in the reference English articles below.
       - If not found in reference articles, use the Hong Kong Government's official English translation.
       - As a last resort, use your own knowledge of standard English translations.
    3. Keep each topic summary between 150 and 400 words.
    4. Maintain a professional, journalistic tone suitable for an English-language news digest.
    5. Do not add information not present in the Chinese summary.
    6. Translate topic titles into concise English news headline style.

    **Chinese digest to translate:**
    {json.dumps(zh_summary, ensure_ascii=False, indent=2)}

    **Reference English articles (use for proper noun grounding):**
    {reference_section if reference_section else "(No English reference articles available)"}

    Your output should be in JSON format.
    Schema:
    {TopicsSummary.model_json_schema()}
    """


def translate_digest_to_english(
    zh_summary: dict, en_reference_texts: dict[str, str]
) -> tuple[dict, list[int]]:
    """Translate the Chinese digest to English, shedding material Gemini rejects.

    Returns the translated digest together with the indices of
    ``zh_summary["topics"]`` it covers, in order. The indices matter because a
    topic can be dropped: Gemini's non-configurable PROHIBITED_CONTENT filter
    rejects some prompts outright, deterministically, so an identical retry can
    never succeed (see ProhibitedContentError). What *does* change the verdict is
    the arrangement of the prompt: the filter is deterministic for any given
    ordering but disagrees between orderings, so we escalate through

      1. re-ordering the grounding text — nothing is lost at all,
      2. dropping the verbatim grounding text for one topic,
      3. dropping all grounding text,
      4. dropping the offending topic itself.

    Measured on the 2026-09-19 digest: the original order blocked 14/14, while
    3 of 5 positions for the offending article passed 3/3 each — so a reshuffle
    clears it most of the time and costs no content. Grounding is shed before
    topics because the filter trips on raw source articles rather than on the
    Chinese summaries written from them.
    """
    topics = list(zh_summary["topics"])
    all_indices = list(range(len(topics)))

    def attempt(indices: list[int], refs: dict[str, str]) -> dict:
        subset = {"topics": [topics[i] for i in indices]}
        return generate_response(
            prompt=_build_translation_prompt(subset, refs),
            validation_class=TopicsSummary,
            lang="en",
        )

    logger.info("Translating digest to English...")
    try:
        return attempt(all_indices, en_reference_texts), all_indices
    except ProhibitedContentError as e:
        logger.warning(
            "English translation blocked (%s); retrying with the prompt rearranged",
            e.block_reason,
        )

    names = list(en_reference_texts)
    # Seeded so a rerun reproduces the same sequence; the rungs below cover the
    # case where every ordering we try still blocks.
    orders = _shuffled_orders(names, random.Random(0), TRANSLATION_SHUFFLE_ATTEMPTS)
    for n, order in enumerate(orders, 1):
        try:
            result = attempt(all_indices, {k: en_reference_texts[k] for k in order})
            logger.warning(
                "Translated after reordering grounding text (attempt %d of %d)",
                n, len(orders),
            )
            return result, all_indices
        except ProhibitedContentError:
            continue

    for name in names:
        trimmed = {k: v for k, v in en_reference_texts.items() if k != name}
        try:
            result = attempt(all_indices, trimmed)
            logger.warning("Translated without grounding text for topic: %s", name)
            return result, all_indices
        except ProhibitedContentError:
            continue

    if en_reference_texts:
        try:
            result = attempt(all_indices, {})
            logger.warning("Translated without any English grounding text")
            return result, all_indices
        except ProhibitedContentError:
            pass

    for i in all_indices:
        kept = [j for j in all_indices if j != i]
        if not kept:
            break
        try:
            result = attempt(kept, {})
            logger.warning(
                "Skipped prohibited topic from English digest: %s", topics[i]["topic"]
            )
            return result, kept
        except ProhibitedContentError:
            continue

    raise ProhibitedContentError(
        "PROHIBITED_CONTENT",
        "no combination of topics and grounding text passed Gemini's input filter",
    )


def subedit_summary_en(topics_summary: dict) -> dict:
    """Subedit the English digest for style consistency."""
    prompt = f"""
    Please act as a news subeditor. Edit the following English news digest for consistent style and presentation, while strictly preserving the original information.

    **Style Guidelines:**
    1. **Topic titles:** Ensure each title is concise and written in news headline style.
    2. **Person Titles:** Use consistent, professional titles throughout.
    3. **Date Format:** Today's date is {date.today().strftime('%Y-%m-%d')}. Replace relative terms like "today", "yesterday" with specific dates (e.g. "March 5").
    4. **Summary Length:** Each topic summary should be approximately 150-400 words. Focus on conciseness and information density.
    5. **Proper Nouns:** Ensure consistency in spelling of names, organizations, and places throughout.
    6. **Grammar and Flow:** Fix any awkward phrasing from translation while preserving meaning.

    **Input Summary:**
    {topics_summary}

    Your output should be in JSON format.
    Schema:
    {TopicsSummary.model_json_schema()}
    """

    logger.info("Editing English summary...")
    return generate_response(prompt=prompt, validation_class=TopicsSummary, lang="en")
