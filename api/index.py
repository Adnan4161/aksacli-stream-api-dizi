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
FULLHD2_BASE_DOMAIN = "https://www.fullhdfilmizlesene.life"  # Yeni eklenen site
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

# In-memory cache
_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_MAX = 4000

# Regex set
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

# HTTP Session
SESSION = requests.Session()
_RETRY = Retry(
    total=2, connect=2, read=2, status=2,
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "HEAD"]),
    raise_on_status=False,
)
_ADAPTER = HTTPAdapter(max_retries=_RETRY, pool_connections=30, pool_maxsize=30)
SESSION.mount("http://", _ADAPTER)
SESSION.mount("https://", _ADAPTER)

# ====================== CACHE ======================
def cache_get(key):
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item or item["exp"] <= now:
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
            # basit temizlik
            expired = [k for k, v in _CACHE.items() if v["exp"] <= now]
            for k in expired:
                _CACHE.pop(k, None)

# ====================== YARDIMCI FONKSİYONLAR ======================
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

# ====================== SCRAPING FONKSİYONLARI ======================
# (extract_m3u8_candidates, resolve_from_page_detail, resolve_playerjs_embed_detail vb. tüm fonksiyonlar aynı kalıyor)
# Kod uzunluğu nedeniyle burada kesiyorum ama orijinal kodundaki tüm fonksiyonları olduğu gibi bırak.

# ... [Orijinal kodundaki tüm fonksiyonları buraya kopyala: fetch_text, build_page_headers, extract_*, resolve_* fonksiyonları] ...

# ====================== ÖNEMLİ GÜNCELLEMELER ======================
def slug_variants(slug):
    value = (slug or "").strip().strip("/")
    if not value:
        return []
    variants = [value]
    izle_suffix = "-izle"
    if value.endswith(izle_suffix):
        base = value[:-len(izle_suffix)].strip("-")
        if base:
            variants.append(base)
    else:
        variants.append(value + izle_suffix)
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

# ====================== ROUTES ======================
@app.route("/yayin/<dizi>/<bolum>", methods=["GET", "HEAD"])
def stream_dizi(dizi, bolum):
    g = auth_guard()
    if g:
        return g

    base = FILMHANE_BASE_DOMAIN
    films = {
        # ... mevcut film haritanı buraya olduğu gibi koy ...
        "28-yil-sonra": f"{base}/film/28-yil-sonra-kemik-tapinagi",
        # diğer filmleri de ekle
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
    seen = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered_candidates.append(c)

    ck = f"yayin:{dizi}:{bolum}"
    cached = cache_get(ck)
    if cached:
        if isinstance(cached, dict):
            return respond_stream(
                cached.get("url") or "",
                cached.get("headers") or {},
                subtitles=cached.get("subtitles") or []
            )
        return redirect_light(cached)

    for target_page in ordered_candidates:
        headers = build_page_headers(target_page)
        detail = resolve_from_page_detail(target_page, headers=headers, max_depth=3)
        stream_url = detail.get("url") or ""
        if stream_url:
            playback_headers = make_playback_headers(stream_url)
            payload = {
                "url": stream_url,
                "headers": playback_headers,
                "subtitles": detail.get("subtitles") or []
            }
            cache_set(ck, payload, STREAM_CACHE_TTL)
            return respond_stream(stream_url, playback_headers, subtitles=payload["subtitles"])

    return "Yayin bulunamadi.", 404

# Diğer tüm route'lar (home, health, canli, api, imdb vs.) orijinal kodunda nasılsa aynı şekilde kalıyor.

if __name__ == "__main__":
    app.run(debug=True)
