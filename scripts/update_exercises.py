#!/usr/bin/env python3
"""
Script tự động tìm kiếm và cập nhật thông tin các cuộc diễn tập quân sự trên thế giới
Chạy định kỳ 1-2 giờ/lần qua GitHub Actions hoặc Cronjob máy chủ.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "exercises.json")

def fetch_gdelt_military_exercises():
    query = '("military exercise" OR "joint exercise" OR "live-fire exercise" OR "naval drill" OR "联合演习" OR "共同訓練" OR "연합훈련")'
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + urllib.parse.quote(query)
        + "&mode=artlist&maxrecords=15&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MilExWatchBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return data.get("articles", [])
    except Exception as e:
        print(f"[WARN] GDELT fetch error: {e}")
        return []

def infer_domain_and_drills(title: str):
    t = title.lower()
    if any(k in t for k in ["naval", "sea", "maritime", "submarine", "fleet"]):
        return "Hải quân", "Hải quân & Chống ngầm", [
            "Tác chiến hiệp đồng biên đội tàu mặt nước và chống ngầm (ASW)",
            "Bảo đảm an ninh hàng hải và bắn đạn thật trên biển"
        ]
    if any(k in t for k in ["air defense", "missile", "drone", "uas", "fighter", "air force"]):
        return "Phòng không", "Phòng không & Chống UAV", [
            "Tác chiến phòng không - phòng thủ tên lửa tích hợp (IAMD)",
            "Phát hiện, chế áp thiết bị bay không người lái (Counter-UAS)"
        ]
    if any(k in t for k in ["cyber", "electronic"]):
        return "Tác chiến mạng", "Tác chiến mạng (Cyber)", [
            "Bảo vệ hạ tầng thông tin chỉ huy và ứng phó tấn công mạng"
        ]
    return "Đa miền", "Tác chiến Đa miền (OSINT)", [
        "Hiệp đồng chỉ huy tham mưu và cơ động lực lượng liên quân",
        "Thực binh bắn đạn thật và bảo đảm hậu cần - kỹ thuật chiến dịch"
    ]

def main():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    known_urls = {item.get("sourceUrl") for item in existing if isinstance(item, dict)}
    articles = fetch_gdelt_military_exercises()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    added = 0
    for art in articles:
        url = art.get("url", "").strip()
        title = art.get("title", "").strip()
        if not url or not title or url in known_urls:
            continue
        domain, domain_label, drills = infer_domain_and_drills(title)
        source_country = art.get("sourcecountry", "Quốc tế")
        seendate = art.get("seendate", "2026")[:8]
        formatted_date = (
            f"{seendate[6:8]}/{seendate[4:6]}/{seendate[0:4]}"
            if len(seendate) == 8 and seendate.isdigit()
            else now_str
        )
        record = {
            "id": "osint-" + re.sub(r"[^a-zA-Z0-9]", "", seendate + title[:12]).lower(),
            "name": title[:85],
            "dates": f"Ghi nhận: {formatted_date}",
            "status": "Đang diễn ra",
            "location": source_country or "Khu vực tác chiến liên hợp",
            "region": "Ấn Độ Dương - Thái Bình Dương" if any(k in title.lower() for k in ["pacific", "asia", "china", "japan", "india", "korea", "philippines"]) else "Châu Âu & Bắc Đại Tây Dương",
            "domain": domain,
            "domainLabel": domain_label,
            "purpose": f"Bản tin cập nhật tự động từ nguồn mở quốc tế: {title}",
            "drills": drills,
            "forces": "Lực lượng vũ trang các quốc gia tham gia theo thông cáo báo chí",
            "troops": 1500,
            "nationsCount": 2,
            "sourceTitle": art.get("domain", "OSINT Defense Feed"),
            "sourceUrl": url,
            "updatedAt": now_str
        }
        existing.insert(0, record)
        known_urls.add(url)
        added += 1
        if added >= 5:
            break

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing[:50], f, ensure_ascii=False, indent=2)
    print(f"[OK] Updated {DATA_FILE} with {added} new records (total: {len(existing[:50])}).")

if __name__ == "__main__":
    main()
