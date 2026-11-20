#!/usr/bin/env python3
import json, os, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
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
VI_RE = re.compile(r"[ăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹ]", re.I)
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def is_vi(text):
    return bool(text) and not CJK_RE.search(text) and bool(VI_RE.search(text))

def detect_lang(text, hint="auto"):
    if hint and hint not in ("auto", "global"):
        return "zh-CN" if hint.startswith("zh") else hint
    if re.search(r"[\u3040-\u30ff]", text): return "ja"
    if re.search(r"[\uac00-\ud7af]", text): return "ko"
    if re.search(r"[\u4e00-\u9fff]", text): return "zh-CN"
    return "en"

def to_vi(text, lang="auto"):
    if not text or lang == "vi" or is_vi(text):
        return text
    sl = detect_lang(text, lang)
    time.sleep(0.35)
    try:
        u = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={urllib.parse.quote(sl)}&tl=vi&dt=t&q={urllib.parse.quote(text)}"
        d = json.loads(http_get(u, 10))
        out = "".join(p[0] for p in d[0] if p and p[0]).strip()
        if out and out.lower() != text.lower():
            return out
    except Exception as e:
        print(f"[WARN] Google fail: {e}")
    try:
        u = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text[:450])}&langpair={urllib.parse.quote(sl + '|vi')}"
        d = json.loads(http_get(u, 12))
        out = ((d.get("responseData") or {}).get("translatedText") or "").strip()
        if out and out.lower() != text.lower() and "MYMEMORY WARNING" not in out.upper():
            return out
    except Exception as e:
        print(f"[WARN] MyMemory fail: {e}")
    try:
        lg = "zh" if sl.startswith("zh") else sl
        d = json.loads(http_get(f"https://lingva.ml/api/v1/{lg}/vi/{urllib.parse.quote(text[:400])}", 10))
        out = (d.get("translation") or "").strip()
        if out and out.lower() != text.lower():
            return out
    except Exception as e:
        print(f"[WARN] Lingva fail: {e}")
    return text

def parse_dt(item):
    for k in ("publishedAtIso", "collectedAtIso"):
        if item.get(k):
            try: return datetime.fromisoformat(item[k].replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception: pass
    for f in (item.get("updatedAt", ""), item.get("dates", "")):
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", str(f))
        if m:
            try: return datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4] or 12), int(m[5] or 0), tzinfo=timezone.utc)
            except Exception: pass
    return None

def fetch_rss():
    res = []
    for hl, gl, q in RSS_QUERIES:
        u = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
        try:
            root = ET.fromstring(http_get(u, 12))
            for it in root.findall(".//item")[:5]:
                t = (it.findtext("title") or "").strip()
                l = (it.findtext("link") or "").strip()
                p = (it.findtext("pubDate") or "").strip()
                s = it.find("source")
                sn = s.text.strip() if s is not None and s.text else "Google News"
                if t and l:
                    res.append({"title": t, "url": l, "pubDate": p, "source": sn, "lang": hl})
        except Exception as e:
            print(f"[WARN] RSS ({hl}): {e}")
    return res

def infer(title, lang):
    t = title.lower()
    if any(k in t for k in ["naval", "sea", "maritime", "submarine", "hải quân", "biển", "海上", "해군"]):
        d, dl, dr = "Hải quân", "Hải quân & Chống ngầm", ["Tác chiến biên đội mặt nước và chống ngầm (ASW)", "Bảo đảm an ninh hàng hải và bắn đạn thật"]
    elif any(k in t for k in ["air defense", "missile", "drone", "uas", "phòng không", "không quân", "防空", "공군"]):
        d, dl, dr = "Phòng không", "Phòng không & Chống UAV", ["Phòng không - phòng thủ tên lửa tích hợp (IAMD)", "Phát hiện và chế áp UAV (Counter-UAS)"]
    elif any(k in t for k in ["cyber", "mạng", "サイバー", "사이버"]):
        d, dl, dr = "Tác chiến mạng", "Tác chiến mạng (Cyber)", ["Bảo vệ hạ tầng chỉ huy và ứng phó tấn công mạng"]
    else:
        d, dl, dr = "Đa miền", "Tác chiến Đa miền (OSINT)", ["Hiệp đồng chỉ huy tham mưu liên quân", "Thực binh bắn đạn thật và bảo đảm hậu cần"]
    reg = "Việt Nam & Đông Nam Á" if (lang == "vi" or any(k in t for k in ["việt nam", "quân khu", "biển đông"])) else ("Châu Âu & Bắc Đại Tây Dương" if any(k in t for k in ["nato", "europe", "baltic", "poland", "ukraine", "arctic"]) else "Ấn Độ Dương - Thái Bình Dương")
    return d, dl, dr, reg
def main():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    now = datetime.now(timezone.utc)
    now_str, now_iso = now.strftime("%d/%m/%Y %H:%M UTC"), now.isoformat()
    existing = []
    if os.path.exists(DATA_FILE):
        try:
            loaded = json.load(open(DATA_FILE, encoding="utf-8"))
            if isinstance(loaded, list): existing = loaded
        except Exception: pass
    fresh = []
    for item in existing:
        if not isinstance(item, dict): continue
        dt = parse_dt(item)
        if dt and (now - dt) <= timedelta(days=MAX_AGE_DAYS):
            if item.get("name") and not is_vi(item["name"]):
                vn = to_vi(item["name"], "auto")
                if vn != item["name"]:
                    item["name"] = vn[:120]
                    item["purpose"] = f"Tin tức tự động dịch & cập nhật ({item.get('sourceTitle', 'OSINT')}): {vn}"
                    if isinstance(item.get("articles"), list) and item["articles"]:
                        item["articles"][0]["title"] = vn
            fresh.append(item)
    urls = {i.get("sourceUrl") for i in fresh}
    titles = {i.get("name", "").lower() for i in fresh}
    added = 0
    for art in fetch_rss():
        if art["url"] in urls: continue
        try:
            pub_dt = parsedate_to_datetime(art["pubDate"])
            pub_dt = pub_dt.astimezone(timezone.utc) if pub_dt.tzinfo else pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = now
        if (now - pub_dt) > timedelta(days=MAX_AGE_DAYS): continue
        vn = to_vi(art["title"], art["lang"])
        if vn.lower() in titles: continue
        d, dl, dr, reg = infer(art["title"] + " " + vn, art["lang"])
        slug = re.sub(r"[^a-zA-Z0-9]", "", art["title"][:20]).lower() or str(added)
        fresh.insert(0, {
            "id": f"osint-{now.strftime('%Y%m%d%H')}-{slug}",
            "name": vn[:120],
            "dates": f"Ghi nhận: {pub_dt.strftime('%d/%m/%Y')}",
            "status": "Đang diễn ra",
            "location": art["source"],
            "region": reg,
            "domain": d,
            "domainLabel": dl,
            "purpose": f"Tin tức tự động dịch & cập nhật ({art['source']}): {vn}",
            "drills": dr,
            "forces": "Lực lượng vũ trang tham gia theo thông cáo báo chí",
            "troops": 1500,
            "nationsCount": 2,
            "sourceTitle": art["source"],
            "sourceUrl": art["url"],
            "articles": [{"title": vn, "url": art["url"], "publisher": art["source"]}],
            "updatedAt": now_str,
            "collectedAtIso": now_iso,
            "publishedAtIso": pub_dt.isoformat(),
        })
        urls.add(art["url"]); titles.add(vn.lower()); added += 1
        if added >= 10: break
    fresh.sort(key=lambda i: parse_dt(i) or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(fresh[:60], f, ensure_ascii=False, indent=2)
    print(f"[OK] added={added}, total={len(fresh[:60])}")

if __name__ == "__main__":
    main()
