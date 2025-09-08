from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from notion_client import Client
import time
import re
import os
from dotenv import load_dotenv

load_dotenv()

# --- 설정 ---
# Notion API 토큰과 데이터베이스 ID 설정
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

# Notion 클라이언트 초기화
notion = Client(auth=NOTION_TOKEN)


def get_science_contests_with_selenium():
    """Scrapes science/engineering contests from Linkareer using Selenium."""
    # URL for science/engineering contests
    url = "https://linkareer.com/list/contest?filterBy_categoryIDs=35&filterType=CATEGORY&orderBy_direction=DESC&orderBy_field=CREATED_AT&page=1"

    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument('headless')

    driver = webdriver.Chrome(service=service, options=options)
    contest_list = []

    try:
        driver.get(url)
        # Wait for the page to fully load dynamic content
        time.sleep(5)

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')

        # Find all contest items using a more stable class name
        # Based on your HTML, 'activity-list-card-item-wrapper' is the parent container.
        items = soup.find_all('div', class_='activity-list-card-item-wrapper')

        if not items:
            print("❌ No contest items found. Check the HTML structure.")
            return []

        for item in items:
            try:
                # Extract title and link from the anchor tag
                title_tag = item.select_one('a.image-link')
                if title_tag:
                    link = "https://linkareer.com" + title_tag['href']
                    # The title text is in the h5 tag
                    title = item.select_one('h5.activity-title').get_text(strip=True)
                else:
                    title = "제목 없음"
                    link = ""

                # Extract host organization
                host_tag = item.find('p', class_='organization-name')
                host = host_tag.get_text(strip=True) if host_tag else "주최자 없음"

                # Extract deadline from the second info text section
                info_text_div = item.find('div', class_=re.compile(r'SecondInfoText__StyledWrapper'))
                deadline = "마감일 없음"
                if info_text_div:
                    # The deadline is the first child div. Let's find a div with a 'D-' pattern.
                    deadline_tag = info_text_div.find('div')
                    if deadline_tag and 'D-' in deadline_tag.get_text():
                        deadline = deadline_tag.get_text(strip=True)

                contest_list.append({
                    "title": title,
                    "link": link,
                    "host": host,
                    "deadline": deadline
                })
            except Exception as e:
                print(f"Error during item parsing: {e}")
                continue

    finally:
        driver.quit()

    return contest_list


# Functions for Notion API are the same as before
def get_existing_titles(database_id):
    existing_titles = set()
    try:
        results = notion.databases.query(database_id=DATABASE_ID).get("results")
        for page in results:
            title_prop = page.get("properties", {}).get("이름", {})
            if "title" in title_prop and title_prop["title"]:
                existing_titles.add(title_prop["title"][0]["plain_text"])
    except Exception as e:
        print(f"Failed to fetch existing data from Notion: {e}")
    return existing_titles


def add_contest_to_notion(contest, database_id):
    # Validate data before sending to Notion
    if not contest.get("title") or not contest.get("link"):
        print(f"❌ Data validation failed: title or link is empty. Data: {contest}")
        return

    properties = {
        "이름": {"title": [{"text": {"content": contest["title"]}}]},
        "주최": {"rich_text": [{"text": {"content": contest["host"]}}]},
        "마감일": {"rich_text": [{"text": {"content": contest["deadline"]}}]},
        "링크": {"url": contest["link"]}
    }

    try:
        notion.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )
        print(f"✅ Successfully added '{contest['title']}' to Notion!")
    except Exception as e:
        print(f"❌ Failed to add to Notion: {e}")


if __name__ == "__main__":
    print("🚀 Starting Linkareer science/engineering contest scraping using Selenium...")

    existing_titles = get_existing_titles(DATABASE_ID)
    print(f"Number of contests already in Notion: {len(existing_titles)}")

    latest_contests = get_science_contests_with_selenium()

    new_contests_count = 0
    for contest in latest_contests:
        if contest.get("title") and contest["title"] not in existing_titles:
            add_contest_to_notion(contest, DATABASE_ID)
            new_contests_count += 1

    if new_contests_count == 0:
        print("No new science/engineering contest information found. 😴")