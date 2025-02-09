import os
import sys
import json
import feedparser
import pandas as pd
import markdownify
import re
import gemini
from utils import generate_article_text, generate_article_links, append_summary_and_links
from uuid import uuid4

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
}

def html_to_markdown(html_content):
    if not html_content:
        return ""
    markdown_text = markdownify.markdownify(html_content)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text).strip()
    # remove html tags
    markdown_text = re.sub(r'<[^>]*>', '', markdown_text)
    return markdown_text

# Function to extract news data from RSS feeds
def extract_news_data():
    news_items = []
    for feed_title, feed_url in rss_feeds.items():
        print(f"Extracting news data from {feed_title}...")
        
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries:
            news_item = {
                    "uuid": uuid4().hex,
                    "headline": entry.get("title"),
                    "published": entry.get("published"),
                    "summary": (html_to_markdown(entry.get("summary", ""))[:300] + " ...") if len(html_to_markdown(entry.get("summary"))) > 300 else html_to_markdown(entry.get("summary", "")),
                    "content": html_to_markdown(entry.get("content", [{}])[0].get("value")),
                    "url": entry.get("link"),
                    "image_links": None,  # Ignoring thumbnails as requested
                    "source": feed.feed.get("title"),
                    "categories": ", ".join(tag["term"] for tag in entry.get("tags", []) if "term" in tag),
                }
            news_items.append(news_item)
    return news_items


# Function to save news data to a CSV file
def save_to_csv(news_items, filename="news_data.csv"):
    df = pd.DataFrame(news_items)
    df.to_csv(filename, index=False)
 

# Main execution
if __name__ == "__main__":
    # news_data = extract_news_data()
    # save_to_csv(news_data)

    df = pd.read_csv("news_data.csv")
    df.set_index('uuid', inplace=True)    
    df.published = pd.to_datetime(df.published)
    today = pd.Timestamp.today()
    week_ago = pd.Timestamp(today - pd.Timedelta(days=7)).tz_localize('UTC')
    df = df[df.published > week_ago]

    with open(os.path.join(temp_dir, '00-headlines.txt'), 'w') as f:
        f.truncate(0)  # clear the file
        for uuid, row in df.iterrows():
            f.write(f"{uuid}: {row['headline']}\n{row['summary']}\n\n")

    topics = gemini.generate_topics(df[["headline", "summary"]])
    articles_by_topic = gemini.generate_articles_list_by_topic(topics, df[["headline"]])

    with open(os.path.join(temp_dir, '01-topics.json'), 'w') as f:
        json.dump(topics, f, ensure_ascii=False, indent=4)
    with open(os.path.join(temp_dir, '02-articles_by_topic.json'), 'w') as f:
        json.dump(articles_by_topic, f, ensure_ascii=False, indent=4)

    topics = json.load(open('01-topics.json'))
    articles_by_topic = json.load(open('02-articles_by_topic.json'))

    major_topics = list(articles_by_topic.keys())[:-1]
    topics_summary = {}
    topics_link = {}
    full_text = ""

    for topic in major_topics:
        articles = articles_by_topic[topic]
        articles_text = generate_article_text(articles, df)
        articles_links = generate_article_links(articles, df)
        topics_summary[topic] = gemini.topic_summary(topic, articles_text)
        topics_link[topic] = articles_links
        full_text = append_summary_and_links(full_text, topic, topics_summary[topic], articles_links)

    formatted_summary = gemini.subedit_summary(full_text)["summary"]

    with open(os.path.join(temp_dir, '03-topics_summary.txt'), 'w') as f:
        for topic, summary in topics_summary.items():
            f.write(f"{topic}\n{summary}\n\n")

    with open(os.path.join(temp_dir, '04-topics_link.txt'), 'w') as f:
        for topic, link in topics_link.items():
            f.write(f"##{topic}\n{link}\n\n")

    with open(os.path.join(temp_dir, '05-full_text.txt'), 'w') as f:
        f.write(full_text)

    with open(os.path.join(temp_dir, '06-formatted_summary.txt'), 'w') as f:
        f.write(formatted_summary)

    print("Done!")
    



    
    



