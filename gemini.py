import logging
import os

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
    retry_if_exception_type,
)

from response_model import (
    is_valid_response,
    TopicsList,
    ScoreModel,
    TopicSummary,
    TopicsSummary,
    ArticlesByTopic,
)

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"

MAX_UUID_VALIDATION_ATTEMPTS = 5

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
)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(Exception),
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
        result = response.text.strip()

        logger.info(
            "Tokens — input: %d, output: %d",
            response.usage_metadata.prompt_token_count,
            response.usage_metadata.candidates_token_count,
        )

        if validation_class is not None:
            json_result = extract_json_to_dict(result)
            if not is_valid_response(json_result, validation_class):
                raise ValueError("Invalid response format. Regenerating....")
            return json_result
        else:
            return result

    except Exception as e:
        response_text = response.text if response else "(no response)"
        with open("temp/error.txt", "w", encoding="utf-8") as f:
            f.write(f"Prompt: {prompt}\n\n Response: {response_text}\n\n Error: {e}")
        logger.error("Error: %s", e)
        raise


def generate_topics(df: pd.DataFrame, number_of_topics: int = 5) -> dict:
    article_list = df[["headline", "summary"]].to_dict(orient="records")

    prompt = f"""
    You are a news editor for a news website. These are a list of news articles headlines and content. Identify the top {number_of_topics} major topics that was reported.

    When choosing the major topics, you should:
    1. Consider the number of articles reporting on the issue. More reporting indicates wider public interest.
    2. Consider the issue's impact on the society as a whole and the economy.
    3. Policy proposals and discussion should generally be accorded higher priority. For these topics, sometime it is useful to combine several issues under an overarching theme.
    4. Do not summarise court cases for different issues into a single topic.
    5. Court cases should only be included if they have widespeard impact on the society.
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
    article_list = headlines.reset_index().to_dict(orient="records")

    prompt = f"""
    You are a news editor for a news website. These are a number of major themes that we will cover.

    Major Themes:
    {major_themes}

    Here are a list of headlines and summaries with the article uuid. Try to group them under the major themes provided. If the article does not fit any of the major themes, group it under "Others".

    Headlines, summaries & uuid:
    {article_list}

    Your output should be in JSON format.
    Schema:
    {ArticlesByTopic.model_json_schema()}
    """
    valid_uuids = set(headlines.index)

    for attempt in range(1, MAX_UUID_VALIDATION_ATTEMPTS + 1):
        logger.info(
            "Generating articles list by topic (attempt %d/%d)...",
            attempt,
            MAX_UUID_VALIDATION_ATTEMPTS,
        )
        output = generate_response(prompt=prompt, validation_class=ArticlesByTopic)

        has_valid_uuids = all(
            article["uuid"] in valid_uuids
            for topic in output["topics"]
            for article in topic["articles"]
        )
        empty_topics = [
            topic["topic"]
            for topic in output["topics"]
            if topic["topic"].lower() != "others"
            and topic["topic"] != "其他"
            and len(topic["articles"]) == 0
        ]

        if has_valid_uuids and not empty_topics:
            return output
        if not has_valid_uuids:
            logger.warning("Invalid UUID in output. Regenerating...")
        if empty_topics:
            logger.warning("Empty articles for topics: %s. Regenerating...", empty_topics)

    # After all retries: if UUIDs are valid, drop empty topics and proceed
    if has_valid_uuids and empty_topics:
        logger.warning(
            "Dropping %d topic(s) with no matched articles after %d attempts: %s",
            len(empty_topics),
            MAX_UUID_VALIDATION_ATTEMPTS,
            empty_topics,
        )
        output["topics"] = [
            topic
            for topic in output["topics"]
            if topic["topic"].lower() == "others"
            or topic["topic"] == "其他"
            or len(topic["articles"]) > 0
        ]
        return output

    raise RuntimeError(
        f"Failed to generate valid article groupings after {MAX_UUID_VALIDATION_ATTEMPTS} attempts"
    )


def topic_summary(topic: str, article_text: str) -> dict:
    prompt = f"""
    You are a news editor for a news website. You are going to write a news summary for the topic: {topic}. You will be provided with a number of articles related to the topic, including the article headline and the article text.

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


def subedit_summary(topics_summary: dict) -> dict:
    prompt = f"""
    Please act as a news subeditor. Your goal is to edit the following news summary for consistent style and presentation, while strictly adhering to the following guidelines. It's important to maintain the original information and avoid adding any new content or rewriting the core meaning.

    **Style Guidelines:**
    1. ** Character Set:** Use Traditional Chinese characters primarily. English is acceptable for proper nouns lacking direct Traditional Chinese translations. No other languages should be used and you should delete / translate non-compliant characters.
    2. ** Topic title:** Does the topic title make sense and matches the summary? Is the language concise and written in a news headline style?
    3. **Person Titles:** Ensure consistent titling for individuals throughout the summary.
    4. **Title Usage:** Avoid unnecessary honorifics like 先生, 女士. Use concise and professional titles where appropriate.
    5. **Date Format:** Replace general terms like "today", "yesterday", "tomorrow" with specific dates.
    6. **Summary Length:**  Aim for each topic summary to be approximately 250-600 words. Focus on conciseness and information density within this range.

    **Input Summary (Markdown):**
    {topics_summary}

    Your output should be in JSON format.
    Schema:
    {TopicsSummary.model_json_schema()}
    """

    logger.info("Editing summary...")
    return generate_response(prompt=prompt, validation_class=TopicsSummary)


def evaluate_output(best_of: int, output: list[dict]) -> dict:
    summary_in_prompt = "\n\n".join(
        f"**summary_id: {s['summary_id']}**\n\nsummary_text:{s['text']}"
        for s in output
    )

    prompt = f"""
    You are the chief editor for an company that produce media summary for news. You will be presented with {best_of} choices of news summary and score them against each other. The score should be between 1 and 100.

    You can assume the style and formatting of the summary is correct.

    You should score them using these criteria:
    1. Consistency: Do the summaries have the same key points and structure?
    2. Clarity: Is the summary easy to understand for a general audience which might not have background knowledge on the issue being discussed?
    3. Relevance: Does the summary provides a clear overview of the main points and key takeaways of the topic?
    4. Order of topics: Are the topics arranged in order of importance? You should consider the impact of the topics on the society as a whole and the economy.
    5. The topics are independent of each other and they should cover a wide range of issues.

    Here are the summaries:
    {summary_in_prompt}

    Your output should be in JSON format.
    Schema:
    {ScoreModel.model_json_schema()}
    ```
    """

    logger.info("Evaluating output...")

    score = generate_response(prompt=prompt, validation_class=ScoreModel)

    best_score = max(score["scores"], key=lambda x: x["score"])
    logger.info(
        "Best score — Summary ID: %d, Score: %d",
        best_score["summary_id"],
        best_score["score"],
    )

    return best_score
