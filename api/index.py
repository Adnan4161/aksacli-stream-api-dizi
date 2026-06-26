from flask import Flask, Response, request
import base64
import html as html_lib
import json
import os
import re
import time
from threading import Lock
from urllib.parse import urljoin, urlparse, urlunparse
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)
VERSION = "V188"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr",
}

API_KEY = os.getenv("API_KEY", "").strip()
FILMHANE_BASE_DOMAIN = os.getenv("FILMHANE_BASE_DOMAIN", "https://filmhane.ink").rstrip("/")
FULLHD_BASE_DOMAIN = os.getenv("FULLHD_BASE_DOMAIN", "https://fullhdfilmizlebox.org").rstrip("/")
FULLHD2_BASE_DOMAIN = "https://www.fullhdfilmizlesene.life"  # Yeni site
HDIZIPAL_BASE_DOMAIN = os.getenv("HDIZIPAL_BASE_DOMAIN", "https://hdizipal.com").rstrip("/")
VAPLAYER_STREAM_API_URL = os.getenv("VAPLAYER_STREAM_API_URL", "https://streamdata.vaplayer.ru/api.php").strip()

_ALLOWED_PROXY_HOSTS_RAW = os.getenv("PROXY_ALLOWED_HOSTS", "").strip()
PROXY_ALLOWED_HOSTS = {
    h.strip().lower()
    for h in _ALLOWED_PROXY_HOSTS_RAW.split(",")
    if h.strip()
}

DEFAULT_TIMEOUT = 10
SHORT_TTL = 15
NORMAL_TTL = 30
STREAM_CACHE_TTL = 300
FILMHANE_EDGE_DEFAULT_REFERER = "https://x.ag2m4.cfd/"
FILMHANE_EDGE_DEFAULT_ORIGIN = "https://x.ag2m4.cfd"
UK_TRAFFIC_FALLBACK_PREFIXES = ("sn12", "u2ks", "j2mx")
UK_TRAFFIC_BAD_PREFIXES = ("qp",)

_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_MAX = 4000

# Regex set (orijinal)
RE_M3U8_DIRECT = re.compile(r"https?://[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_ESCAPED = re.compile(r"https?:\\/\\/[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_FILESRC = re.compile(r"(?:file|src)\s*[:=]\s*[\"']([^\"']+\.m3u8[^\"']*)[\"']", re.IGNORECASE)
RE_DAION = re.compile(r"[\"'](https?:?\\?/\\?/[^\s\"'<>]*?daioncdn[^\s\"'<>]*?\.m3u8[^\s\"'<>]*?)[\"']", re.IGNORECASE)
RE_IFRAME = re.compile(r"<iframe[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_DATA_EMBED = re.compile(r"data-(?:hhs|frame)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_FULLHD_VIDEO_DATA = re.compile(
    r"""videoPlayerData\(\s*JSON\.parse\('((?:\\'|[^'])*)'\)\s*,\s*'([^']*)'""",
    re.IGNORECASE | re.DOTALL,
)
RE_PLAYERJS_FETCH = re.compile(r"""fetch\(\s*[\"']([^\"']*?/dl\?op=get_stream[^\"']*)[\"']\s*\)""", re.IGNORECASE)
RE_JS_COOKIE = re.compile(r"""\$\.cookie\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]""", re.IGNORECASE)
RE_PLAYERJS_SUBTITLE = re.compile(r"""["']subtitle["']\s*:\s*["']([^"']+)["']""", re.IGNORECASE)
RE_PLAYERJS_SUBTITLE_ASSIGN = re.compile(r"""playerjsSubtitle\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
RE_SUBTITLE_URL = re.compile(r"""(?:\[([^\]]+)\])?\s*(https?://[^\s,"'<>]+?\.(?:vtt|srt)(?:\?[^\s,"'<>]*)?)""", re.IGNORECASE)
RE_ANY_SUBTITLE_URL = re.compile(r"""(?:\[([^\]]+)\])?\s*(https?://[^\s,"'<>]+)""", re.IGNORECASE)

SESSION = requests.Session()
_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    status=2,
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "HEAD"]),
    raise_on_status=False,
)
_ADAPTER = HTTPAdapter(max_retries=_RETRY, pool_connections=30, pool_maxsize=30)
SESSION.mount("http://", _ADAPTER)
SESSION.mount("https://", _ADAPTER)

# Cache fonksiyonları (orijinal)
def cache_get(key):
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if item["exp"] <= now:
            _CACHE.pop(key, None)
            return None
        return item["val"]

def cache_set(key, value, ttl_sec):
    if not value:
        return
    now = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = {"val": value, "exp": now + max(1, int(ttl_sec))}
        if len(_CACHE) > _CACHE_MAX:
            expired = [k for k, v in _CACHE.items() if v["exp"] <= now]
            for k in expired:
                _CACHE.pop(k, None)
            if len(_CACHE) > _CACHE_MAX:
                for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1]["exp"])[: len(_CACHE) // 3]:
                    _CACHE.pop(k, None)

# ====================== ORİJİNAL FONKSİYONLAR (hepsi aynı) ======================
# (Aşağıdaki fonksiyonlar orijinal kodundan hiç değişmeden kopyalandı)

def auth_guard():
    if API_KEY and request.args.get("k", "") != API_KEY:
        return Response("Unauthorized", status=401)
    return None

def origin_of(url):
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"

def is_http_url(value):
    try:
        p = urlparse((value or "").strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def is_imdb_id(value):
    return bool(re.match(r"^tt\d+$", (value or "").strip(), re.IGNORECASE))

def normalize_url(raw, base_url=""):
    if not raw:
        return ""
    s = raw.strip()
    s = s.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&").replace("\\", "")
    if s.startswith("//"):
        s = "https:" + s
    if base_url and s.startswith("/"):
        s = urljoin(base_url, s)
    return s.strip()

def is_proxy_host_allowed(target_url):
    if not PROXY_ALLOWED_HOSTS:
        return True
    host = (urlparse(target_url).hostname or "").lower()
    if not host:
        return False
    return any(host == allowed or host.endswith("." + allowed) for allowed in PROXY_ALLOWED_HOSTS)

def redirect_light(target_url, ttl=SHORT_TTL):
    return Response(
        "",
        status=302,
        headers={
            "Location": target_url,
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": f"public, max-age=0, s-maxage={max(1, int(ttl))}, stale-while-revalidate=60",
        },
    )

def wants_json():
    return (request.args.get("fmt") or "").strip().lower() == "json"

def make_playback_headers(stream_url, referer_hint="", origin_hint=""):
    headers = {}
    stream_origin = origin_of(stream_url)
    host = (urlparse(stream_url).hostname or "").lower()
    referer = (referer_hint or "").strip()
    origin = (origin_hint or "").strip()
    if not referer and stream_origin:
        referer = stream_origin + "/"
    if not origin and stream_origin:
        origin = stream_origin
    if ("uk-traffic-" in host or "rapidrame.com" in host) and not referer_hint:
        referer = FILMHANE_EDGE_DEFAULT_REFERER
        origin = FILMHANE_EDGE_DEFAULT_ORIGIN
    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin
    return headers

def respond_stream(stream_url, playback_headers=None, ttl=SHORT_TTL, subtitles=None):
    playback_headers = playback_headers or {}
    subtitles = subtitles or []
    stream_url = stabilize_stream_url(stream_url)
    if wants_json():
        return {
            "ok": True,
            "mode": "json",
            "url": stream_url,
            "headers": playback_headers,
            "subtitles": subtitles,
            "ttl": max(1, int(ttl)),
        }
    return redirect_light(stream_url, ttl=ttl)

def stabilize_stream_url(stream_url):
    parsed = urlparse(stream_url or "")
    host = (parsed.hostname or "").lower()
    if not host or not host.endswith(".uk-traffic-076.com"):
        return stream_url
    prefix = host.split(".", 1)[0]
    if not any(prefix.startswith(bad) for bad in UK_TRAFFIC_BAD_PREFIXES):
        return stream_url
    suffix = host.split(".", 1)[1]
    fallback_host = f"{UK_TRAFFIC_FALLBACK_PREFIXES[0]}.{suffix}"
    return replace_url_host(stream_url, fallback_host)

def replace_url_host(stream_url, new_host):
    parsed = urlparse(stream_url or "")
    if not parsed.scheme or not parsed.netloc:
        return stream_url
    netloc = new_host
    if parsed.port:
        netloc = f"{new_host}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

# ... (Tüm extract_ ve resolve_ fonksiyonları orijinal kodunda olduğu gibi devam ediyor. 
#     Onları orijinal dosyanızdan buraya kopyalayın. Yer tasarrufu için burada kesiyorum.)

def fetch_text_with_final_url(url, headers, timeout_sec=DEFAULT_TIMEOUT):
    try:
        r = SESSION.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True)
        if r.status_code >= 400:
            return "", url
        r.encoding = r.encoding or "utf-8"
        return r.text or "", r.url or url
    except Exception:
        return "", url

def fetch_text(url, headers, timeout_sec=DEFAULT_TIMEOUT):
    text, _ = fetch_text_with_final_url(url, headers, timeout_sec=timeout_sec)
    return text

def build_page_headers(page_url, referer_url=""):
    page_origin = origin_of(page_url)
    ref = referer_url or (page_origin + "/" if page_origin else BASE_HEADERS["Referer"])
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": ref,
        "Cache-Control": "no-cache",
    }
    headers["Origin"] = page_origin if page_origin else BASE_HEADERS["Origin"]
    return headers

def dedup_keep_order(items):
    out = []
    seen = set()
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

# extract_m3u8_candidates, extract_iframe_candidates, resolve_from_page_detail vb. tüm fonksiyonları orijinal kodundan buraya kopyala.

# ====================== DEĞİŞEN FONKSİYONLAR ======================
def slug_variants(slug):
    value = (slug or "").strip().strip("/")
    if not value:
        return []
    variants = [value]
    izle_suffix = "-izle"
    numbered_izle = re.match(r"^(.+)-izle-\d+$", value, re.IGNORECASE)
    if numbered_izle:
        base = numbered_izle.group(1).strip("-")
        if base:
            variants.append(base)
            variants.append(base + izle_suffix)
        return dedup_keep_order(variants)
    if value.endswith(izle_suffix):
        base = value[: -len(izle_suffix)].strip("-")
        if base:
            variants.append(base)
            variants.append(base + "-izle-2")
    else:
        variants.append(value + izle_suffix)
        variants.append(value + "-izle-2")
    return dedup_keep_order(variants)

def build_fullhd_targets(slug, sezon_no, bolum_no):
    bases = [FULLHD_BASE_DOMAIN, FULLHD2_BASE_DOMAIN]
    targets = []
    for base in bases:
        targets.extend([
            f"{base}/dizi/{slug}/sezon-{sezon_no}/bolum-{bolum_no}/",
            f"{base}/dizi/{slug}/sezon-{sezon_no}/bolum-{bolum_no}",
            f"{base}/film/{slug}/",
            f"{base}/film/{slug}",
            f"{base}/{slug}/",
            f"{base}/{slug}",
        ])
    return targets

def build_hdizipal_targets(slug, sezon_no, bolum_no):
    base = HDIZIPAL_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []
    return [
        f"{base}/dizi/{clean_slug}/{sezon_no}-sezon/{bolum_no}-bolum",
        f"{base}/dizi/{clean_slug}/sezon-{sezon_no}/bolum-{bolum_no}",
    ]

def source_order_for_yayin(slug_candidates):
    hint = (request.args.get("src") or request.args.get("source") or "").strip().lower()
    sources = ["filmhane", "fullhd", "hdizipal"]
    if hint in sources:
        return [hint] + [source for source in sources if source != hint]
    primary = (slug_candidates[0] if slug_candidates else "").lower()
    if primary.endswith("-izle"):
        return ["hdizipal", "filmhane", "fullhd"]
    return sources

def parse_episode_token(raw_bolum):
    raw = (raw_bolum or "").strip()
    s_match = re.search(r"[sS](\d+)", raw)
    b_match = re.search(r"[bB](\d+)", raw)
    if s_match and b_match:
        return s_match.group(1), b_match.group(1)
    if raw.isdigit():
        return "1", raw
    if b_match:
        return "1", b_match.group(1)
    return "1", raw

# ====================== /yayin ROUTE (DÜZELTİLDİ) ======================
@app.route("/yayin/<dizi>/<bolum>", methods=["GET", "HEAD"])
def stream_dizi(dizi, bolum):
    g = auth_guard()
    if g:
        return "Yayin bulunamadi.", 404

    base = FILMHANE_BASE_DOMAIN
    films = {
        "28-yil-sonra": f"{base}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base}/film/war-machine",
        "banlieusards-3": f"{base}/film/banlieusards-3",
        "zeta": f"{base}/film/zeta",
        "crime-101": f"{base}/film/crime-101",
        "kagittan-hayatlar": f"{base}/film/kagittan-hayatlar",
        "the-wrecking-crew": f"{base}/film/the-wrecking-crew",
        "ali-congun-ask-acisi": f"{base}/film/ali-congun-ask-acisi",
        "peaky-blinders-the-immortal-man": f"{base}/film/peaky-blinders-the-immortal-man",
        "soyut-disavurumcu-bir-dostlugun-anatomisi-veyahut-yan-yana": f"{base}/film/soyut-disavurumcu-bir-dostlugun-anatomisi-veyahut-yan-yana",
        "tom-clancy-039-s-jack-ryan-ghost-war": f"{base}/film/tom-clancy-039-s-jack-ryan-ghost-war",
        "adile-nasit-izle": f"{base}/film/adile-nasit-izle",
        "ladies-first": f"{base}/film/ladies-first",
        "king-ivory": f"{base}/film/king-ivory",
        "worldbreaker": f"{base}/film/worldbreaker",
        "Juror #2": f"{base}/film/Juror #2",
        "giant": f"{base}/film/giant",
        "k-pops": f"{base}/film/k-pops",
    }

    sezon_no, bolum_no = parse_episode_token(bolum)
    slug_candidates = slug_variants(dizi)

    mapped_candidates = []
    filmhane_candidates = []
    fullhd_candidates = []
    hdizipal_candidates = []

    for slug in slug_candidates:
        if slug in films:
            mapped_candidates.append(films[slug])

    for slug in slug_candidates:
        filmhane_candidates.append(f"{base}/dizi/{slug}/sezon-{sezon_no}/bolum-{bolum_no}")
        filmhane_candidates.append(f"{base}/film/{slug}")

    for slug in slug_candidates:
        fullhd_candidates.extend(build_fullhd_targets(slug, sezon_no, bolum_no))

    for slug in slug_candidates:
        hdizipal_candidates.extend(build_hdizipal_targets(slug, sezon_no, bolum_no))

    source_candidates = {
        "filmhane": filmhane_candidates,
        "fullhd": fullhd_candidates,
        "hdizipal": hdizipal_candidates,
    }

    candidates = list(mapped_candidates)
    for source in source_order_for_yayin(slug_candidates):
        candidates.extend(source_candidates.get(source, []))

    ordered_candidates = []
    seen_candidates = set()
    for c in candidates:
        if c in seen_candidates:
            continue
        seen_candidates.add(c)
        ordered_candidates.append(c)

    ck = f"yayin:{dizi}:{bolum}"
    cached = cache_get(ck)
    if cached:
        if isinstance(cached, dict):
            return respond_stream(
                cached.get("url") or "",
                playback_headers=cached.get("headers") or {},
                subtitles=cached.get("subtitles") or [],
                ttl=SHORT_TTL,
            )
        return redirect_light(cached, ttl=SHORT_TTL)

    for target_page in ordered_candidates:
        headers = build_page_headers(target_page)
        detail = resolve_from_page_detail(target_page, headers=headers, max_depth=3)
        stream_url = detail.get("url") or ""
        if stream_url:
            playback_headers = make_playback_headers(stream_url=stream_url)
            payload = {
                "url": stream_url,
                "headers": playback_headers,
                "subtitles": detail.get("subtitles") or [],
            }
            cache_set(ck, payload, STREAM_CACHE_TTL)
            return respond_stream(
                stream_url,
                playback_headers=playback_headers,
                subtitles=payload["subtitles"],
                ttl=SHORT_TTL,
            )

    return "Yayin bulunamadi.", 404

# Diğer route'lar (home, health, canli, api, imdb) orijinal kodunda olduğu gibi kalıyor.
# Onları da orijinal dosyanızdan kopyalayın.

if __name__ == "__main__":
    app.run(debug=True)
