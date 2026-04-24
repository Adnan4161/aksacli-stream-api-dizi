from flask import Flask, Response, request
import json
import os
import re
import time
from threading import Lock
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

VERSION = "V173"

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
SHORT_TTL = 15
NORMAL_TTL = 30

FILMHANE_EDGE_DEFAULT_REFERER = "https://x.ag2m4.cfd/"
FILMHANE_EDGE_DEFAULT_ORIGIN = "https://x.ag2m4.cfd"

# In-memory cache (best effort)
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
RE_PLAYERJS_FETCH = re.compile(r"""fetch\(\s*[\"']([^\"']*?/dl\?op=get_stream[^\"']*)[\"']\s*\)""", re.IGNORECASE)
RE_JS_COOKIE = re.compile(r"""\$\.cookie\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]""", re.IGNORECASE)


# HTTP session with tiny retry
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

    # Filmhane playerjs edge servers often require this explicit origin/ref.
    if ("uk-traffic-" in host or "rapidrame.com" in host) and not referer_hint:
        referer = FILMHANE_EDGE_DEFAULT_REFERER
        origin = FILMHANE_EDGE_DEFAULT_ORIGIN

    if referer:
        headers["Referer"] = referer
    if origin:
        headers["Origin"] = origin

    return headers


def respond_stream(stream_url, playback_headers=None, ttl=SHORT_TTL):
    playback_headers = playback_headers or {}
    if wants_json():
        return {
            "ok": True,
            "mode": "json",
            "url": stream_url,
            "headers": playback_headers,
            "ttl": max(1, int(ttl)),
        }
    return redirect_light(stream_url, ttl=ttl)


def fetch_text(url, headers, timeout_sec=DEFAULT_TIMEOUT):
    try:
        r = SESSION.get(url, headers=headers, timeout=timeout_sec, allow_redirects=True)
        if r.status_code >= 400:
            return ""
        r.encoding = r.encoding or "utf-8"
        return r.text or ""
    except Exception:
        return ""


def dedup_keep_order(items):
    out = []
    seen = set()
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def extract_m3u8_candidates(text, base_url):
    cands = []

    for m in RE_M3U8_ESCAPED.findall(text or ""):
        u = normalize_url(m, base_url)
        if is_http_url(u):
            cands.append(u)

    for m in RE_M3U8_DIRECT.findall(text or ""):
        u = normalize_url(m, base_url)
        if is_http_url(u):
            cands.append(u)

    for m in RE_M3U8_FILESRC.findall(text or ""):
        u = normalize_url(m, base_url)
        if is_http_url(u):
            cands.append(u)

    return dedup_keep_order(cands)


def extract_iframe_candidates(text, base_url):
    urls = []

    for raw in RE_IFRAME.findall(text or ""):
        u = normalize_url(raw, base_url)
        if is_http_url(u):
            urls.append(u)

    for raw in RE_DATA_EMBED.findall(text or ""):
        u = normalize_url(raw, base_url)
        if is_http_url(u):
            urls.append(u)

    if not urls:
        try:
            soup = BeautifulSoup(text or "", "html.parser")
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src") or iframe.get("data-src") or ""
                u = normalize_url(src, base_url)
                if is_http_url(u):
                    urls.append(u)
        except Exception:
            pass

    return dedup_keep_order(urls)


def extract_playerjs_dl_url(embed_html, embed_url):
    m = RE_PLAYERJS_FETCH.search(embed_html or "")
    if not m:
        return ""
    return normalize_url(m.group(1), base_url=embed_url)


def extract_inline_js_cookies(embed_html):
    cookies = {}
    for key, val in RE_JS_COOKIE.findall(embed_html or ""):
        k = (key or "").strip()
        if not k:
            continue
        cookies[k] = (val or "").strip()
    return cookies


def cookie_header(cookies):
    if not cookies:
        return ""
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def extract_url_from_jsonish(body, base_url=""):
    if not body:
        return ""

    # strict JSON first
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            raw = data.get("url") or data.get("stream") or data.get("file")
            if raw:
                u = normalize_url(str(raw), base_url)
                if is_http_url(u):
                    return u
    except Exception:
        pass

    # fallback regex
    m = re.search(r'"url"\s*:\s*"([^"]+)"', body, re.IGNORECASE)
    if not m:
        m = re.search(r"'url'\s*:\s*'([^']+)'", body, re.IGNORECASE)
    if m:
        u = normalize_url(m.group(1), base_url)
        if is_http_url(u):
            return u

    return ""


def resolve_playerjs_embed(embed_url, upstream_headers):
    embed_origin = origin_of(embed_url)
    embed_headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Referer": upstream_headers.get("Referer", embed_origin + "/" if embed_origin else BASE_HEADERS["Referer"]),
        "Origin": upstream_headers.get("Origin", embed_origin if embed_origin else BASE_HEADERS["Origin"]),
    }

    embed_html = fetch_text(embed_url, embed_headers, timeout_sec=DEFAULT_TIMEOUT)
    if not embed_html:
        return ""

    # direct m3u8 in embed HTML
    direct = extract_m3u8_candidates(embed_html, embed_url)
    if direct:
        return direct[0]

    dl_url = extract_playerjs_dl_url(embed_html, embed_url)
    if not dl_url or not is_http_url(dl_url):
        return ""

    js_cookies = extract_inline_js_cookies(embed_html)
    c_header = cookie_header(js_cookies)

    referer_candidates = [embed_url]
    if embed_origin:
        referer_candidates.append(embed_origin + "/")

    for ref in dedup_keep_order(referer_candidates):
        dl_headers = {
            "User-Agent": embed_headers["User-Agent"],
            "Referer": ref,
            "Origin": embed_origin or embed_headers["Origin"],
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        if c_header:
            dl_headers["Cookie"] = c_header

        body = fetch_text(dl_url, dl_headers, timeout_sec=DEFAULT_TIMEOUT)
        u = extract_url_from_jsonish(body, base_url=dl_url)
        if u and ".m3u8" in u.lower():
            return u

    return ""


def resolve_from_page(page_url, headers, depth=0, max_depth=3):
    html = fetch_text(page_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return ""

    cands = extract_m3u8_candidates(html, page_url)
    if cands:
        return cands[0]

    if depth >= max_depth:
        return ""

    embeds = extract_iframe_candidates(html, page_url)
    for u in embeds[:8]:
        low = u.lower()

        # playerjs style embed (filmhane source)
        if "embed" in low or "/dl?op=get_stream" in low:
            fast = resolve_playerjs_embed(u, headers)
            if fast:
                return fast

        next_origin = origin_of(u)
        next_headers = {
            "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
            "Referer": (next_origin + "/") if next_origin else headers.get("Referer", BASE_HEADERS["Referer"]),
            "Origin": next_origin if next_origin else headers.get("Origin", BASE_HEADERS["Origin"]),
        }
        found = resolve_from_page(u, next_headers, depth + 1, max_depth)
        if found:
            return found

    return ""


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


def fetch_dogus_stream(landing_url):
    page_origin = origin_of(landing_url)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (page_origin + "/") if page_origin else BASE_HEADERS["Referer"],
        "Origin": page_origin if page_origin else BASE_HEADERS["Origin"],
    }

    html = fetch_text(landing_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if html:
        m = RE_DAION.search(html)
        if m:
            u = normalize_url(m.group(1), landing_url)
            if is_http_url(u):
                return u

        cands = extract_m3u8_candidates(html, landing_url)
        if cands:
            return cands[0]

    return resolve_from_page(landing_url, headers=headers, max_depth=1)


@app.route("/", methods=["GET", "HEAD"])
def home():
    return f"Aksacli Stream API {VERSION} - redirect-only quota-safe"


@app.route("/health", methods=["GET", "HEAD"])
def health():
    return {
        "ok": True,
        "version": VERSION,
        "mode": "redirect-only",
        "resolver": "playerjs-dl-enabled",
        "cache_items": len(_CACHE),
        "api_key_enabled": bool(API_KEY),
    }


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
def stream_canli(kanal):
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

    ck = f"canli:{kanal}"
    cached = cache_get(ck)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    if kanal in turkuvaz:
        return redirect_light(turkuvaz[kanal], ttl=SHORT_TTL)

    if kanal in dogus:
        link = fetch_dogus_stream(dogus[kanal])
        if link:
            cache_set(ck, link, 60)
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

    ck = f"api:{target_url}"
    cached = cache_get(ck)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    dom = origin_of(target_url)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (dom + "/") if dom else BASE_HEADERS["Referer"],
        "Origin": dom if dom else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_url, headers=headers, max_depth=3)
    if stream_url:
        cache_set(ck, stream_url, NORMAL_TTL)
        playback_headers = make_playback_headers(
            stream_url=stream_url,
            referer_hint=dom + "/" if dom else "",
            origin_hint=dom
        )
        return respond_stream(stream_url, playback_headers=playback_headers, ttl=SHORT_TTL)

    return "Video kaynagi bulunamadi.", 404


@app.route("/yayin/<dizi>/<bolum>", methods=["GET", "HEAD"])
def stream_dizi(dizi, bolum):
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

    # token links can expire quickly -> tiny cache
    ck = f"yayin:{target_page}"
    cached = cache_get(ck)
    if cached:
        return redirect_light(cached, ttl=5)

    base_origin = origin_of(base)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": f"{base}/",
        "Origin": base_origin if base_origin else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_page, headers=headers, max_depth=3)
    if stream_url:
        cache_set(ck, stream_url, 5)
        playback_headers = make_playback_headers(stream_url=stream_url)
        return respond_stream(stream_url, playback_headers=playback_headers, ttl=5)

    return "Yayin bulunamadi.", 404


if __name__ == "__main__":
    app.run(debug=True)
