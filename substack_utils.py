import os
import json
import time
import dotenv
from substack import Api
from substack.post import Post
from substack.exceptions import SubstackAPIException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

dotenv.load_dotenv()


def login_to_substack(email, password):
    """
    Log in to Substack using Selenium and save cookies in JSON format.
    """
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")

    # service = Service("/usr/local/bin/chromedriver")  # Adjust path if needed
    # driver = webdriver.Chrome(service=service, options=chrome_options)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)

    try:
        driver.get("https://substack.com/sign-in")

        wait = WebDriverWait(driver, 200)
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        email_field.send_keys(email)

        sign_in_link = wait.until(
            EC.element_to_be_clickable((By.LINK_TEXT, "Sign in with password"))
        )
        sign_in_link.click()

        password_field = wait.until(
            EC.presence_of_element_located((By.NAME, "password"))
        )
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)

        time.sleep(20)  # Adjust if needed for slower connections

        cookies = driver.get_cookies()
        with open("substack_cookies.json", "w") as file:
            json.dump(cookies, file)
        print("Cookies saved to 'substack_cookies.json'.")

    finally:
        driver.quit()


def retry_on_502(func, max_retries=3, delay=1):
    """
    Retry function on 502 error with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except SubstackAPIException as e:
            if "502 Bad Gateway" in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (2**attempt))
                continue
            raise


def retry_on_error(func, max_retries=3, delay=1):
    """
    Retry function on general Substack API errors with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except SubstackAPIException as e:
            if attempt < max_retries - 1:
                time.sleep(delay * (2**attempt))
                continue
            raise


def publish_newsletter_to_substack(api, title, content, topics):
    """
    Publish the newsletter using python-substack.
    """
    profile = retry_on_502(lambda: api.get_user_profile())
    user_id = profile.get("id")
    if not user_id:
        raise ValueError("Could not get user ID from profile")

    post = Post(title=title, subtitle=f"Topics: {', '.join(topics)}", user_id=user_id)

    post.add_v2({"content": "<h4>This is a heading</h4>"})

    # # Add content

    # post.add(
    #     {
    #         "type": "paragraph",
    #         "content": "This is how you add a new paragraph to your post!",
    #     }
    # )

    # # bolden text
    # post.add(
    #     {
    #         "type": "paragraph",
    #         "content": [
    #             {"content": "This is how you "},
    #             {"content": "bolden ", "marks": [{"type": "strong"}]},
    #             {"content": "a word."},
    #         ],
    #     }
    # )

    # # add hyperlink to text
    # post.add(
    #     {
    #         "type": "paragraph",
    #         "content": [
    #             {
    #                 "content": "View Link",
    #                 "marks": [
    #                     {"type": "link", "href": "https://whoraised.substack.com/"}
    #                 ],
    #             }
    #         ],
    #     }
    # )

    # for section in content:
    #     post.add({"type": "paragraph", "content": section})
    #     post.add({"type": "divider"})
    # # set paywall boundary
    # post.add({"type": "paywall"})

    print(f"Draft content: {post.get_draft()}")  # For debugging

    # Create draft
    draft = retry_on_error(lambda: api.post_draft(post.get_draft()))
    draft_id = draft.get("id")
    if not draft_id:
        raise ValueError("Failed to create draft - no ID returned")

    # Pre-publish checks
    retry_on_error(lambda: api.prepublish_draft(draft_id))

    # Uncomment if you want to fully publish:
    # retry_on_error(lambda: api.publish_draft(draft_id))

    print("Newsletter published (drafted) successfully!")


if __name__ == "__main__":
    email = os.getenv("SUBSTACK_EMAIL")
    password = os.getenv("SUBSTACK_PASSWORD")
    cookies_path = os.path.join("temp", "substack_cookies.json")

    # Step 1: If cookies file doesn’t exist, perform login via Selenium
    if not os.path.exists(cookies_path):
        login_to_substack(email, password)

    # Step 2: Convert Selenium cookies (list of dicts) to {name: value}
    with open(cookies_path, "r") as f:
        selenium_list = json.load(f)

    cookie_dict = {}
    for c in selenium_list:
        cookie_dict[c["name"]] = c["value"]

    with open("selenium_cookies.json", "w") as f:
        json.dump(cookie_dict, f)

    # Step 3: Initialize the Api with the re-formatted cookies
    try:
        api = Api(
            cookies_path="temp/selenium_cookies.json",
            publication_url="https://hknewsdigest.substack.com",
        )
        print("Successfully authenticated with Substack API")
    except Exception as e:
        print(f"Authentication failed: {e}")
        raise

    # Step 4: Prepare your newsletter data
    newsletter_title = "My First Newsletter"
    newsletter_content = [
        "Hello subscribers!",
        "This is <strong>just</strong> a short example newsletter content.",
        "Stay tuned for more updates.",
    ]
    newsletter_topics = ["Greetings", "Update", "Community"]

    # Step 5: Publish (or create a draft) on Substack
    publish_newsletter_to_substack(
        api, newsletter_title, newsletter_content, newsletter_topics
    )
