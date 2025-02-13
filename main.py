import os
import json
import pandas as pd
import gemini
from utils import (
    generate_article_text,
    generate_article_links,
    append_summary_and_links,
    extract_news_data,
    save_to_csv,
)


temp_dir = "temp"
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)

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

BEST_OF_OPTION = 3
NUMBER_OF_TOPICS = 5

# Main execution
if __name__ == "__main__":
    # news_data = extract_news_data(rss_feeds)
    # save_to_csv(news_data)

    df = pd.read_csv("news_data.csv")
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
            articles = topic["articles"]
            articles_text = generate_article_text(articles, df)
            articles_links = generate_article_links(articles, df)
            topics_summary["topics"].append(
                gemini.topic_summary(topic["topic"], articles_text)
            )
            topics_link.append({"topic": topic, "link": articles_links})

        formatted_summary = gemini.subedit_summary(topics_summary)

        with open(os.path.join(temp_dir, "topics_summary.json"), "w") as f:
            json.dump(formatted_summary, f, ensure_ascii=False, indent=4)
        with open(os.path.join(temp_dir, "topics_link.json"), "w") as f:
            json.dump(topics_link, f, ensure_ascii=False, indent=4)

        # Pre edited version
        pre_edited_text = append_summary_and_links(topics_summary, topics_link)
        # Post edited version
        edited_text = append_summary_and_links(formatted_summary, topics_link)

        final_text.append({"summary_id": i, "text": edited_text})

        with open(os.path.join(temp_dir, "03-topics_summary.txt"), "w") as f:
            for topic in topics_summary["topics"]:
                f.write(f"{topic["topic"]}\n{topic["summary"]}\n\n")

        with open(os.path.join(temp_dir, "04-topics_link.txt"), "w") as f:
            for topic in topics_link:
                f.write(f"##{topic["topic"]}\n{topic["link"]}\n\n")

        with open(os.path.join(temp_dir, "05-full_text.md"), "w") as f:
            f.write(pre_edited_text)

        with open(os.path.join(temp_dir, "06-pre_edited_summary.md"), "w") as f:
            f.write(pre_edited_text)

        with open(os.path.join(temp_dir, "07-formatted_summary.md"), "w") as f:
            f.write(edited_text)

    with open(os.path.join(temp_dir, "final_text.json"), "w") as f:
        json.dump(final_text, f, ensure_ascii=False, indent=4)

    for index, item in enumerate(final_text):
        with open(os.path.join(temp_dir, f"summary_{index+1}.md"), "w") as f:
            f.write(item["text"])

    with open(os.path.join(temp_dir, "final_text.json"), "r") as f:
        final_text = json.load(f)

    score = gemini.evaluate_output(BEST_OF_OPTION, final_text)
    print("===========SCORE==============")
    print(score)
    print("==============================")
    print("Done!")
