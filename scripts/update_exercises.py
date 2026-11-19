#!/usr/bin/env python3
"""
Script tự động tìm kiếm, DỊCH SANG TIẾNG VIỆT và chỉ giữ lại tin diễn tập quân sự
thu thập được trong 3 NGÀY GẦN NHẤT (72 giờ).
Kết hợp đa nguồn: Google News RSS (Anh, Việt, Trung, Nhật, Hàn) + GDELT DOC 2.0 API.
Chạy định kỳ 2 giờ/lần qua GitHub Actions.
"""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "exercises.json")
MAX_AGE_DAYS = 3

RSS_QUERIES = [
    ("en", "US", "military exercise OR joint naval drill when:3d"),
    ("vi", "VN", "diễn tập quân sự when:3d"),
    ("zh-CN", "CN", "联合军演 OR 军事演习 when:3d"),
    ("ja", "JP", "共同訓練 自衛隊 when:3d"),
    ("ko", "KR", "연합훈련 국방부 when:3d"),
]

def http_get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MilExWatchBot/2.2; +https://github.com/dqt169/milex-watch-2026)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def translate_to_vietnamese(text: str, lang: str = "auto") -> str:
    if not text or lang == "vi":
        return text
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

def parse_item_datetime_utc(item: dict):
    iso_val = item.get("collectedAtIso")
    if iso_val:
        try:
            dt = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    for field in (item.get("updatedAt", ""), item.get("dates", "")):
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", str(field))
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hour = int(m.group(4)) if m.group(4) else 12
            minute = int(m.group(5)) if m.group(5) else 0
            try:
                return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def is_within_max_age(dt_utc, now_utc) -> bool:
    if dt_utc is None:
        return False
    return (now_utc - dt_utc) <= timedelta(days=MAX_AGE_DAYS)

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
            for item in root.findall(".//item")[:5]:
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
        + "&mode=artlist&maxrecords=10&timespan=3d&format=json"
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

def parse_article_pub_dt(raw_date: str, fallback_dt: datetime) -> datetime:
    if not raw_date:
        return fallback_dt
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        if len(raw_date) >= 8 and raw_date[:8].isdigit():
            try:
                return datetime(int(raw_date[0:4]), int(raw_date[4:6]), int(raw_date[6:8]), 12, 0, tzinfo=timezone.utc)
            except Exception:
                pass
    return fallback_dt

def main():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%d/%m/%Y %H:%M UTC")
    now_iso = now_utc.isoformat()

    existing = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    existing = loaded
        except Exception:
            existing = []

    # Prune old records (> 3 days) from existing data
    fresh_existing = []
    for item in existing:
        if not isinstance(item, dict):
            continue
        dt_utc = parse_item_datetime_utc(item)
        if is_within_max_age(dt_utc, now_utc):
            if item.get("name"):
                vi_name = translate_to_vietnamese(item["name"], "auto")
                if vi_name != item["name"]:
                    item["name"] = vi_name[:110]
                    item["purpose"] = f"Tin tức tự động dịch & cập nhật ({item.get('sourceTitle', 'OSINT')}): {vi_name}"
            fresh_existing.append(item)

    known_urls = {item.get("sourceUrl") for item in fresh_existing}
    known_titles = {item.get("name", "").lower() for item in fresh_existing}

    candidates = fetch_google_news_rss() + fetch_gdelt_articles()
    added = 0
    for art in candidates:
        url = art["url"]
        raw_title = art["title"]
        if url in known_urls:
            continue
        pub_dt = parse_article_pub_dt(art.get("pubDate", ""), now_utc)
        if not is_within_max_age(pub_dt, now_utc):
            continue
        vi_title = translate_to_vietnamese(raw_title, art["lang"])
        if vi_title.lower() in known_titles:
            continue
        domain, domain_label, drills, region = infer_metadata(raw_title + " " + vi_title, art["lang"])
        pub_str = pub_dt.strftime("%d/%m/%Y")
        slug = re.sub(r"[^a-zA-Z0-9]", "", raw_title[:20]).lower() or str(added)
        record = {
            "id": f"osint-{now_utc.strftime('%Y%m%d%H')}-{slug}",
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
            "collectedAtIso": now_iso,
        }
        fresh_existing.insert(0, record)
        known_urls.add(url)
        known_titles.add(vi_title.lower())
        added += 1
        if added >= 10:
            break

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(fresh_existing[:60], f, ensure_ascii=False, indent=2)
    print(f"[OK] Updated {DATA_FILE}: added {added}, kept {len(fresh_existing[:60])} records within last {MAX_AGE_DAYS} days.")

if __name__ == "__main__":
    main()
