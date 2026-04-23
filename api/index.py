from flask import Flask, Response, request
import os
import re
import time
from threading import Lock
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

# -----------------------------
# Config
# -----------------------------
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
FILMHANE_BASE_DOMAIN = os.getenv("FILMHANE_BASE_DOMAIN", "https://filmhane.fit").rstrip("/")

_ALLOWED_PROXY_HOSTS_RAW = os.getenv("PROXY_ALLOWED_HOSTS", "").strip()
PROXY_ALLOWED_HOSTS = {
    h.strip().lower()
    for h in _ALLOWED_PROXY_HOSTS_RAW.split(",")
    if h.strip()
}

DEFAULT_TIMEOUT = 10
SHORT_TTL = 20
NORMAL_TTL = 45

# -----------------------------
# HTTP session (light retry)
# -----------------------------
SESSION = requests.Session()
_retry = Retry(
    total=2,
    connect=2,
    read=2,
    status=2,
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "HEAD"]),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=30, pool_maxsize=30)
SESSION.mount("http://", _adapter)
SESSION.mount("https://", _adapter)

# -----------------------------
# In-memory cache
# -----------------------------
_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_MAX = 4000

def cache_get(key: str):
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if item["exp"] <= now:
            _CACHE.pop(key, None)
            return None
        return item["val"]

def cache_set(key: str, value: str, ttl_sec: int):
    if not value:
        return
    now = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = {"val": value, "exp": now + max(1, ttl_sec)}
        if len(_CACHE) > _CACHE_MAX:
            # Drop expired first
            expired = [k for k, v in _CACHE.items() if v["exp"] <= now]
            for k in expired:
                _CACHE.pop(k, None)
            # Still big: trim oldest by exp
            if len(_CACHE) > _CACHE_MAX:
                for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1]["exp"])[: len(_CACHE) // 3]:
                    _CACHE.pop(k, None)

# -----------------------------
# Helpers
# -----------------------------
RE_M3U8 = re.compile(r"""["'](https?://[^"'<>\s]+\.m3u8[^"'<>\s]*)["']""", re.IGNORECASE)
RE_ALT = re.compile(r"""(?:file|src)\s*:\s*["'](https?://[^"'<>\s]+\.m3u8[^"'<>\s]*)["']""", re.IGNORECASE)
RE_DAION = re.compile(r"""["'](https?:?\\?/\\?/[^\s"'<>]*?daioncdn[^\s"'<>]*?\.m3u8[^\s"'<>]*?)["']""", re.IGNORECASE)

def auth_guard():
    if API_KEY and request.args.get("k", "") != API_KEY:
        return Response("Unauthorized", status=401)
    return None

def origin_of(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"

def is_http_url(value: str) -> bool:
    try:
        p = urlparse(value.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def normalize_url(raw: str, base_url: str = "") -> str:
    if not raw:
        return ""
    s = raw.strip()
    s = s.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&").replace("\\", "")
    if s.startswith("//"):
        s = "https:" + s
    if base_url and s.startswith("/"):
        s = urljoin(base_url, s)
    return s.strip()

def is_proxy_host_allowed(target_url: str) -> bool:
    if not PROXY_ALLOWED_HOSTS:
        return True
    host = (urlparse(target_url).hostname or "").lower()
    if not host:
        return False
    return any(host == allowed or host.endswith("." + allowed) for allowed in PROXY_ALLOWED_HOSTS)

def redirect_light(target_url: str, ttl: int = SHORT_TTL) -> Response:
    return Response(
        "",
        status=302,
        headers={
            "Location": target_url,
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": f"public, max-age=0, s-maxage={max(1, ttl)}, stale-while-revalidate=120",
        },
    )

def fetch_text(url: str, headers: dict, timeout_sec: int = DEFAULT_TIMEOUT) -> str:
    try:
        r = SESSION.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True)
        if r.status_code >= 400:
            return ""
        r.encoding = r.encoding or "utf-8"
        return r.text or ""
    except Exception:
        return ""

def first_m3u8_from_text(text: str, base_url: str = "") -> str:
    if not text:
        return ""

    m = RE_M3U8.search(text)
    if m:
        u = normalize_url(m.group(1), base_url)
        if is_http_url(u):
            return u

    m = RE_ALT.search(text)
    if m:
        u = normalize_url(m.group(1), base_url)
        if is_http_url(u):
            return u

    return ""

def resolve_from_page(page_url: str, headers: dict, max_iframes: int = 5) -> str:
    html = fetch_text(page_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return ""

    found = first_m3u8_from_text(html, base_url=page_url)
    if found:
        return found

    try:
        soup = BeautifulSoup(html, "html.parser")
        iframe_urls = []
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src") or iframe.get("data-src") or ""
            src = normalize_url(src, base_url=page_url)
            if is_http_url(src):
                iframe_urls.append(src)

        # de-dup
        seen = set()
        unique_iframes = []
        for u in iframe_urls:
            if u in seen:
                continue
            seen.add(u)
            unique_iframes.append(u)

        for iframe_url in unique_iframes[:max_iframes]:
            iframe_origin = origin_of(iframe_url)
            iframe_headers = {
                "User-Agent": BASE_HEADERS["User-Agent"],
                "Referer": (iframe_origin + "/") if iframe_origin else BASE_HEADERS["Referer"],
                "Origin": iframe_origin if iframe_origin else BASE_HEADERS["Origin"],
            }
            iframe_html = fetch_text(iframe_url, headers=iframe_headers, timeout_sec=6)
            found = first_m3u8_from_text(iframe_html, base_url=iframe_url)
            if found:
                return found
    except Exception:
        pass

    return ""

def parse_episode_token(raw_bolum: str):
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

def fetch_dogus_stream(landing_url: str) -> str:
    page_origin = origin_of(landing_url)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (page_origin + "/") if page_origin else BASE_HEADERS["Referer"],
        "Origin": page_origin if page_origin else BASE_HEADERS["Origin"],
    }

    html = fetch_text(landing_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return ""

    m = RE_DAION.search(html)
    if m:
        u = normalize_url(m.group(1), base_url=landing_url)
        if is_http_url(u):
            return u

    return resolve_from_page(landing_url, headers=headers, max_iframes=3)

# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Aksacli Stream API V170 - redirect-only mode (quota-safe)"

@app.route("/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "cache_items": len(_CACHE), "mode": "redirect-only"}

@app.route("/canli/proxy", methods=["GET", "HEAD"])
def proxy_general():
    g = auth_guard()
    if g:
        return g

    target_url = (request.args.get("url") or "").strip()
    if not target_url:
        return "URL eksik", 400
    if not is_http_url(target_url):
        return "Gecersiz URL", 400
    if not is_proxy_host_allowed(target_url):
        return "Host izinli degil", 403

    # IMPORTANT: no content proxying, only redirect
    return redirect_light(target_url, ttl=SHORT_TTL)

@app.route("/canli/gold.m3u8", methods=["GET", "HEAD"])
def proxy_gold():
    g = auth_guard()
    if g:
        return g
    return redirect_light("https://goldvod.site/live/hpgdisco/123456/266.m3u8", ttl=SHORT_TTL)

@app.route("/canli/sup.m3u8", methods=["GET", "HEAD"])
def proxy_sup():
    g = auth_guard()
    if g:
        return g
    return redirect_light(
        "http://sup-4k.org:80/play/live.php?mac=00:1A:79:56:7A:24&stream=10740&extension=ts",
        ttl=SHORT_TTL,
    )

@app.route("/canli/<kanal>", methods=["GET", "HEAD"])
def stream_canli(kanal: str):
    g = auth_guard()
    if g:
        return g

    kanal = (kanal or "").strip().lower()

    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv",
    }

    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber",
        "aspor": "https://cdn504.tvkulesi.com/aspor.m3u8?hst=amp.tvkulesi.com&ch=a-spor",
    }

    cache_key = f"canli:{kanal}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    if kanal in turkuvaz:
        return redirect_light(turkuvaz[kanal], ttl=SHORT_TTL)

    if kanal in dogus:
        link = fetch_dogus_stream(dogus[kanal])
        if link:
            cache_set(cache_key, link, ttl_sec=60)
            return redirect_light(link, ttl=SHORT_TTL)

    return "Kanal bulunamadi.", 404

@app.route("/api", methods=["GET", "HEAD"])
def resolve_universal():
    g = auth_guard()
    if g:
        return g

    target_url = (request.args.get("url") or "").strip()
    if not target_url:
        return "URL eksik. Kullanim: /api?url=...", 400
    if not is_http_url(target_url):
        return "Gecersiz URL", 400

    cache_key = f"api:{target_url}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    dom = origin_of(target_url)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (dom + "/") if dom else BASE_HEADERS["Referer"],
        "Origin": dom if dom else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_url, headers=headers, max_iframes=5)
    if stream_url:
        cache_set(cache_key, stream_url, ttl_sec=NORMAL_TTL)
        return redirect_light(stream_url, ttl=SHORT_TTL)

    return "Video kaynagi bulunamadi.", 404

@app.route("/yayin/<dizi>/<bolum>", methods=["GET", "HEAD"])
def stream_dizi(dizi: str, bolum: str):
    g = auth_guard()
    if g:
        return g

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
    }

    if dizi in films:
        target_page = films[dizi]
    else:
        sezon_no, bolum_no = parse_episode_token(bolum)
        target_page = f"{base}/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"

    cache_key = f"yayin:{target_page}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    base_origin = origin_of(base)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (base + "/"),
        "Origin": base_origin if base_origin else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_page, headers=headers, max_iframes=6)
    if stream_url:
        # short cache because many film links are tokenized
        cache_set(cache_key, stream_url, ttl_sec=25)
        return redirect_light(stream_url, ttl=15)

    return "Yayin bulunamadi.", 404

if __name__ == "__main__":
    app.run(debug=True)
