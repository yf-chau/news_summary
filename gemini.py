import os
import json
import pandas as pd
import google.generativeai as genai
import dotenv

dotenv.load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Create the model
generation_config = {
  "temperature": 0.7,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 65536,
  "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
  model_name="gemini-2.0-flash-thinking-exp-01-21",
  generation_config=generation_config,
)


def generate_response(prompt: str, lang: str = "tc") -> json:
    system_prompt = {"tc": "**所有輸出都必須使用繁體中文。**\n\n", "sc": "**所有输出都必须使用简体中文。**\n\n", "en": "**All output should be in English only.**\n\n"}
    full_prompt = system_prompt[lang] + prompt
    try:
        response = model.generate_content(full_prompt)
        result = response.text    
        result = result.strip()
        if result.startswith("```json") and result.endswith("```"):
            result = result[7:]
            result = result[:-3]
            result = json.loads(result)
        print(result)
    except Exception as e:
        print(prompt_content)
        return f"Error: {e}"
    return result


def generate_topics(df: pd.DataFrame):
    NUMBER_OF_HEADLINES = 5
    article_list = []
    for headline, summary in zip(df["headline"].tolist(), df["summary"].tolist()):
        article_list.append({"headline": headline, "summary": summary})

    prompt = f"""
    You are a news editor for a news website. These are a list of news articles headlines and content. Identify the top {NUMBER_OF_HEADLINES} major topics that was reported.
    
    When choosing the major topics, you should:
    1. Consider the number of articles reporting on the issue. More reporting indicates wider public interest.
    2. Consider the issue's impact on the society as a whole and the economy.
    3. Policy proposals and discussion should generally be accorded higher priority. For these topics, sometime it is useful to combine several issues under an overarching theme.
    4. Do not summarise court cases for different issues into a single topic.
    5. Court cases should only be included if they have widespeard impact on the society.
    6. In any case, there should not be more than {round(NUMBER_OF_HEADLINES * 0.4)} topics related to court cases.

    Summarise each topic into a concise, news headline format. Your output should be in JSON with a single key "topics", containing a list of {NUMBER_OF_HEADLINES} descriptions. Do not wrap the json codes in JSON markers.

    Articles:
    {article_list}
    """

    print("Generating topics...")
    return generate_response(prompt)

def generate_articles_list_by_topic(major_themes: json, headlines: pd.DataFrame):
    prompt = f"""
    You are a news editor for a news website. These are a number of major themes that we will cover.

    Major Themes:
    {major_themes}

    Here are a list of headlines with the article uuid. Try to group them under the major themes provided. If the headline does not fit any of the major themes, group it under “Other”.

    Headlines & uuid:
    {headlines}

    Your output should be in JSON format. The key should be the provided themes and others, and the value should be a list of dictionary, with "headline" and "uuid" keys. Do not wrap the json codes in JSON markers.
    """

    print("Generating articles list by topic...")
    return generate_response(prompt)

def topic_summary(topic: str, article_text: str):
    prompt = f"""
    You are a news editor for a news website. You are going to write a news summary for the topic: {topic}. You will be provided with a number of articles related to the topic, including the article headline and the article text.
    
    When writing the summary, you should:
    1. Only use the material available from the articles provided
    2. Provide a brief summary of the topic
    3. If the article contains quotes from people, try to include them as much as possible
    4. If a person's quote is responding to another person's quote, try to include both quotes
    5. Do not include addtional comments that is not present in the provided articles
    6. You should write between 250 and 600Chinese characters.
    
    Here are the articles: {article_text}

    Your output should be in JSON format. The key should be "summary" and the value should be the summary of the article.
    """

    print(f"Generating summary for topic {topic}...")
    return generate_response(prompt)

def subedit_summary(summary: str) -> str:
    prompt = f"""
    Please act as a news subeditor. Your goal is to edit the following news summary (provided in Markdown format) for consistent style and presentation, while strictly adhering to the following guidelines.  It's important to maintain the original information and avoid adding any new content or rewriting the core meaning.

    **Style Guidelines:**

    1. **Character Set:** Use Traditional Chinese characters primarily. English is acceptable for proper nouns lacking direct Traditional Chinese translations.
    2. **Person Titles:** Ensure consistent titling for individuals throughout the summary.
    3. **Title Usage:** Avoid unnecessary honorifics like 先生, 女士. Use concise and professional titles where appropriate.
    4. **Date Format:** Replace general terms like "today" with specific dates.
    5. **Summary Length:**  Aim for each topic summary to be approximately 250-600 words. Focus on conciseness and information density within this range.

    **Input Summary (Markdown):**
    {summary}

Your output should be in JSON format. The key should be "summary" and the value should be the edited summary in markdown format.
    """
    print(f"Editing summary...")
    return generate_response(prompt)
