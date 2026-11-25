#!/usr/bin/env python3
import json, os, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "exercises.json")
SOURCES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "sources.json")
MAX_AGE_DAYS = 3
RSS_QUERIES = [
    ("en", "US", '"military exercise" OR "military drill" OR "joint naval drill" OR "live-fire drill" OR "wargames" when:3d'),
    ("vi", "VN", '"diễn tập quân sự" OR "diễn tập bắn đạn thật" OR "diễn tập khu vực phòng thủ" when:3d'),
    ("ru", "RU", '"военное учение" OR "военные учения" OR "совместные учения" OR "военно-морские учения" when:3d'),
    ("zh-CN", "CN", "联合军演 OR 军事演习 OR 实弹演习 when:3d"),
    ("ja", "JP", "共同訓練 OR 軍事演習 自衛隊 when:3d"),
    ("ko", "KR", "연합훈련 OR 군사훈련 국방부 when:3d"),
]
VI_RE = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ]", re.I)
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
CYR_RE = re.compile(r"[\u0400-\u04ff]")

VENUES = [
    ("Eo biển Luzon", r"\bluzon strait\b|eo biển luzon|吕宋海峡"),
    ("Biển Đông", r"\bsouth china sea\b|\bwest philippine sea\b|biển đông|南海|южно-китайск"),
    ("Eo biển Đài Loan", r"\btaiwan strait\b|eo biển đài loan|台湾海峡|тайваньск\w*\s+пролив"),
    ("Biển Hoa Đông", r"\beast china sea\b|biển hoa đông|东海|東シナ海|восточно-китайск"),
    ("Biển Nhật Bản", r"\bsea of japan\b|\beast sea\b|biển nhật bản|日本海|동해|японск\w*\s+мор"),
    ("Biển Hoàng Hải", r"\byellow sea\b|hoàng hải|黄海|서해|желт\w*\s+мор"),
    ("Biển Philippines", r"\bphilippine sea\b|biển philippines|フィリピン海"),
    ("Biển Baltic", r"\bbaltic sea\b|\bbaltic\b|biển baltic|балтийск"),
    ("Biển Đen", r"\bblack sea\b|biển đen|черн\w*\s+мор"),
    ("Biển Đỏ", r"\bred sea\b|biển đỏ|красн\w*\s+мор"),
    ("Biển Bắc", r"\bnorth sea\b|biển bắc|северн\w*\s+мор"),
    ("Địa Trung Hải", r"\bmediterranean\b|địa trung hải|средиземн"),
    ("Vịnh Ba Tư", r"\bpersian gulf\b|\barabian gulf\b|vịnh ba tư|персидск\w*\s+залив"),
    ("Eo biển Hormuz", r"\bstrait of hormuz\b|\bhormuz\b|eo biển hormuz"),
    ("Eo biển Malacca", r"\bstrait of malacca\b|\bmalacca\b|eo biển malacca"),
    ("Bán đảo Triều Tiên", r"\bkorean peninsula\b|bán đảo triều tiên|한반도|朝鮮半島|корейск\w*\s+полуостров"),
    ("Okinawa", r"\bokinawa\b|沖縄"),
    ("Kyushu", r"\bkyushu\b|九州"),
    ("Hokkaido", r"\bhokkaido\b|北海道"),
    ("Guam", r"\bguam\b|グアム"),
    ("Hawaii", r"\bhawaii\b"),
    ("Alaska", r"\balaska\b"),
    ("Bắc Cực", r"\barctic\b|bắc cực|арктик"),
    ("Ấn Độ Dương", r"\bindian ocean\b|ấn độ dương|индийск\w*\s+океан"),
    ("Thái Bình Dương", r"\bpacific ocean\b|\bindo-pacific\b|\bwestern pacific\b|thái bình dương|太平洋|тихоокеан"),
    ("Vịnh Bengal", r"\bbay of bengal\b|vịnh bengal"),
    ("Biển Ả Rập", r"\barabian sea\b|biển ả rập"),
    ("Batanes", r"\bbatanes\b"),
    ("Palawan", r"\bpalawan\b"),
    ("Subic", r"\bsubic\b"),
]

COUNTRIES = [
    ("Philippines", r"\bphilippines?\b|\bphilippine\b|\bmanila\b|菲律宾|フィリピン|필리핀|филиппин"),
    ("Việt Nam", r"\bvietnam\b|\bvietnamese\b|việt nam|quân khu\s*\d|越南|ベトナム|베트남|вьетнам"),
    ("Mỹ", r"\bunited states\b|\bu\.s\.a?\b|\bu\.s\.\b|\bus navy\b|\bus army\b|\bus marine|\bus air force\b|\busaf\b|\busmc\b|\bamerican\b|\bpentagon\b|\bmỹ\b|\bhoa kỳ\b|美国|米国|米軍|미국|미군|\bсша\b"),
    ("Trung Quốc", r"\bchina\b|\bchinese\b|\bpla\b|\bplan\b|trung quốc|中国|解放军|중국|кита[йяюе]"),
    ("Nhật Bản", r"\bjapan\b|\bjapanese\b|\bjsdf\b|\bjmsdf\b|\bjasdf\b|nhật bản|日本|自衛隊|일본|자위대|япони"),
    ("Hàn Quốc", r"\bsouth korea\b|\brok\b|hàn quốc|韩国|韓国|한국|국방부|южн\w*\s+коре"),
    ("Triều Tiên", r"\bnorth korea\b|\bdprk\b|triều tiên|朝鲜|北朝鮮|북한|кндр|северн\w*\s+коре"),
    ("Đài Loan", r"\btaiwan\b|\btaiwanese\b|đài loan|台湾|대만|тайван"),
    ("Úc", r"\baustralia\b|\baustralian\b|\badf\b|\búc\b|澳大利亚|オーストラリア|호주|австрали"),
    ("Ấn Độ", r"\bindia\b|\bindian\b|ấn độ|印度|インド|인도|инди[ияю]"),
    ("Nga", r"\brussia\b|\brussian\b|\bnga\b|俄罗斯|ロシア|러시아|росси|рф\b"),
    ("Belarus", r"\bbelarus\b|\bbelarusian\b|беларус|белорусс"),
    ("Ukraine", r"\bukraine\b|\bukrainian\b|ukraina|украин"),
    ("Anh", r"\bunited kingdom\b|\bbritain\b|\bbritish\b|\broyal navy\b|\braf\b|\b(?:quân đội|hải quân|không quân|tàu chiến|nước)\s+anh\b|英国|영국|великобритан"),
    ("Pháp", r"\bfrance\b|\bfrench\b|\bpháp\b|法国|フランス|프랑스|франци"),
    ("Đức", r"\bgermany\b|\bgerman\b|\bbundeswehr\b|\bđức\b|德国|ドイツ|독일|германи"),
    ("Ba Lan", r"\bpoland\b|\bpolish\b|ba lan|波兰|폴란드|польш"),
    ("Ý", r"\bitaly\b|\bitalian\b|\b(?:hải quân|quân đội|nước)\s+ý\b|意大利|イタリア|итали"),
    ("Canada", r"\bcanada\b|\bcanadian\b|加拿大|カナダ|캐나다|канад"),
    ("Na Uy", r"\bnorway\b|\bnorwegian\b|na uy|норвеги"),
    ("Thụy Điển", r"\bsweden\b|\bswedish\b|thụy điển|швеци"),
    ("Phần Lan", r"\bfinland\b|\bfinnish\b|phần lan|финлянди"),
    ("Đan Mạch", r"\bdenmark\b|\bdanish\b|đan mạch|дани[ия]"),
    ("Hà Lan", r"\bnetherlands\b|\bdutch\b|hà lan|нидерланд"),
    ("Thổ Nhĩ Kỳ", r"\bturkey\b|\btürkiye\b|\bturkish\b|thổ nhĩ kỳ|турци"),
    ("Hy Lạp", r"\bgreece\b|\bgreek\b|hy lạp|греци"),
    ("Romania", r"\bromania\b|\bromanian\b|румыни"),
    ("Estonia", r"\bestonia\b|\bestonian\b|эстони"),
    ("Latvia", r"\blatvia\b|\blatvian\b|латви"),
    ("Lithuania", r"\blithuania\b|\blithuanian\b|литв"),
    ("Thái Lan", r"\bthailand\b|\bthai\b|thái lan|泰国|タイ|태국|таиланд"),
    ("Indonesia", r"\bindonesia\b|\bindonesian\b|印度尼西亚|インドネシア|индонези"),
    ("Malaysia", r"\bmalaysia\b|\bmalaysian\b|马来西亚|マレーシア|малайзи"),
    ("Singapore", r"\bsingapore\b|\bsingaporean\b|新加坡|シンガポール|сингапур"),
    ("Iran", r"\biran\b|\biranian\b|伊朗|イラン|이란|иран"),
    ("Israel", r"\bisrael\b|\bisraeli\b|\bidf\b|以色列|イスラエル|이스라엘|израил"),
    ("Pakistan", r"\bpakistan\b|\bpakistani\b|пакистан"),
    ("New Zealand", r"\bnew zealand\b"),
    ("Ả Rập Xê Út", r"\bsaudi arabia\b|\bsaudi\b|ả rập xê út"),
    ("Ai Cập", r"\begypt\b|\begyptian\b|ai cập|егип"),
]

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def is_vi(text):
    return bool(text) and not CJK_RE.search(text) and not CYR_RE.search(text) and bool(VI_RE.search(text))

def detect_lang(text, hint="auto"):
    if hint and hint not in ("auto", "global"):
        return "zh-CN" if hint.startswith("zh") else hint
    if re.search(r"[\u3040-\u30ff]", text): return "ja"
    if re.search(r"[\uac00-\ud7af]", text): return "ko"
    if re.search(r"[\u4e00-\u9fff]", text): return "zh-CN"
    if CYR_RE.search(text): return "ru"
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

def clean_headline(text, source=""):
    t = (text or "").strip()
    if source:
        t = re.sub(r"\s*[-–|]\s*" + re.escape(source.strip()) + r"\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+[-–|]\s+[A-Z0-9][A-Za-z0-9\s.&']{1,35}$", "", t)
    return t.strip()

def extract_troops(text):
    if not text:
        return 0
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:vạn|万)\s*(?:quân|binh|lính|người|士兵|兵力|人)", text, re.I)
    if m:
        try: return int(float(m.group(1).replace(",", ".")) * 10000)
        except Exception: pass
    m = re.search(r"(\d{1,3}(?:[.,\s]\d{3})+|\d{3,6})\s*(?:\+?\s*)?(?:troops|soldiers|personnel|sailors|marines|airmen|service\s*members|quân\s*nhân|quân|binh\s*sĩ|chiến\s*sĩ|lính|военнослужащ\w*|солдат|человек|名士兵|人|명)", text, re.I)
    if m:
        digits = re.sub(r"[.,\s]", "", m.group(1))
        try:
            val = int(digits)
            if 20 <= val <= 500000:
                return val
        except Exception:
            pass
    return 0

def extract_location_and_nations(text_orig, text_vi, reg, source=""):
    combined = f"{clean_headline(text_orig, source)} {clean_headline(text_vi, source)}"
    venues = []
    country_text = combined
    for name, pat in VENUES:
        if re.search(pat, combined, re.I):
            venues.append(name)
            country_text = re.sub(pat, " ", country_text, flags=re.I)
    countries = [name for name, pat in COUNTRIES if re.search(pat, country_text, re.I)]
    venues = list(dict.fromkeys(venues))
    countries = list(dict.fromkeys(countries))
    if venues and countries:
        extra = [c for c in countries if c.lower() not in venues[0].lower()]
        loc = f"{', '.join(venues[:2])} ({', '.join(extra[:3])})" if extra else ", ".join(venues[:2])
    elif venues:
        loc = ", ".join(venues[:2])
    elif countries:
        loc = ", ".join(countries[:3])
    else:
        loc = f"Khu vực {reg}"
    m_nat = re.search(r"\b(\d{1,2})\s*(?:nations?|countries|allies|quốc gia|nước|стран|государств|国|개국)\b", combined, re.I)
    if m_nat and 1 <= int(m_nat.group(1)) <= 50:
        nations_count = int(m_nat.group(1))
    elif countries:
        nations_count = len(countries)
    elif re.search(r"\btrilateral\b|ba bên|3 nước|3 quốc gia|трехсторонн|三国|삼국", combined, re.I):
        nations_count = 3
    elif re.search(r"\bbilateral\b|song phương|hai nước|2 nước|двусторонн|两国", combined, re.I):
        nations_count = 2
    else:
        nations_count = 0
    return loc, nations_count

def load_dynamic_source_queries():
    if not os.path.exists(SOURCES_FILE):
        return []
    try:
        with open(SOURCES_FILE, encoding="utf-8") as f:
            sources = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {SOURCES_FILE}: {e}")
        return []
    if not isinstance(sources, list):
        return []
    domains = []
    seen = set()
    for src in sources:
        if not isinstance(src, dict) or not src.get("enabled"):
            continue
        url = (src.get("url") or "").strip()
        if not url:
            continue
        host = urllib.parse.urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or host == "api.gdeltproject.org" or host in seen:
            continue
        seen.add(host)
        domains.append(host)
    queries = []
    for i in range(0, len(domains), 7):
        chunk = domains[i:i + 7]
        site_expr = " OR ".join(f"site:{d}" for d in chunk)
        q = f'({site_expr}) (exercise OR drill OR "diễn tập" OR 演习 OR 訓練 OR 훈련 OR учение OR учения) when:3d'
        queries.append(("en", "US", q))
    return queries

def fetch_rss():
    res = []
    for hl, gl, q in RSS_QUERIES + load_dynamic_source_queries():
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
    if os.path.exists(SOURCES_FILE):
        try:
            with open(SOURCES_FILE, encoding="utf-8") as f:
                sources = json.load(f)
            if isinstance(sources, list):
                for src in sources:
                    if not isinstance(src, dict) or not src.get("enabled"):
                        continue
                    url = (src.get("url") or "").strip()
                    low = url.lower()
                    if not url or not any(tok in low for tok in ("/rss", "/feed", ".xml", ".atom")):
                        continue
                    name = (src.get("name") or urllib.parse.urlparse(url).netloc or "RSS").strip()
                    try:
                        root = ET.fromstring(http_get(url, 12))
                        items = root.findall(".//item")[:5]
                        if items:
                            for it in items:
                                t = (it.findtext("title") or "").strip()
                                l = (it.findtext("link") or "").strip()
                                p = (it.findtext("pubDate") or "").strip()
                                if t and l:
                                    res.append({"title": t, "url": l, "pubDate": p, "source": name, "lang": "auto"})
                        else:
                            for it in root.findall(".//{http://www.w3.org/2005/Atom}entry")[:5]:
                                t = (it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                                l_el = it.find("{http://www.w3.org/2005/Atom}link")
                                l = ((l_el.attrib.get("href") if l_el is not None else "") or "").strip()
                                p = (it.findtext("{http://www.w3.org/2005/Atom}updated") or it.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
                                if t and l:
                                    res.append({"title": t, "url": l, "pubDate": p, "source": name, "lang": "auto"})
                    except Exception as e:
                        print(f"[WARN] Direct RSS ({name}): {e}")
        except Exception as e:
            print(f"[WARN] Direct RSS sources load: {e}")
            return res

def fetch_gdelt():
    res = []
    q = '("military exercise" OR "military drill" OR "naval drill")'
    u = f"https://api.gdeltproject.org/api/v2/doc/doc?query={urllib.parse.quote(q)}&mode=ArtList&maxrecords=8&timespan=3d&format=json"
    try:
        data = json.loads(http_get(u, 12))
        for art in (data.get("articles") or [])[:6]:
            t = (art.get("title") or "").strip()
            l = (art.get("url") or "").strip()
            sn = (art.get("domain") or "GDELT").strip()
            sd = (art.get("seendate") or "").strip()
            pub_dt = None
            if len(sd) >= 15:
                try: pub_dt = datetime.strptime(sd[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                except Exception: pass
            if t and l:
                res.append({"title": t, "url": l, "pubDate": pub_dt.isoformat() if pub_dt else "", "source": sn, "lang": "auto"})
    except Exception as e:
        print(f"[WARN] GDELT: {e}")
    return res

def infer(title, lang):
    t = title.lower()
    if any(k in t for k in ["naval", "sea", "maritime", "submarine", "hải quân", "biển", "海上", "해군", "вмф", "флот", "морск"]):
        d, dl, dr = "Hải quân", "Hải quân & Chống ngầm", ["Tác chiến biên đội mặt nước và chống ngầm (ASW)", "Bảo đảm an ninh hàng hải và bắn đạn thật"]
    elif any(k in t for k in ["air defense", "missile", "drone", "uas", "phòng không", "không quân", "防空", "공군", "пво", "вкс", "ракет", "бпла"]):
        d, dl, dr = "Phòng không", "Phòng không & Chống UAV", ["Phòng không - phòng thủ tên lửa tích hợp (IAMD)", "Phát hiện và chế áp UAV (Counter-UAS)"]
    elif any(k in t for k in ["cyber", "mạng", "サイバー", "사이버", "кибер"]):
        d, dl, dr = "Tác chiến mạng", "Tác chiến mạng (Cyber)", ["Bảo vệ hạ tầng chỉ huy và ứng phó tấn công mạng"]
    else:
        d, dl, dr = "Đa miền", "Tác chiến Đa miền (OSINT)", ["Hiệp đồng chỉ huy tham mưu liên quân", "Thực binh bắn đạn thật và bảo đảm hậu cần"]
    reg = "Việt Nam & Đông Nam Á" if (lang == "vi" or any(k in t for k in ["việt nam", "quân khu", "biển đông"])) else ("Châu Âu & Bắc Đại Tây Dương" if (lang == "ru" or any(k in t for k in ["nato", "нато", "europe", "baltic", "балтийск", "poland", "ukraine", "arctic", "арктик", "росси", "черн"])) else "Ấn Độ Dương - Thái Bình Dương")
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
            if str(item.get("id", "")).startswith("osint-"):
                src = item.get("sourceTitle", "")
                reg = item.get("region", "Ấn Độ Dương - Thái Bình Dương")
                loc, n_cnt = extract_location_and_nations(item.get("name", ""), item.get("purpose", ""), reg, src)
                tr = extract_troops(f"{item.get('name', '')} {item.get('purpose', '')}")
                if not item.get("location") or item.get("location") == src or "news" in str(item.get("location", "")).lower():
                    item["location"] = loc
                if item.get("troops") == 1500 and tr == 0:
                    item["troops"] = 0
                elif tr > 0:
                    item["troops"] = tr
                if item.get("nationsCount") == 2 or not item.get("nationsCount"):
                    item["nationsCount"] = n_cnt
            fresh.append(item)
    urls = {i.get("sourceUrl") for i in fresh}
    titles = {i.get("name", "").lower() for i in fresh}
    added = 0
    for art in fetch_rss() + fetch_gdelt():
        if art["url"] in urls: continue
        try:
            if "T" in art["pubDate"] and "+" in art["pubDate"]:
                pub_dt = datetime.fromisoformat(art["pubDate"]).astimezone(timezone.utc)
            else:
                pub_dt = parsedate_to_datetime(art["pubDate"])
                pub_dt = pub_dt.astimezone(timezone.utc) if pub_dt.tzinfo else pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = now
        if (now - pub_dt) > timedelta(days=MAX_AGE_DAYS): continue
        vn = to_vi(art["title"], art["lang"])
        if vn.lower() in titles: continue
        d, dl, dr, reg = infer(art["title"] + " " + vn, art["lang"])
        loc, n_cnt = extract_location_and_nations(art["title"], vn, reg, art["source"])
        tr = extract_troops(f"{art['title']} {vn}")
        slug = re.sub(r"[^a-zA-Z0-9]", "", art["title"][:20]).lower() or str(added)
        fresh.insert(0, {
            "id": f"osint-{now.strftime('%Y%m%d%H')}-{slug}",
            "name": vn[:120],
            "dates": f"Ghi nhận: {pub_dt.strftime('%d/%m/%Y')}",
            "status": "Đang diễn ra",
            "location": loc,
            "region": reg,
            "domain": d,
            "domainLabel": dl,
            "purpose": f"Tin tức tự động dịch & cập nhật ({art['source']}): {vn}",
            "drills": dr,
            "forces": "Lực lượng vũ trang tham gia theo thông cáo báo chí",
            "troops": tr,
            "nationsCount": n_cnt,
            "sourceTitle": art["source"],
            "sourceUrl": art["url"],
            "articles": [{"title": vn, "url": art["url"], "publisher": art["source"]}],
            "updatedAt": now_str,
            "collectedAtIso": now_iso,
            "publishedAtIso": pub_dt.isoformat(),
        })
        urls.add(art["url"]); titles.add(vn.lower()); added += 1
        if added >= 20: break
    fresh.sort(key=lambda i: parse_dt(i) or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(fresh[:80], f, ensure_ascii=False, indent=2)
    print(f"[OK] added={added}, total={len(fresh[:80])}")

if __name__ == "__main__":
    main()
