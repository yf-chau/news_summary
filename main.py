import os
import sys
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
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
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

BEST_OF_OPTION = 5
NUMBER_OF_TOPICS = 5

# Main execution
if __name__ == "__main__":
    # news_data = extract_news_data(rss_feeds)
    # save_to_csv(news_data)

    articles = """
    女經理指投訴公司董事言語性騷擾後遭孤立　入稟向安樂工程旗下公司及上司追討賠償
    安樂工程旗下公司一名行政經理，指在 2021 至 2023 年間，遭公司男董事多次言語性騷擾，她周二（11 日）入稟區域法院，指遭男董事及公司性別歧視，要求書面道歉及賠償損失。  
    
    入稟狀指，申訴人遭董事公開評論其身材姣好、「風韻猶存」，應派做公關知客招待客人，又嘲弄她以消毒搓手液「顏射」男同事，及指她偏愛外籍前上司，「快啲去屌個死鬼佬啦，去含 X 啦」等。  
    
    申訴人向公司投訴後，得悉個案交由安樂工程集團主席潘樂陶及遭投訴的董事共同處理，又獲告知上述行為是「公司文化」；其後申訴人遭孤立及被剝奪晉升機會。

    ##### **入稟狀：上司形容「風韻猶存」應做知客****誣捏曾任夜店經理**

    申訴人為楊慧儀，答辯人為安樂機電設備工程有限公司，及公司首席執行董事兼董事總經理鄭偉能。

    入稟狀指，楊自 1990 年在安樂工程集團旗下不同公司工作，至 2024 年 8 月離職前，入職約 34 年。約於 2010 年，楊開始在安樂機電設備工程有限公司工作，並於 2021 年起，經常受到上司鄭偉能言語性騷擾，包括使用帶有性意味的粗俗字眼。

    其中在 2021 年 7 月 28 日一個部門聚餐上，鄭在其他同事面前公開評論申訴人的身材，表示「應該派 Jackie 姐呢啲咁好身材同風韻猶存嘅女同事去做公關知客招待客人」。

    10 月 21 日另一場部門聚餐上，鄭在其他同事面前，誣捏申訴人曾任夜總會經理，著她帶另一位曾任空中服務員的女同事到他桌前，言語帶有強烈的性邀請意味。

    入稟狀指，鄭隨後更向其他同事指「我同 Jackie 有嘢（意指『有路』）喇」，令申訴人感到非常尷尬，羞辱、騷擾和冒犯。

    ##### **嘲弄申訴人以洗手液顏射同事****席間男同事聞言大笑**

    約於 2022 年 6 月 20 日，申訴人與另外約 10 名男同事開會，席上她是唯一一名女性，申訴人使用桌上一支消毒搓手液時，不慎將搓手液噴到一名男經理身上，遭鄭嘲弄試圖「顏射」該男經理，在場男同事聞言大笑。

    同年 12 月 22 日，鄭與申訴人通電話時，再次使用粗俗言語侮辱申訴人，包括提到性器官、性交等字眼。鄭又質疑楊為何在公司報告中讚揚前主管 John Collie，而沒有稱讚鄭，令申訴人受威嚇及感到尷尬。

    ##### **質疑申訴人偏愛前上司****要求大聲承諾最喜歡答辯人**

    至 2023 年 3 月 22 日，申訴人與直屬上司在會議室時，鄭出現並要求兩人互數缺點。入稟狀指，兩人受威脅下只好照做，期間鄭質疑申訴人為何告訴安樂集團創始人兼執行董事潘樂陶，她只喜歡外籍前上司，「你咁鍾意個死鬼佬，你鍾意湊鬼呀嘛，快啲去屌個死鬼佬啦，去含 X 啦」。鄭又要求申訴人日後被問到喜歡哪位上司時，只能說最喜歡他，並指示申訴人即場大聲反覆作出承諾。

    入稟狀指，同年 4 月 1 日，申訴人所有男同事和下屬均獲升職，而申訴人作為團隊裏唯一的女性，即使工作表現獲讚賞，亦不獲升職，行為構成性別歧視。

    ##### **投訴後得知由潘樂陶及答辯人處理****獲告知上司行為屬「公司文化」**

    約於同年 4 月 24 日，申訴人以電郵聯絡安樂集團人事部投訴鄭偉能。申訴人的直屬上司在 5 月初通知申訴人，她的投訴將由潘樂陶和鄭偉能一同處理。申訴人不同意，認為由被指控者處理投訴對她不公，惟她獲告知這是潘樂陶的指示。

    另外，在申訴人的反對下，公司仍然安排她與 10 名男同事在同年 5 月 5 日開會。她又認為，其投訴被公司無視，甚至獲告知鄭的行為，包括使用有性器官或代表性交的字眼，屬「公司文化」。

    ##### **投訴後被孤立　跟進項目被轉走**

    入稟狀指，自申訴人提出投訴後遭孤立，鄭要求其他同事不要接觸申訴人。同年 10 月，申訴人原本跟進的項目，被轉交其他同事負責；同一時間，鄭指示申訴人的下屬，不要將申訴人當作上司看待。申訴人不獲安排任何重要工作會議或項目，甚至被上司質疑她為何時常使用洗手間。

    ##### **要求答辯人書面道歉及賠償**

    入稟狀指，上述行為製造一個對申訴人不利、甚至敵對的工作環境，構成性別歧視，而公司容許鄭偉能製造這個敵對的工作環境。

    申訴人最後向平等機會委員會投訴，張志宇律師行替申訴人入稟申訴，要求法庭宣告答辯人違反《性別歧視條例》，須向申訴人書面道歉並賠償損失，包括醫療、輔導等費用，及支付懲罰性賠償，入稟狀未有列明金額。

    ```
    DCEO2/2025
    ```

    「安樂工程」旗下公司前女經理指被男高層性騷擾入稟索償　曾投訴反被告知屬「公司文化和傳統」
    !

    **前律政司司長鄭若驊丈夫潘樂陶旗下的「安樂工程集團」、其附屬公司的一名前女經理指控，公司男高層在同事聚會等場合，屢次出言性騷擾，包括使用含性器官的粗言穢語、訛稱事主曾是夜總會領班等，事主不堪受辱向公司投訴，卻被告知性騷擾言行屬「公司文化和傳統」，事後遭排斥及職權騷擾，需接受心理治療。女事主兩日前（11日）透過律師代表，入稟區域法院，向涉事男高層及公司追討賠償，指他們違反《性別歧視條例》。**

    訂閱《庭刊》

    申索人為楊慧儀，答辯人為鄭偉能及安樂機電設備工程公司。入稟狀透露，楊自1990年已受聘於安樂工程集團旗下公司，於2010年開始在涉案公司工作，擔任電話服務中心經理，現已離職；鄭偉能則是涉案公司的總執行董事和董事總經理。

    事主被男高層在同事聚會中　公開訛稱曾任夜總會領班而感尷尬受辱
    ------------------------------

    入稟狀指，申索人自2021年開始，經常受到鄭言語侮辱，包括使用粗言穢語及含性器官字眼，鄭亦會在同事面前，對申索人說色情笑話。2021年7月，一次部門自助餐聚會期間，鄭公開表示：「應該派Jackie姐（女事主）呢啲咁好身材同風韻猶存嘅女同事去做公關知客招待客人。」鄭又在另一些同事聚會中，訛稱申索人曾是夜總會領班、「我同Jackie有嘢」等，令申索人感尷尬、受侮辱及威脅。

    入稟狀續敍述其他事件，包括於2023年3月，鄭在會議室要求申索人和其直屬主管互相點出對方不是，兩人感受威脅只得服從，唯鄭用粗言辱罵二人，其間問申索人為何向安樂集團主席潘樂陶表示，自己只喜歡外籍前上司，並一度向她稱：「你咁鍾意個死鬼佬，你鍾意湊鬼呀嘛，快啲去屌個死鬼佬啦，去含X啦。」鄭之後要求申索人，必須說鄭是她最喜歡的上司，並要求她高聲重覆承諾。

    申索人所屬團隊所有男同事均獲升職　指唯一原因只能是性別歧視
    -----------------------------

    入稟狀又指，申索人所屬團隊的所有男同事均獲升職，申索人作為團隊中唯一女性，雖然工作表現可嘉，卻不獲升職，唯一原因只能是性別歧視，申索人升職機會因而被剝奪，而公司對鄭性騷擾行為的縱容和支持，亦令申索人處身充滿敵意的工作環境。  
    
    事主曾向人事部投訴性騷擾事件，惟後獲告知投訴會由潘樂陶及鄭一同處理。申索人反對，強調將她帶到性騷擾自己的人面前屬不公做法，亦不符公司營運守則，惟她卻獲告知這是潘樂陶的直接命令。

    2023年5月5日左右，申索人被強迫與超過10名公司男經理會面，其投訴其後不單被忽視，更被告知鄭的性騷擾言行、粗言穢語，屬於安樂機電設備工程公司的文化、傳統及或政策的一部分（is part of the culture, custom and/or policy of the 2nd Respondent）。會面後，申索人被排除在所有主要會議和工作項目之外，其男主管甚至質詢她去廁所的次數。

    入稟狀透露，申索人因受性騷擾，需接受醫療及心理輔導；又指鄭及涉案公司違犯《性別歧視條例》，要求法庭下令答辯方賠償及支付懲罰性訟費。

    法院：區域法院  
    申索人：楊慧儀  
    答辯人：鄭偉能、安樂機電設備工程公司  
    案件編號：DCEO2/2025

    ![](https://qr.payme.hsbc.com.hk/2/QrndvPxDgEi2MhNiNPz4b8)
    !

    **如欲接收每日報道整合，請在訊息欄內填寫電郵地址**
    """

    topic = "勞工權益爭議頻發：記者協會主席遭解僱提告、安樂工程爆性騷擾案"

    @retry(
        stop=stop_after_attempt(10),  # Stop after 5 attempts
        wait=wait_exponential(
            multiplier=1, min=2, max=60
        ),  # Exponential backoff, starting at 4s, max 60s
        retry=retry_if_exception_type(
            Exception
        ),  # Retry on any Exception (customize if needed)
    )
    def generate_summary(topic, articles):
        sanitised_input = gemini.sanitise_input_v2(topic, articles)

        with open(
            os.path.join(temp_dir, "sanitised_input.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(sanitised_input, f, ensure_ascii=False, indent=4)

        print("Trying to generate summary....")
        summary = gemini.topic_summary(topic, sanitised_input)
        with open(
            os.path.join(temp_dir, "sanitised_summary.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(summary, f, ensure_ascii=False, indent=4)
        print("Summary generated")

    generate_summary(topic, articles)
    sys.exit()

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
            if topic["topic"].lower() != "others":
                articles = topic["articles"]
                articles_text = generate_article_text(articles, df)
                articles_links = generate_article_links(articles, df)
                sanitised_input = gemini.sanitise_input(topic["topic"], articles_text)
                topics_summary["topics"].append(
                    gemini.topic_summary(topic["topic"], sanitised_input)
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

    score = gemini.evaluate_output(BEST_OF_OPTION, final_text)

    with open(os.path.join(temp_dir, "06-score.json"), "w") as f:
        json.dump(score, f, ensure_ascii=False, indent=4)
    print("===========SCORE==============")
    print(score)
    print("==============================")
    print("Done!")
