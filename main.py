from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from notion_client import Client
import time
import re
import os
from dotenv import load_dotenv
from datetime import date, timedelta

load_dotenv()

# --- 설정 ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

notion = Client(auth=NOTION_TOKEN)


def parse_deadline_to_date(deadline_text):
    """'D-14', '오늘마감' 등의 텍스트를 'YYYY-MM-DD' 형식의 날짜로 변환합니다."""
    try:
        if 'D-' in deadline_text:
            days_left = int(re.search(r'D-(\d+)', deadline_text).group(1))
            deadline_date = date.today() + timedelta(days=days_left)
            return deadline_date.isoformat()
        elif '오늘마감' in deadline_text:
            return date.today().isoformat()
        else:
            return None
    except (ValueError, AttributeError):
        return None


def get_science_contests_with_selenium():
    """Scrapes science/engineering contests from Linkareer using Selenium."""
    url = "https://linkareer.com/list/contest?filterBy_categoryIDs=35&filterType=CATEGORY&orderBy_direction=DESC&orderBy_field=CREATED_AT&page=1"
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = webdriver.Chrome(service=service, options=options)
    contest_list = []

    try:
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', class_='activity-list-card-item-wrapper')

        if not items:
            print("❌ No contest items found. Check the HTML structure.")
            return []

        for item in items:
            try:
                title_tag = item.select_one('a.image-link')
                if title_tag:
                    link = "https://linkareer.com" + title_tag['href']
                    title = item.select_one('h5.activity-title').get_text(strip=True)
                else:
                    title, link = "제목 없음", ""

                host_tag = item.find('p', class_='organization-name')
                host = host_tag.get_text(strip=True) if host_tag else "주최자 없음"

                info_text_div = item.find('div', class_=re.compile(r'SecondInfoText__StyledWrapper'))
                deadline_text = "마감일 정보 없음"
                if info_text_div:
                    deadline_tag = info_text_div.find('div')
                    if deadline_tag:
                        deadline_text = deadline_tag.get_text(strip=True)
                
                deadline_iso_date = parse_deadline_to_date(deadline_text)

                contest_list.append({
                    "title": title, "link": link, "host": host,
                    "deadline_date": deadline_iso_date
                })
            except Exception as e:
                print(f"Error during item parsing: {e}")
                continue
    finally:
        driver.quit()
    return contest_list


def get_existing_titles(database_id):
    """Notion DB에서 기존 공모전 제목들을 가져옵니다."""
    existing_titles = set()
    try:
        response = notion.databases.query(database_id=database_id)
        for page in response.get("results", []):
            title_prop = page.get("properties", {}).get("이름", {})
            if "title" in title_prop and title_prop["title"]:
                existing_titles.add(title_prop["title"][0]["plain_text"])
    except Exception as e:
        print(f"Failed to fetch existing data from Notion: {e}")
    return existing_titles


def add_contest_to_notion(contest, database_id):
    """'교내/교외' 속성을 포함하여 Notion에 공모전 정보를 추가합니다."""
    if not contest.get("title") or not contest.get("link"):
        print(f"❌ Data validation failed: {contest}")
        return

    properties = {
        "이름": {"title": [{"text": {"content": contest["title"]}}]},
        "주최": {"rich_text": [{"text": {"content": contest["host"]}}]},
        "링크": {"url": contest["link"]},
        # ✨ --- '교내/교외' 속성에 '교외' 값 자동 추가 --- ✨
        "교내/교외": {"select": {"name": "교외"}}
    }

    if contest.get("deadline_date"):
        properties["마감일"] = {"date": {"start": contest["deadline_date"]}}

    try:
        notion.pages.create(parent={"database_id": database_id}, properties=properties)
        print(f"✅ Successfully added '{contest['title']}' to Notion!")
    except Exception as e:
        print(f"❌ Failed to add to Notion: {e}")
        print(f"    Failing data: {properties}")


if __name__ == "__main__":
    print("🚀 Starting Linkareer contest scraping...")
    existing_titles = get_existing_titles(DATABASE_ID)
    print(f"Number of contests already in Notion: {len(existing_titles)}")
    latest_contests = get_science_contests_with_selenium()

    new_contests_count = 0
    for contest in latest_contests:
        if contest.get("title") and contest["title"] not in existing_titles:
            add_contest_to_notion(contest, DATABASE_ID)
            new_contests_count += 1

    if new_contests_count == 0:
        print("No new contest information found. 😴")