def generate_article_text(articles, df) -> str:
    article_text = ""
    for article in articles:
        article_headline = df.loc[article["uuid"]]["headline"]
        article_content = df.loc[article["uuid"]]["content"]
        article_text += f"{article_headline}\n{article_content}\n\n"
    return article_text

def generate_article_links(articles, df) -> str:
    article_hyperlink_in_markdown = ""
    for article in articles:
        article_headline = df.loc[article["uuid"]]["headline"]
        article_link = df.loc[article["uuid"]]["url"]
        article_source = df.loc[article["uuid"]]["source"]
        article_hyperlink_in_markdown += f"* [{article_source}：{article_headline}]({article_link})\n"
    return article_hyperlink_in_markdown


def append_summary_and_links(full_text, topic, summary, links) -> str:
    full_text += "## " + topic + "\n\n"
    full_text += summary["summary"]
    full_text += "\n\n"
    full_text += "#### Links\n\n"
    full_text += links
    full_text += "\n\n"

    return full_text