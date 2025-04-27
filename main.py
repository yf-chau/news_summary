import os
import json
import dotenv
import pandas as pd
import gemini
from datetime import datetime
from utils import (
    generate_article_text,
    generate_article_links,
    append_summary_and_links,
    extract_news_data,
    save_to_csv,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from substack_playwright import post_substack_draft

temp_dir = "temp"
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)

dotenv.load_dotenv()

# List of RSS feed URLs
rss_feeds = {
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

# Main execution
if __name__ == "__main__":
    # @retry(
    #     stop=stop_after_attempt(5),  # Stop after 5 attempts
    #     wait=wait_exponential(
    #         multiplier=1, min=2, max=60
    #     ),  # Exponential backoff, starting at 4s, max 60s
    #     retry=retry_if_exception_type(
    #         Exception
    #     ),  # Retry on any Exception (customize if needed)
    # )
    # def generate_summary(topic, articles):
    #     sanitised_input = gemini.sanitise_input_v2(topic, articles)

    #     with open(
    #         os.path.join(temp_dir, "sanitised_input.json"), "w", encoding="utf-8"
    #     ) as f:
    #         json.dump(sanitised_input, f, ensure_ascii=False, indent=4)

    #     print("Trying to generate summary....")
    #     summary = gemini.topic_summary(topic, sanitised_input)
    #     with open(
    #         os.path.join(temp_dir, "sanitised_summary.json"), "w", encoding="utf-8"
    #     ) as f:
    #         json.dump(summary, f, ensure_ascii=False, indent=4)
    #     print("Summary generated")

    news_data = extract_news_data(rss_feeds)
    csv_filepath = os.path.join(temp_dir, "news_data.csv")
    save_to_csv(news_data, csv_filepath)

    df = pd.read_csv(csv_filepath)
    df.set_index("uuid", inplace=True)
    df.published = pd.to_datetime(df.published)
    today = pd.Timestamp.today()
    week_ago = pd.Timestamp(today - pd.Timedelta(days=7)).tz_localize("UTC")
    df = df[df.published > week_ago]

    final_text = []

    for i in range(1, BEST_OF_OPTION + 1):
        print(f"Generating try {i} of {BEST_OF_OPTION}")

        topics = gemini.generate_topics(df[["headline", "summary"]], NUMBER_OF_TOPICS)
        articles_grouped_by_topic = gemini.generate_articles_list_by_topic(
            topics, df[["headline"]]
        )

        with open(os.path.join(temp_dir, "01-topics.json"), "w") as f:
            json.dump(topics, f, ensure_ascii=False, indent=4)
        with open(os.path.join(temp_dir, "02-articles_by_topic.json"), "w") as f:
            json.dump(articles_grouped_by_topic, f, ensure_ascii=False, indent=4)

        topics_summary = {"topics": []}
        topics_link = []
        full_text = ""

        for topic in articles_grouped_by_topic["topics"]:
            if topic["topic"].lower() != "others" and topic["topic"] != "其他":
                articles = topic["articles"]
                articles_text = generate_article_text(articles, df)
                articles_links = generate_article_links(articles, df)
                # sanitised_input = gemini.sanitise_input(topic["topic"], articles_text)
                topics_summary["topics"].append(
                    gemini.topic_summary(topic["topic"], articles_text)
                )
                topics_link.append({"topic": topic, "link": articles_links})

        formatted_summary = gemini.subedit_summary(topics_summary)

        with open(os.path.join(temp_dir, "03-topics_summary.json"), "w") as f:
            json.dump(formatted_summary, f, ensure_ascii=False, indent=4)
        with open(os.path.join(temp_dir, "04-topics_link.json"), "w") as f:
            json.dump(topics_link, f, ensure_ascii=False, indent=4)

        # Pre edited version
        pre_edited_text = append_summary_and_links(topics_summary, topics_link)
        # Post edited version
        edited_text = append_summary_and_links(formatted_summary, topics_link)

        final_text.append({"summary_id": i, "text": edited_text})

        with open(os.path.join(temp_dir, f"summary-{i}_pre_edited.md"), "w") as f:
            f.write(pre_edited_text)

        with open(os.path.join(temp_dir, f"summary-{i}_edited.md"), "w") as f:
            f.write(edited_text)

    with open(os.path.join(temp_dir, "05-final_text.json"), "w") as f:
        json.dump(final_text, f, ensure_ascii=False, indent=4)

    with open(os.path.join(temp_dir, "05-final_text.json"), "r") as f:
        final_text = json.load(f)

    best_score = gemini.evaluate_output(BEST_OF_OPTION, final_text)

    with open(os.path.join(temp_dir, "06-score.json"), "w") as f:
        json.dump(best_score, f, ensure_ascii=False, indent=4)

    post_substack_draft(
        title=f"{datetime.now().strftime('%B %d, %Y')} Hong Kong News Digest",
        content=final_text[best_score["summary_id"] - 1]["text"],
    )
