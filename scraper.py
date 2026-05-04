import asyncio
import httpx
import random
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from google.cloud import storage

# ===== 設定 =====
BUCKET_NAME = "curious4dev_boat"

BASE_RACELIST = "https://www.boatrace.jp/owpc/pc/race/racelist"
BASE_RESULT   = "https://www.boatrace.jp/owpc/pc/race/raceresult"
BASE_ODDS     = "https://www.boatrace.jp/owpc/pc/race/odds3t"

MAX_CONCURRENCY = 5
sem = asyncio.Semaphore(MAX_CONCURRENCY)

storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# =====================
# 共通
# =====================
async def fetch(client, url):
    async with sem:
        await asyncio.sleep(random.uniform(0.3, 1.0))
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        return r.text

def upload_json(path, data):
    blob = bucket.blob(path)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json"
    )

# =====================
# 出走表
# =====================
def parse_racelist(html, meta):
    # 修正前:
    # soup = BeautifulSoup(html, "lxml")
    # 修正後:
    soup = BeautifulSoup(html, "xml")

    table = soup.select_one(".is-w495")
    if not table:
        return []

    rows = table.find_all("tr")[1:]
    out = []

    for r in rows:
        cols = [c.text.strip() for c in r.find_all("td")]
        if len(cols) < 12:
            continue

        try:
            out.append({
                "date": meta["date"],
                "jcd": meta["jcd"],
                "race_no": meta["rno"],
                "lane": int(cols[0]),
                "racer_name": cols[3],
                "age": int(cols[4]),
                "branch": cols[5],
                "win_rate": cols[6],
                "local_win_rate": cols[7],
                "motor_no": cols[9],
                "boat_no": cols[11],
            })
        except:
            continue

    return out

# =====================
# 結果
# =====================
def parse_result(html, meta):
    # 修正前:
    # soup = BeautifulSoup(html, "lxml")
    # 修正後:
    soup = BeautifulSoup(html, "xml")

    table = soup.select_one(".is-w495")
    if not table:
        return []

    rows = table.find_all("tr")[1:]
    out = []

    for r in rows:
        cols = [c.text.strip() for c in r.find_all("td")]
        if len(cols) < 6:
            continue

        try:
            out.append({
                "date": meta["date"],
                "jcd": meta["jcd"],
                "race_no": meta["rno"],
                "rank": cols[0],
                "lane": cols[1],
                "racer_name": cols[2],
                "time": cols[5],
            })
        except:
            continue

    return out

# =====================
# オッズ
# =====================
def parse_odds(html, meta):
    # 修正前:
    # soup = BeautifulSoup(html, "lxml")
    # 修正後:
    soup = BeautifulSoup(html, "xml")

    rows = soup.select("tbody tr")

    out = []
    for r in rows:
        cols = [c.text.strip() for c in r.find_all("td")]
        if len(cols) < 2:
            continue

        out.append({
            "date": meta["date"],
            "jcd": meta["jcd"],
            "race_no": meta["rno"],
            "combination": cols[0],
            "odds": cols[1],
        })

    return out

# =====================
# 場単位処理
# =====================
async def process_stadium(client, date_str, jcd):
    racelist_all = []
    result_all = []
    odds_all = []

    for rno in range(1, 13):
        meta = {"date": date_str, "jcd": jcd, "rno": rno}

        # 出走表
        url = f"{BASE_RACELIST}?rno={rno}&jcd={jcd}&hd={date_str}"
        html = await fetch(client, url)
        racelist_all += parse_racelist(html, meta)

        # 結果
        url = f"{BASE_RESULT}?rno={rno}&jcd={jcd}&hd={date_str}"
        html = await fetch(client, url)
        result_all += parse_result(html, meta)

        # オッズ
        url = f"{BASE_ODDS}?rno={rno}&jcd={jcd}&hd={date_str}"
        html = await fetch(client, url)
        odds_all += parse_odds(html, meta)

    # ===== 保存 =====
    base = f"dt={date_str}/jcd={jcd}"

    upload_json(f"{base}/racelist.json", racelist_all)
    upload_json(f"{base}/results.json", result_all)
    upload_json(f"{base}/odds.json", odds_all)

    print(f"saved: {date_str} {jcd}")

# =====================
# 日単位処理
# =====================
async def run_one_day(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    date_param = target_date.strftime("%Y%m%d")

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = []

        for jcd in range(1, 25):
            j = str(jcd).zfill(2)
            tasks.append(process_stadium(client, date_param, j))

        await asyncio.gather(*tasks)

# =====================
# エントリ
# =====================
async def run_all():
    target = datetime.utcnow() - timedelta(days=1)
    await run_one_day(target)
