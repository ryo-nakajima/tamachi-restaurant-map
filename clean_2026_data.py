"""
2026年データのクリーニング
- ラーメン: 主ジャンルがラーメン/つけ麺/担々麺の店のみ残す
- 牛丼: ジャンルに「牛丼」を含む店のみ + 欠落チェーン店を個別取得
"""
import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

RAMEN_PRIMARY_GENRES = {"ラーメン", "つけ麺", "担々麺", "油そば・まぜそば", "汁なし担々麺"}


def clean_ramen_2026():
    """ラーメン2026: 主ジャンルがラーメン系の店のみに絞る"""
    with open(os.path.join(DATA_DIR, "ramen_2026.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    cleaned = []
    removed = []
    for row in rows:
        genre = row.get("genre", "")
        parts = [g.strip() for g in genre.split(",")]
        # parts[0]=駅, parts[1]=地域, parts[2]=主ジャンル
        main_genre = parts[2] if len(parts) > 2 else ""
        if main_genre in RAMEN_PRIMARY_GENRES:
            cleaned.append(row)
        else:
            removed.append((row["name"], main_genre))

    # 重複除去
    seen = set()
    deduped = []
    for row in cleaned:
        if row["name"] not in seen:
            seen.add(row["name"])
            deduped.append(row)

    print(f"ラーメン2026: {len(rows)} → {len(deduped)} (除外: {len(removed)})")
    for name, genre in removed:
        print(f"  除外: {name} (主ジャンル: {genre})")

    return deduped


def clean_gyudon_2026():
    """牛丼2026: ジャンルに「牛丼」を含む店のみ"""
    with open(os.path.join(DATA_DIR, "gyudon_2026.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    cleaned = []
    removed = []
    for row in rows:
        genre = row.get("genre", "")
        if "牛丼" in genre:
            cleaned.append(row)
        else:
            removed.append(row["name"])

    print(f"\n牛丼2026: {len(rows)} → {len(cleaned)} (除外: {len(removed)})")
    for name in removed:
        print(f"  除外: {name}")

    return cleaned


def search_missing_gyudon():
    """
    欠落している牛丼チェーン店を食べログで個別検索して追加
    """
    missing_candidates = [
        # (検索名, 期待される店名の一部)
        ("松屋 三田", "松屋"),
        ("なか卯 芝浦", "なか卯"),
        ("すき家 芝浦四丁目", "すき家"),
    ]

    found = []
    for query, expected in missing_candidates:
        url = f"https://tabelog.com/tokyo/A1314/A131402/rstLst/?vs=1&sk={query}&svd=20260406&svt=1900&svps=2&hfc=1&sw={query}"
        print(f"\n  検索: {query}")
        try:
            time.sleep(3)
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.select("a.list-rst__rst-name-target"):
                name = a.get_text(strip=True)
                href = a.get("href", "")
                if expected in name:
                    print(f"    発見: {name} → {href}")
                    # 詳細ページから座標取得
                    time.sleep(3)
                    detail_resp = requests.get(href, headers=HEADERS, timeout=15)
                    detail_html = detail_resp.text
                    lat_m = re.search(r"lat['\"]?\s*[:=]\s*([0-9]+\.[0-9]+)", detail_html)
                    lng_m = re.search(r"lng['\"]?\s*[:=]\s*([0-9]+\.[0-9]+)", detail_html)
                    addr_soup = BeautifulSoup(detail_html, "html.parser")
                    addr_tag = addr_soup.select_one("p.rstinfo-table__address")
                    address = addr_tag.get_text(strip=True) if addr_tag else ""

                    rating_tag = addr_soup.select_one("b.c-rating__val")
                    if not rating_tag:
                        rating_tag = addr_soup.select_one("span.rdheader-rating__score-val-dtl")
                    rating = float(rating_tag.get_text(strip=True)) if rating_tag else ""

                    if lat_m and lng_m:
                        found.append({
                            "name": name,
                            "address": address,
                            "lat": lat_m.group(1),
                            "lng": lng_m.group(1),
                            "rating": rating,
                            "reviews": "",
                            "genre": f"牛丼",
                            "closed": "",
                            "url": href,
                        })
                        print(f"    座標: ({lat_m.group(1)}, {lng_m.group(1)})")
                    break
        except Exception as e:
            print(f"    エラー: {e}")

    return found


def save_csv(rows, path, fieldnames=None):
    if not fieldnames:
        fieldnames = rows[0].keys() if rows else []
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"保存: {path} ({len(rows)}件)")


if __name__ == "__main__":
    print("=== ラーメン2026 クリーニング ===")
    ramen_clean = clean_ramen_2026()

    print("\n=== 牛丼2026 クリーニング ===")
    gyudon_clean = clean_gyudon_2026()

    print("\n=== 欠落牛丼チェーン検索 ===")
    missing = search_missing_gyudon()
    if missing:
        gyudon_clean.extend(missing)
        print(f"\n  追加: {len(missing)}店")

    # 保存
    fields = ["name", "address", "lat", "lng", "rating", "reviews", "genre", "closed", "url"]
    save_csv(ramen_clean, os.path.join(DATA_DIR, "ramen_2026.csv"), fields)
    save_csv(gyudon_clean, os.path.join(DATA_DIR, "gyudon_2026.csv"), fields)

    print(f"\n=== 最終結果 ===")
    print(f"ラーメン2026: {len(ramen_clean)}店")
    print(f"牛丼2026: {len(gyudon_clean)}店")
