#!/usr/bin/env python3
"""
Script tự động tìm kiếm, DỊCH SANG TIẾNG VIỆT và cập nhật thông tin diễn tập quân sự.
Kết hợp đa nguồn: Google News RSS (Anh, Việt, Trung, Nhật, Hàn) + GDELT DOC 2.0 API.
Chạy định kỳ 2 giờ/lần qua GitHub Actions.
"""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "exercises.json")

RSS_QUERIES = [
    ("en", "US", "military exercise OR joint naval drill 2026"),
    ("vi", "VN", "diễn tập quân sự 2026"),
    ("zh-CN", "CN", "联合军演 OR 军事演习"),
    ("ja", "JP", "共同訓練 自衛隊"),
    ("ko", "KR", "연합훈련 국방부"),
]

def http_get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MilExWatchBot/2.1; +https://github.com/dqt169/milex-watch-2026)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def translate_to_vietnamese(text: str, lang: str = "auto") -> str:
    if not text or lang == "vi":
        return text
    # Skip if already contains Vietnamese diacritics
    if re.search(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", text.lower()):
        return text
    try:
        sl = "zh-CN" if lang.startswith("zh") else ("ja" if lang == "ja" else ("ko" if lang == "ko" else "auto"))
        url = (
            "https://translate.googleapis.com/translate_a/single?client=gtx"
            f"&sl={urllib.parse.quote(sl)}&tl=vi&dt=t&q={urllib.parse.quote(text)}"
        )
        raw = http_get(url, timeout=10)
        data = json.loads(raw)
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return translated.strip() or text
    except Exception as e:
        print(f"[WARN] Translate fallback: {e}")
        return text

def fetch_google_news_rss():
    results = []
    for hl, gl, query in RSS_QUERIES:
        ceid = f"{gl}:{hl}"
        rss_url = (
            f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
            f"&hl={urllib.parse.quote(hl)}&gl={urllib.parse.quote(gl)}&ceid={urllib.parse.quote(ceid)}"
        )
        try:
            xml_text = http_get(rss_url, timeout=12)
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item")[:4]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source_name = source_el.text.strip() if source_el is not None and source_el.text else "Google News OSINT"
                if title and link:
                    results.append({
                        "title": title,
                        "url": link,
                        "pubDate": pub_date,
                        "source": source_name,
                        "lang": hl,
                    })
        except Exception as e:
            print(f"[WARN] RSS fetch error ({hl}): {e}")
    return results

def fetch_gdelt_articles():
    query = "military exercise OR joint exercise OR naval drill"
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?query="
        + urllib.parse.quote(query)
        + "&mode=artlist&maxrecords=10&timespan=1d&format=json"
    )
    try:
        raw = http_get(url, timeout=15)
        data = json.loads(raw)
        out = []
        for art in data.get("articles", []):
            title = (art.get("title") or "").strip()
            link = (art.get("url") or "").strip()
            if title and link:
                out.append({
                    "title": title,
                    "url": link,
                    "pubDate": art.get("seendate", ""),
                    "source": art.get("domain", "GDELT OSINT"),
                    "lang": "global",
                })
        return out
    except Exception as e:
        print(f"[WARN] GDELT fetch error: {e}")
        return []

def infer_metadata(title: str, lang: str):
    t = title.lower()
    if any(k in t for k in ["naval", "sea", "maritime", "submarine", "fleet", "hải quân", "biển", "海上", "海演", "해군"]):
        domain, domain_label = "Hải quân", "Hải quân & Chống ngầm"
        drills = [
            "Tác chiến hiệp đồng biên đội tàu mặt nước và chống ngầm (ASW)",
            "Bảo đảm an ninh hàng hải và bắn đạn thật trên biển",
        ]
    elif any(k in t for k in ["air defense", "missile", "drone", "uas", "fighter", "phòng không", "không quân", "空軍", "防空", "공군"]):
        domain, domain_label = "Phòng không", "Phòng không & Chống UAV"
        drills = [
            "Tác chiến phòng không - phòng thủ tên lửa tích hợp (IAMD)",
            "Phát hiện, chế áp thiết bị bay không người lái (Counter-UAS)",
        ]
    elif any(k in t for k in ["cyber", "mạng", "サイバー", "사이버"]):
        domain, domain_label = "Tác chiến mạng", "Tác chiến mạng (Cyber)"
        drills = ["Bảo vệ hạ tầng thông tin chỉ huy và ứng phó tấn công mạng"]
    else:
        domain, domain_label = "Đa miền", "Tác chiến Đa miền (OSINT)"
        drills = [
            "Hiệp đồng chỉ huy tham mưu và cơ động lực lượng liên quân",
            "Thực binh bắn đạn thật và bảo đảm hậu cần - kỹ thuật chiến dịch",
        ]

    if lang == "vi" or any(k in t for k in ["việt nam", "quân khu", "thái nguyên", "biển đông"]):
        region = "Việt Nam & Đông Nam Á"
    elif any(k in t for k in ["nato", "europe", "baltic", "poland", "lithuania", "ukraine", "black sea", "arctic", "germany", "uk ", "france"]):
        region = "Châu Âu & Bắc Đại Tây Dương"
    else:
        region = "Ấn Độ Dương - Thái Bình Dương"

    return domain, domain_label, drills, region

def format_pub_date(raw_date: str, fallback: str) -> str:
    if not raw_date:
        return fallback
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        if len(raw_date) >= 8 and raw_date[:8].isdigit():
            return f"{raw_date[6:8]}/{raw_date[4:6]}/{raw_date[0:4]}"
    return fallback

def main():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            existing = []

    # Translate any existing non-Vietnamese records already in data/exercises.json
    for item in existing:
        if isinstance(item, dict) and item.get("name"):
            vi_name = translate_to_vietnamese(item["name"], "auto")
            if vi_name != item["name"]:
                item["name"] = vi_name[:110]
                item["purpose"] = f"Tin tức tự động dịch & cập nhật ({item.get('sourceTitle', 'OSINT')}): {vi_name}"

    known_urls = {item.get("sourceUrl") for item in existing if isinstance(item, dict)}
    known_titles = {item.get("name", "").lower() for item in existing if isinstance(item, dict)}

    candidates = fetch_google_news_rss() + fetch_gdelt_articles()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    today_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    added = 0
    for art in candidates:
        url = art["url"]
        raw_title = art["title"]
        if url in known_urls:
            continue
        vi_title = translate_to_vietnamese(raw_title, art["lang"])
        if vi_title.lower() in known_titles:
            continue
        domain, domain_label, drills, region = infer_metadata(raw_title + " " + vi_title, art["lang"])
        pub_str = format_pub_date(art.get("pubDate", ""), today_str)
        slug = re.sub(r"[^a-zA-Z0-9]", "", raw_title[:20]).lower() or str(added)
        record = {
            "id": f"osint-{datetime.now(timezone.utc).strftime('%Y%m%d%H')}-{slug}",
            "name": vi_title[:110],
            "dates": f"Ghi nhận: {pub_str}",
            "status": "Đang diễn ra",
            "location": art["source"],
            "region": region,
            "domain": domain,
            "domainLabel": domain_label,
            "purpose": f"Tin tức tự động dịch & cập nhật ({art['source']}): {vi_title}",
            "drills": drills,
            "forces": "Lực lượng vũ trang tham gia theo thông cáo báo chí",
            "troops": 1500,
            "nationsCount": 2,
            "sourceTitle": art["source"],
            "sourceUrl": url,
            "articles": [{"title": vi_title, "url": url, "publisher": art["source"]}],
            "updatedAt": now_str,
        }
        existing.insert(0, record)
        known_urls.add(url)
        known_titles.add(vi_title.lower())
        added += 1
        if added >= 8:
            break

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing[:60], f, ensure_ascii=False, indent=2)
    print(f"[OK] Updated {DATA_FILE} with {added} new Vietnamese-translated records (total: {len(existing[:60])}).")

if __name__ == "__main__":
    main()
