from flask import Flask, Response, request
import base64
import html as html_lib
import json
import os
import re
import time
from threading import Lock
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

VERSION = "V203"

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
DIZIFILM_BASE_DOMAIN = os.getenv("DIZIFILM_BASE_DOMAIN", "https://dizifilm.life/film/polar-opposites").rstrip("/")
HDIZIPAL_BASE_DOMAIN = os.getenv("HDIZIPAL_BASE_DOMAIN", "https://hdizipal.com").rstrip("/")
HDFILMCEHENNEMI_BASE_DOMAIN = os.getenv("HDFILMCEHENNEMI_BASE_DOMAIN", "https://www.hdfilmcehennemi.nl").rstrip("/")
HDFILMCEHENNEMI_EMBED_DOMAIN = os.getenv("HDFILMCEHENNEMI_EMBED_DOMAIN", "https://hdfilmcehennemi.mobi").rstrip("/")
HDFILMIZLETO_BASE_DOMAIN = os.getenv("HDFILMIZLETO_BASE_DOMAIN", "https://www.hdfilmizle.to").rstrip("/")
FILMMAKINESI_BASE_DOMAIN = os.getenv("FILMMAKINESI_BASE_DOMAIN", "https://filmmakinesi.to").rstrip("/")
FULLHDFILMIZLESENE_BASE_DOMAIN = os.getenv("FULLHDFILMIZLESENE_BASE_DOMAIN", "https://www.fullhdfilmizlesene.life").rstrip("/")
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

# In-memory cache (best effort)
_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_MAX = 4000

# Regex set
RE_M3U8_DIRECT = re.compile(r"https?://[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_ESCAPED = re.compile(r"https?:\\/\\/[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_FILESRC = re.compile(r"(?:file|src)\s*[:=]\s*[\"']([^\"']+\.m3u8[^\"']*)[\"']", re.IGNORECASE)
RE_JWPLAYER_FILE_URL = re.compile(r"""["']file["']\s*:\s*["']((?:\\.|[^"'\\])+)["']""", re.IGNORECASE | re.DOTALL)
RE_VIDMOXY_ENCODED_VALUE = re.compile(
    r"""(?:["']q["']\s*:\s*["']([^"']+)["']|_\(\s*["']([^"']+)["']\s*\))""",
    re.IGNORECASE | re.DOTALL,
)
RE_DAION = re.compile(r"[\"'](https?:?\\?/\\?/[^\s\"'<>]*?daioncdn[^\s\"'<>]*?\.m3u8[^\s\"'<>]*?)[\"']", re.IGNORECASE)
RE_IFRAME = re.compile(r"<iframe[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_DATA_EMBED = re.compile(r"data-(?:hhs|frame)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_DATA_VIDEO_URL = re.compile(r"""data-video[_-]?url=["']([^"']+)["']""", re.IGNORECASE)
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
RE_HDFILMCEHENNEMI_DECODER = re.compile(
    r"""function\s+(dc_[A-Za-z0-9_]+).*?charCode\s*=\s*\(charCode\s*-\s*\((\d+)\s*%\s*\(i\s*\+\s*(\d+)\)\).*?var\s+(s_[A-Za-z0-9_]+)\s*=\s*\1\(\[(.*?)\]\)""",
    re.IGNORECASE | re.DOTALL,
)
RE_JWPLAYER_TRACKS = re.compile(r"""(?:tracks\s*:|configs\.tracks\s*=|jwSetup\.tracks\s*=)\s*(\[[^\]]*\])""", re.IGNORECASE | re.DOTALL)
RE_HDFILMCEHENNEMI_EMBED_ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")
RE_VIDRAME_DD = re.compile(r"""EE\.dd\(\s*["']([^"']+)["']\s*\)""", re.IGNORECASE)
RE_FULLHDFILMIZLESENE_SCX = re.compile(r"""var\s+scx\s*=\s*(\{.*?\})\s*;""", re.IGNORECASE | re.DOTALL)
RE_RAPIDVID_AV_FILE = re.compile(r"""["']file["']\s*:\s*av\(\s*["']([^"']+)["']\s*\)""", re.IGNORECASE | re.DOTALL)
RE_PLAYER_CONFIGS = re.compile(r"""playerConfigs\s*=\s*(\{.*?\})\s*;""", re.IGNORECASE | re.DOTALL)

HDFILMCEHENNEMI_KNOWN_EMBEDS = {
    "kac-run-izle-hdf-6": "cvoodwhGycV",
    "kac-run-izle": "cvoodwhGycV",
    "kac-run": "cvoodwhGycV",
}

FULLHDFILMIZLESENE_KNOWN_RAPIDVIDS = {
    "abd-1994-brezilya-nin-muhtesem-donusu-tetra-acreditar-de-novo": "v1x89512e1b",
    "run-2020": "v1x3dff5ca0",
    "run-2020-2": "v1x3dff5ca0",
}

FULLHDFILMIZLESENE_KNOWN_SOBREATS = {
    "sniper-the-white-raven": [
        "82082b2cca44274df97053c381591b0d",
        "864bbe578e7cbde7188bedf699a2128a",
    ],
}

FULLHDFILMIZLESENE_KNOWN_VIDMOXY = {
    "blue-jay": [
        "https://vidmoxy.net/pt/v1x9b090c1a",
    ],
    "paralel-evren": [
        "https://vidmoxy.net/pt/v1x36467b6d",
    ],
}

VIDMOXY_KNOWN_STREAMS = {
    "https://vidmoxy.net/pt/v1x9b090c1a": "https://v1.pictobox.live/mz/Dzk1MF5XLKxhZwNkAv4kZQtjpP5KEHWFnKNhEUIuoNd0zxpTywqT9vo3thoTy2MDs0xi1vr1",
    "https://vidmoxy.net/pt/v1x36467b6d": "https://v1.pictobox.live/m2/HTSlLJkyoP5SqaWyov5Qo2uypzIhL2HhZwNkZl4kZQtjpP5RqJSfd0zxpTywqT9vo3thL2Mxs0xi1vr1",
}


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


def wants_debug():
    return (request.args.get("debug") or "").strip().lower() in {"1", "true", "yes"}


def json_response(payload, status=200):
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        status=status,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
        },
    )


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


def respond_stream(stream_url, playback_headers=None, ttl=SHORT_TTL, subtitles=None):
    playback_headers = playback_headers or {}
    subtitles = subtitles or []
    stream_url = stabilize_stream_url(stream_url)
    if wants_json():
        client_url = client_playback_url(stream_url)
        return {
            "ok": True,
            "mode": "json",
            "url": client_url,
            "mimeType": "application/x-mpegURL" if client_url != stream_url else "",
            "headers": playback_headers,
            "subtitles": subtitles,
            "ttl": max(1, int(ttl)),
        }
    return redirect_light(stream_url, ttl=ttl)


def client_playback_url(stream_url):
    if not is_fullhdfilmizlesene_stream_host(stream_url):
        return stream_url

    lower = (stream_url or "").lower()
    if ".m3u8" in lower or "ext=m3u8" in lower or "format=m3u8" in lower or "type=m3u8" in lower:
        return stream_url

    parsed = urlparse(stream_url)
    fragment = parsed.fragment or ""
    if "ext=m3u8" in fragment.lower():
        return stream_url
    new_fragment = f"{fragment}&ext=m3u8" if fragment else "ext=m3u8"
    return urlunparse(parsed._replace(fragment=new_fragment))


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


def probe_stream_url(stream_url):
    try:
        r = SESSION.get(
            stream_url,
            headers=make_playback_headers(stream_url),
            timeout=4,
            allow_redirects=True,
            stream=True,
        )
        try:
            if r.status_code != 200:
                return False
            content_type = (r.headers.get("content-type") or "").lower()
            if "mpegurl" in content_type or "application/octet-stream" in content_type:
                return True
            sample = next(r.iter_content(chunk_size=512), b"")
            return sample.lstrip().startswith(b"#EXTM3U")
        finally:
            r.close()
    except Exception:
        return False


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


def post_text(url, headers, timeout_sec=DEFAULT_TIMEOUT):
    try:
        r = SESSION.post(url, headers=headers, data="", timeout=timeout_sec, allow_redirects=True)
        if r.status_code >= 400:
            return ""
        r.encoding = r.encoding or "utf-8"
        return r.text or ""
    except Exception:
        return ""


def fetch_or_post_text(url, headers, timeout_sec=DEFAULT_TIMEOUT):
    text = fetch_text(url, headers=headers, timeout_sec=timeout_sec)
    if text:
        return text
    return post_text(url, headers=headers, timeout_sec=timeout_sec)


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


def extract_jwplayer_file_candidates(text, base_url):
    cands = []
    sources = [text or ""]
    decoded = html_lib.unescape(text or "").replace("\\/", "/").replace("\\u0026", "&")
    if decoded and decoded not in sources:
        sources.append(decoded)

    for source in sources:
        for raw in RE_JWPLAYER_FILE_URL.findall(source or ""):
            value = decode_js_string_literal(raw).replace("\\/", "/").replace("\\u0026", "&")
            u = normalize_url(value, base_url)
            if is_http_url(u):
                cands.append(u)

    return dedup_keep_order(cands)


def extract_iframe_candidates(text, base_url):
    urls = []
    sources = [text or ""]
    decoded = html_lib.unescape(text or "")
    decoded = decoded.replace("\\/", "/").replace('\\"', '"').replace("\\u0026", "&")
    if decoded and decoded not in sources:
        sources.append(decoded)

    for source in sources:
        for raw in RE_IFRAME.findall(source):
            u = normalize_url(raw, base_url)
            if is_http_url(u):
                urls.append(u)

        for raw in RE_DATA_EMBED.findall(source):
            u = normalize_url(raw, base_url)
            if is_http_url(u):
                urls.append(u)

        for raw in RE_DATA_VIDEO_URL.findall(source):
            u = normalize_url(raw, base_url)
            if is_http_url(u):
                urls.append(u)

    if not urls:
        try:
            soup = BeautifulSoup(decoded or text or "", "html.parser")
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src") or iframe.get("data-src") or ""
                u = normalize_url(src, base_url)
                if is_http_url(u):
                    urls.append(u)
        except Exception:
            pass

    for source in sources:
        for u in extract_fullhd_iframe_candidates(source, base_url):
            urls.append(u)

    for source in sources:
        for u in extract_atob_iframe_candidates(source, base_url):
            urls.append(u)

    for source in sources:
        for u in extract_fullhdfilmizlesene_iframe_candidates(source, base_url):
            urls.append(u)

    return dedup_keep_order(urls)


def extract_atob_iframe_candidates(text, base_url):
    urls = []
    for raw_list in re.findall(r"""var\s+_\s*=\s*\[([^\]]+)\]""", text or "", re.IGNORECASE | re.DOTALL):
        parts = re.findall(r"""["']([^"']+)["']""", raw_list)
        decoded_parts = []
        for part in parts:
            try:
                decoded_parts.append(base64.b64decode(part).decode("utf-8", errors="ignore"))
            except Exception:
                decoded_parts.append("")
        candidate = "".join(decoded_parts).strip()
        u = normalize_url(candidate, base_url)
        if is_http_url(u):
            urls.append(u)

    return dedup_keep_order(urls)


def decode_base64_text(value, encoding="utf-8"):
    text = (value or "").strip().replace("-", "+").replace("_", "/")
    if not text:
        return ""
    text += "=" * ((4 - len(text) % 4) % 4)
    try:
        return base64.b64decode(text).decode(encoding, errors="ignore")
    except Exception:
        return ""


def decode_fullhdfilmizlesene_scx_value(value):
    return decode_base64_text(rot13_text(value or ""))


def decode_rapidvid_av_value(value):
    raw = decode_base64_text((value or "")[::-1], encoding="latin-1")
    if not raw:
        return ""

    key = "K9L"
    mixed = []
    for idx, ch in enumerate(raw):
        mixed.append(chr(ord(ch) - ((ord(key[idx % len(key)]) % 5) + 1)))

    return decode_base64_text("".join(mixed))


def iter_scx_values(bucket):
    if isinstance(bucket, list):
        for value in bucket:
            yield value
        return

    if isinstance(bucket, dict):
        preferred_keys = ["tr", "tek", "default", "0", "en"]
        seen = set()
        for key in preferred_keys:
            if key in bucket:
                seen.add(key)
                yield bucket[key]
        for key, value in bucket.items():
            if key not in seen:
                yield value


def extract_fullhdfilmizlesene_iframe_candidates(text, base_url):
    urls = []
    m = RE_FULLHDFILMIZLESENE_SCX.search(text or "")
    if not m:
        return urls

    try:
        payload = json.loads(m.group(1))
    except Exception:
        return urls

    if not isinstance(payload, dict):
        return urls

    items = []
    for name, item in payload.items():
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order", 999))
        except Exception:
            order = 999
        items.append((order, name, item))

    for _, _, item in sorted(items, key=lambda x: x[0]):
        sx = item.get("sx") if isinstance(item.get("sx"), dict) else {}
        for bucket in (sx.get("t"), sx.get("p")):
            for encoded in iter_scx_values(bucket):
                decoded = decode_fullhdfilmizlesene_scx_value(str(encoded or ""))
                if not decoded:
                    continue
                iframe_urls = extract_iframe_candidates(decoded, base_url) if "<" in decoded else []
                if iframe_urls:
                    urls.extend(iframe_urls)
                    continue
                u = normalize_url(decoded, base_url)
                if is_http_url(u):
                    urls.append(u)

    return dedup_keep_order(urls)


def decode_js_string_literal(raw):
    value = html_lib.unescape(raw or "")
    try:
        return json.loads(f'"{value}"')
    except Exception:
        try:
            return value.encode("utf-8").decode("unicode_escape")
        except Exception:
            return value.replace("\\'", "'")


def extract_fullhd_iframe_candidates(text, base_url):
    urls = []

    for raw_payload, default_lang in RE_FULLHD_VIDEO_DATA.findall(text or ""):
        payload_text = decode_js_string_literal(raw_payload)
        try:
            payload = json.loads(payload_text)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        videos = payload.get((default_lang or "").strip())
        if not isinstance(videos, list):
            videos = []
            for value in payload.values():
                if isinstance(value, list):
                    videos = value
                    break

        for video in videos[:8]:
            if not isinstance(video, dict):
                continue

            link = str(video.get("link") or "").strip()
            template_raw = str(video.get("template") or "").strip()
            service_slug = str(video.get("service_slug") or "").strip()
            if not link or not template_raw:
                continue

            try:
                template = base64.b64decode(template_raw).decode("utf-8", errors="ignore")
            except Exception:
                template = template_raw

            rendered = template.replace("{url}", link).replace("{slug}", service_slug)
            for raw in re.findall(r"""(?:src|data-src)=["']([^"']+)["']""", rendered, re.IGNORECASE):
                u = normalize_url(raw, base_url)
                if is_http_url(u):
                    urls.append(u)

            for raw in re.findall(r"https?://[^\"'<>\s]+", rendered, re.IGNORECASE):
                u = normalize_url(raw, base_url)
                if is_http_url(u):
                    urls.append(u)

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


def normalize_subtitle_language(label):
    text = (label or "").strip().lower().replace("\u0307", "").translate(str.maketrans({
        "\u0131": "i",
        "\u011f": "g",
        "\u00fc": "u",
        "\u015f": "s",
        "\u00f6": "o",
        "\u00e7": "c",
    }))
    text = (
        text.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    if "turk" in text or text in ("tr", "tur", "turkish"):
        return "tr"
    if "eng" in text or "ingiliz" in text or text in ("en", "english"):
        return "en"
    return ""


def subtitle_mime_type(url):
    low = (url or "").lower().split("?", 1)[0]
    if low.endswith(".srt"):
        return "application/x-subrip"
    return "text/vtt"


def extract_playerjs_subtitles(embed_html, embed_url=""):
    tracks = []
    seen = set()

    raw_values = []
    raw_values.extend(RE_PLAYERJS_SUBTITLE.findall(embed_html or ""))
    raw_values.extend(RE_PLAYERJS_SUBTITLE_ASSIGN.findall(embed_html or ""))

    for raw in raw_values:
        raw = html_lib.unescape(raw or "")
        raw = raw.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")
        matches = RE_SUBTITLE_URL.findall(raw)
        if not matches:
            matches = RE_ANY_SUBTITLE_URL.findall(raw)
        for label, raw_url in matches:
            url = normalize_url(raw_url, base_url=embed_url)
            if not is_http_url(url) or url in seen:
                continue
            seen.add(url)
            clean_label = (label or "").strip() or "Altyazi"
            tracks.append({
                "url": url,
                "label": clean_label,
                "language": normalize_subtitle_language(clean_label) or "tr",
                "mimeType": subtitle_mime_type(url),
            })

    return tracks


def extract_jwplayer_subtitles(embed_html, embed_url=""):
    tracks = []
    seen = set()

    def add_track(raw_url, label="", is_default=False):
        url = normalize_url(str(raw_url or ""), base_url=embed_url)
        if not is_http_url(url) or url in seen:
            return
        low = url.lower().split("?", 1)[0]
        if not (low.endswith(".vtt") or low.endswith(".srt")):
            return
        seen.add(url)
        clean_label = (label or "").strip() or "Altyazi"
        tracks.append({
            "url": url,
            "label": clean_label,
            "language": normalize_subtitle_language(clean_label) or "tr",
            "mimeType": subtitle_mime_type(url),
            "default": bool(is_default),
        })

    source = re.sub(r"/\*.*?\*/", "", embed_html or "", flags=re.DOTALL)
    for raw_array in RE_JWPLAYER_TRACKS.findall(source):
        try:
            payload = json.loads(raw_array)
        except Exception:
            payload = None

        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if str(item.get("kind") or "").lower() not in ("", "captions", "subtitles"):
                    continue
                add_track(item.get("file"), item.get("label"), item.get("default"))
            continue

        for m in re.finditer(
            r""""file"\s*:\s*"([^"]+?\.(?:vtt|srt)[^"]*)".*?"label"\s*:\s*"([^"]*)"(?:.*?"default"\s*:\s*(true|false))?""",
            raw_array,
            re.IGNORECASE | re.DOTALL,
        ):
            add_track(m.group(1), m.group(2), (m.group(3) or "").lower() == "true")

    return tracks


def merge_subtitle_tracks(*track_lists):
    merged = []
    seen = set()
    for track_list in track_lists:
        for track in track_list or []:
            url = track.get("url") if isinstance(track, dict) else ""
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(track)
    return merged


def is_hlszone_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        return host == "hlszone.com" and "/video/" in p.path.lower()
    except Exception:
        return False


def hlszone_video_id(embed_url):
    try:
        path = urlparse(embed_url or "").path
    except Exception:
        return ""

    m = re.search(r"/video/([^/?#]+)", path, re.IGNORECASE)
    if not m:
        return ""
    return (m.group(1) or "").strip()


def is_hdfilmcehennemi_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        return host.endswith("hdfilmcehennemi.mobi") and "/video/embed/" in p.path.lower()
    except Exception:
        return False


def is_filmmakinesi_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:
        return False

    return (
        host in ("closeload.filmmakinesi.to", "rapid.filmmakinesi.to")
        and ("embed" in path or "/video/" in path)
    )


def is_rapidvid_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:
        return False

    return host == "rapidvid.net" and "/vod/" in path


def is_sobreatsesuyp_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:
        return False

    return host.endswith("sobreatsesuyp.com") and "/iframe" in path


def is_vidmoxy_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:
        return False

    return (
        (host == "vidmoxy.net" or host.endswith(".vidmoxy.net"))
        and ("/fl/" in path or "/pt/" in path or "/embed/" in path or "/v/" in path)
    )


def rapidvid_embed_url(video_id):
    clean_id = (video_id or "").strip().strip("/")
    if not clean_id:
        return ""
    if not clean_id.startswith("v1x"):
        clean_id = "v1x" + clean_id
    return f"https://rapidvid.net/vod/{clean_id}"


def sobreat_embed_url(video_id):
    clean_id = (video_id or "").strip().strip("/")
    if not clean_id:
        return ""
    return f"https://sobreatsesuyp.com/movie/{clean_id}/iframe"


def vidmoxy_embed_url(video_id):
    clean_id = (video_id or "").strip().strip("/")
    if not clean_id:
        return ""
    if clean_id.startswith("http://") or clean_id.startswith("https://"):
        return clean_id
    if not clean_id.startswith("v1x"):
        clean_id = "v1x" + clean_id
    return f"https://vidmoxy.net/pt/{clean_id}"


def vidmoxy_known_stream_url(embed_url):
    key = (embed_url or "").strip().rstrip("/").lower()
    if not key:
        return ""
    return VIDMOXY_KNOWN_STREAMS.get(key, "")


def normalize_vidmoxy_stream_url(stream_url):
    try:
        p = urlparse(stream_url or "")
    except Exception:
        return stream_url

    host = (p.hostname or "").lower()
    if host == "pictobox.cfd":
        return urlunparse(p._replace(netloc="pictobox.live"))
    if host.endswith(".pictobox.cfd"):
        fixed_host = host[: -len(".pictobox.cfd")] + ".pictobox.live"
        if p.port:
            fixed_host = f"{fixed_host}:{p.port}"
        return urlunparse(p._replace(netloc=fixed_host))
    return stream_url


def fullhdfilmizlesene_rapidvid_id_for_slug(slug):
    clean_slug = (slug or "").strip().strip("/").lower()
    if not clean_slug:
        return ""

    mapped = FULLHDFILMIZLESENE_KNOWN_RAPIDVIDS.get(clean_slug)
    if mapped:
        return mapped

    for prefix in ("rapidvid-", "rv-"):
        if clean_slug.startswith(prefix):
            candidate = clean_slug[len(prefix):].strip("-/")
            if re.match(r"^(?:v1x)?[a-z0-9]+$", candidate):
                return candidate

    return ""


def fullhdfilmizlesene_sobreat_ids_for_slug(slug):
    clean_slug = (slug or "").strip().strip("/").lower()
    if not clean_slug:
        return []
    return FULLHDFILMIZLESENE_KNOWN_SOBREATS.get(clean_slug, [])


def fullhdfilmizlesene_vidmoxy_urls_for_slug(slug):
    clean_slug = (slug or "").strip().strip("/").lower()
    if not clean_slug:
        return []
    return [
        vidmoxy_embed_url(video_id)
        for video_id in FULLHDFILMIZLESENE_KNOWN_VIDMOXY.get(clean_slug, [])
        if vidmoxy_embed_url(video_id)
    ]


def is_fullhdfilmizlesene_stream_host(url):
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return False
    return (
        host == "photogrids.site" or host.endswith(".photogrids.site")
        or host == "imglink.info" or host.endswith(".imglink.info")
        or host == "pixtures.art" or host.endswith(".pixtures.art")
        or host == "imgz.me" or host.endswith(".imgz.me")
        or host == "pictobox.live" or host.endswith(".pictobox.live")
        or host == "pictobox.cfd" or host.endswith(".pictobox.cfd")
    )


def hdfilmcehennemi_embed_url(embed_id):
    clean_id = (embed_id or "").strip().strip("/")
    if not clean_id:
        return ""
    return f"{HDFILMCEHENNEMI_EMBED_DOMAIN}/video/embed/{clean_id}/"


def hdfilmcehennemi_embed_id_for_slug(slug):
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return ""

    mapped = HDFILMCEHENNEMI_KNOWN_EMBEDS.get(clean_slug.lower())
    if mapped:
        return mapped

    for prefix in ("hdf-", "hdfc-", "hdfilm-", "hdfilmcehennemi-"):
        if clean_slug.lower().startswith(prefix):
            candidate = clean_slug[len(prefix):].strip("-/")
            if RE_HDFILMCEHENNEMI_EMBED_ID.match(candidate):
                return candidate

    return ""


def hdfilmcehennemi_slug_from_url(page_url):
    try:
        p = urlparse(page_url or "")
    except Exception:
        return ""

    host = (p.hostname or "").lower()
    if "hdfilmcehennemi" not in host:
        return ""

    parts = [part for part in p.path.strip("/").split("/") if part]
    if not parts:
        return ""

    if parts[0].lower() == "dizi" and len(parts) > 1:
        return parts[1]

    return parts[0]


def is_probable_hls_manifest_url(url):
    low = (url or "").lower().split("?", 1)[0]
    if ".m3u8" in low:
        return True
    if "/hls/" in low and (low.endswith("/master.txt") or low.endswith(".m3u") or "/txt/" in low and low.endswith(".txt")):
        return True
    return False


def is_hdfilmcehennemi_stream_host(url):
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return False
    return (
        host.endswith(".cdnimages2500.shop")
        or re.match(r"^srv\d+\.cdnimages\d+\.shop$", host) is not None
        or host.endswith(".playmix.uno")
    )


def is_hdfilmizleto_page_url(url):
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return False
    return host == "hdfilmizle.to" or host.endswith(".hdfilmizle.to")


def is_vidrame_embed_url(url):
    try:
        p = urlparse(url or "")
        host = (p.hostname or "").lower()
    except Exception:
        return False
    return host == "vidrame.pro" and "/vr/" in (p.path or "").lower()


def is_hdfilmizleto_stream_host(url):
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return False
    return host == "p1.photofunny.org" or host.endswith(".photofunny.org")


def normalize_hdfilmizleto_media_url(url):
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if host == "p1.photofunia.pro":
        return replace_url_host(url, "p1.photofunny.org")
    return url


def hdfilmcehennemi_proxy_url(target_url, referer_url):
    if not is_http_url(target_url) or not is_probable_hls_manifest_url(target_url):
        return target_url
    if not is_hdfilmcehennemi_stream_host(target_url):
        return target_url

    root = request.url_root.rstrip("/") if request else ""
    if not root:
        return target_url

    ref = (referer_url or "").strip() or (HDFILMCEHENNEMI_EMBED_DOMAIN + "/")
    return (
        f"{root}/hdf/playlist"
        f"?url={quote(target_url, safe='')}"
        f"&ref={quote(ref, safe='')}"
    )


def hdfilmizleto_proxy_url(target_url, referer_url):
    if not is_http_url(target_url) or ".m3u8" not in (target_url or "").lower():
        return target_url
    if not is_hdfilmizleto_stream_host(target_url):
        return target_url

    root = request.url_root.rstrip("/") if request else ""
    if not root:
        return target_url

    ref = (referer_url or "").strip() or "https://vidrame.pro/"
    return (
        f"{root}/hdfilmizleto/playlist.m3u8"
        f"?url={quote(target_url, safe='')}"
        f"&ref={quote(ref, safe='')}"
    )


def rewrite_hdfilmcehennemi_playlist(content, playlist_url, referer_url):
    def rewrite_playlist_reference(value):
        absolute = normalize_url(urljoin(playlist_url, value), playlist_url)
        if is_probable_hls_manifest_url(absolute) and is_hdfilmcehennemi_stream_host(absolute):
            return hdfilmcehennemi_proxy_url(absolute, referer_url)
        return absolute if is_http_url(absolute) else value

    out = []
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            out.append(raw_line)
            continue

        if line.startswith("#"):
            if "URI=" in line:
                rewritten_line = re.sub(
                    r"""URI=(["'])([^"']+)(["'])""",
                    lambda m: f"URI={m.group(1)}{rewrite_playlist_reference(m.group(2))}{m.group(3)}",
                    raw_line,
                )
                out.append(rewritten_line)
            else:
                out.append(raw_line)
            continue

        out.append(rewrite_playlist_reference(line))

    return "\n".join(out) + "\n"


def rewrite_hdfilmizleto_playlist(content, playlist_url, referer_url):
    def rewrite_playlist_reference(value):
        absolute = normalize_hdfilmizleto_media_url(normalize_url(urljoin(playlist_url, value), playlist_url))
        if is_http_url(absolute) and ".m3u8" in absolute.lower() and is_hdfilmizleto_stream_host(absolute):
            return hdfilmizleto_proxy_url(absolute, referer_url)
        return absolute if is_http_url(absolute) else value

    out = []
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            out.append(raw_line)
            continue

        if line.startswith("#"):
            if "URI=" in line:
                rewritten_line = re.sub(
                    r"""URI=(["'])([^"']+)(["'])""",
                    lambda m: f"URI={m.group(1)}{rewrite_playlist_reference(m.group(2))}{m.group(3)}",
                    raw_line,
                )
                out.append(rewritten_line)
            else:
                out.append(raw_line)
            continue

        out.append(rewrite_playlist_reference(line))

    return "\n".join(out) + "\n"


def rot13_text(value):
    out = []
    for ch in value or "":
        code = ord(ch)
        if 65 <= code <= 90:
            out.append(chr(65 + ((code - 65 + 13) % 26)))
        elif 97 <= code <= 122:
            out.append(chr(97 + ((code - 97 + 13) % 26)))
        else:
            out.append(ch)
    return "".join(out)


def decode_vidrame_stream_url(embed_html):
    m = RE_VIDRAME_DD.search(embed_html or "")
    if not m:
        return ""

    encoded = (m.group(1) or "").replace("-", "+").replace("_", "/")
    encoded += "=" * ((4 - len(encoded) % 4) % 4)
    try:
        raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    stream_url = normalize_url(rot13_text(raw)[::-1], "")
    stream_url = normalize_hdfilmizleto_media_url(stream_url)
    return stream_url if is_http_url(stream_url) else ""


def fix_hdfilmizleto_subtitles(subtitles):
    fixed = []
    for track in subtitles or []:
        if not isinstance(track, dict):
            continue
        item = dict(track)
        item["url"] = normalize_hdfilmizleto_media_url(item.get("url") or "")
        label_url = f"{item.get('label') or ''} {item.get('url') or ''}".lower()
        if "english" in label_url or "ingiliz" in label_url:
            item["language"] = "en"
        elif "turkish" in label_url or "forced" in label_url or "turk" in label_url:
            item["language"] = "tr"
        if item.get("url"):
            fixed.append(item)
    return fixed


def decode_rapidvid_stream_url(embed_html, embed_url):
    for raw in RE_RAPIDVID_AV_FILE.findall(embed_html or ""):
        stream_url = normalize_url(decode_rapidvid_av_value(raw), embed_url)
        if is_http_url(stream_url) and is_fullhdfilmizlesene_stream_host(stream_url):
            return stream_url
    return ""


def resolve_rapidvid_embed_detail(embed_url, upstream_headers, embed_html=None):
    referer = upstream_headers.get("Referer") or FULLHDFILMIZLESENE_BASE_DOMAIN + "/"
    embed_origin = origin_of(embed_url) or "https://rapidvid.net"
    headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Accept": upstream_headers.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": upstream_headers.get("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"),
        "Referer": referer,
        "Origin": origin_of(referer) or FULLHDFILMIZLESENE_BASE_DOMAIN,
        "Cache-Control": "no-cache",
    }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return {}

    stream_url = decode_rapidvid_stream_url(html, embed_url)
    if not stream_url:
        cands = extract_m3u8_candidates(html, embed_url)
        stream_url = cands[0] if cands else ""
    if not stream_url:
        return {}

    subtitles = extract_jwplayer_subtitles(html, embed_url)
    return {
        "url": stream_url,
        "headers": make_playback_headers(stream_url, referer_hint=embed_url, origin_hint=embed_origin),
        "subtitles": subtitles,
    }


def decode_vidmoxy_stream_candidates(embed_html, embed_url):
    urls = []

    for u in extract_m3u8_candidates(embed_html, embed_url):
        urls.append(u)

    for u in extract_jwplayer_file_candidates(embed_html, embed_url):
        urls.append(u)

    for match in RE_VIDMOXY_ENCODED_VALUE.findall(embed_html or ""):
        raw = match[0] or match[1] or ""
        variants = dedup_keep_order([
            raw,
            decode_js_string_literal(raw),
            decode_js_string_literal(raw).replace("\\\\", "\\"),
            decode_js_string_literal(raw).replace("\\", ""),
        ])
        for variant in variants:
            decoded = decode_rapidvid_av_value(variant)
            u = normalize_url(decoded, embed_url)
            if is_http_url(u):
                urls.append(u)

    return dedup_keep_order(urls)


def resolve_vidmoxy_embed_detail(embed_url, upstream_headers, embed_html=None):
    embed_origin = origin_of(embed_url) or "https://vidmoxy.net"
    headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Accept": upstream_headers.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": upstream_headers.get("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"),
        "Referer": upstream_headers.get("Referer", FULLHDFILMIZLESENE_BASE_DOMAIN + "/"),
        "Origin": upstream_headers.get("Origin", embed_origin),
        "Cache-Control": "no-cache",
    }

    known_stream_url = vidmoxy_known_stream_url(embed_url)
    if known_stream_url:
        known_stream_url = normalize_vidmoxy_stream_url(known_stream_url)
        return {
            "url": known_stream_url,
            "headers": make_playback_headers(known_stream_url, referer_hint=embed_url, origin_hint=embed_origin),
            "subtitles": [],
        }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return {}

    for stream_url in decode_vidmoxy_stream_candidates(html, embed_url):
        stream_url = normalize_vidmoxy_stream_url(stream_url)
        if not is_fullhdfilmizlesene_stream_host(stream_url) and not is_probable_hls_manifest_url(stream_url):
            continue
        subtitles = extract_jwplayer_subtitles(html, embed_url)
        return {
            "url": stream_url,
            "headers": make_playback_headers(stream_url, referer_hint=embed_url, origin_hint=embed_origin),
            "subtitles": subtitles,
        }

    return {}


def parse_player_configs(embed_html):
    m = RE_PLAYER_CONFIGS.search(embed_html or "")
    if not m:
        return {}
    raw = (m.group(1) or "").replace("\\/", "/")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def sorted_sobreat_playlist_items(items):
    if not isinstance(items, list):
        return []

    normalized = [item for item in items if isinstance(item, dict) and str(item.get("file") or "").strip()]

    def rank(item):
        title = str(item.get("title") or "").lower()
        if "dublaj" in title or "turkce" in title or "türkçe" in title:
            return 0
        if "altyaz" in title or "sub" in title:
            return 1
        return 2

    return sorted(normalized, key=rank)


def sobreat_playlist_url(file_value, embed_url):
    value = str(file_value or "").strip()
    if not value:
        return ""
    if value.startswith("~") or value.startswith("#"):
        value = value[1:]
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return normalize_url(f"/playlist/{value}.txt", embed_url)


def resolve_sobreatsesuyp_embed_detail(embed_url, upstream_headers, embed_html=None, trace=None):
    embed_origin = origin_of(embed_url) or "https://sobreatsesuyp.com"
    referer = upstream_headers.get("Referer") or FULLHDFILMIZLESENE_BASE_DOMAIN + "/"
    headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Accept": upstream_headers.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": upstream_headers.get("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"),
        "Referer": referer,
        "Origin": origin_of(referer) or FULLHDFILMIZLESENE_BASE_DOMAIN,
        "Cache-Control": "no-cache",
    }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        if trace is not None:
            trace.append({"stage": "sobreat_embed", "url": embed_url, "ok": False, "reason": "empty_html"})
        return {}

    config = parse_player_configs(html)
    playlist_file = str(config.get("file") or "").strip()
    csrf_token = str(config.get("key") or "").strip()
    if trace is not None:
        trace.append({
            "stage": "sobreat_config",
            "url": embed_url,
            "ok": bool(playlist_file),
            "html_len": len(html),
            "has_key": bool(csrf_token),
            "playlist_file": playlist_file[:160],
        })
    if not playlist_file:
        return {}

    playlist_url = normalize_url(playlist_file, embed_url)
    playlist_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json,text/plain,*/*",
        "Referer": embed_url,
        "Origin": embed_origin,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache",
    }
    if csrf_token:
        playlist_headers["X-CSRF-TOKEN"] = csrf_token

    playlist_text = fetch_text(playlist_url, headers=playlist_headers, timeout_sec=DEFAULT_TIMEOUT)
    if not playlist_text:
        if trace is not None:
            trace.append({"stage": "sobreat_playlist", "url": playlist_url, "ok": False, "reason": "empty_playlist"})
        return {}

    try:
        playlist_payload = json.loads(playlist_text)
    except Exception:
        playlist_payload = []
    if trace is not None:
        trace.append({
            "stage": "sobreat_playlist",
            "url": playlist_url,
            "ok": bool(playlist_payload),
            "text_len": len(playlist_text),
            "items": len(playlist_payload) if isinstance(playlist_payload, list) else 0,
        })

    for item in sorted_sobreat_playlist_items(playlist_payload):
        stream_lookup = sobreat_playlist_url(item.get("file"), embed_url)
        if not stream_lookup:
            continue

        body = fetch_or_post_text(stream_lookup, headers=playlist_headers, timeout_sec=DEFAULT_TIMEOUT)
        stream_url = extract_url_from_jsonish(body, base_url=stream_lookup)
        if not stream_url and body.strip().startswith(("http://", "https://")):
            stream_url = normalize_url(body.strip(), stream_lookup)
        if trace is not None:
            trace.append({
                "stage": "sobreat_stream",
                "title": str(item.get("title") or ""),
                "url": stream_lookup[:220],
                "ok": bool(stream_url),
                "body_len": len(body or ""),
                "body_head": (body or "")[:140],
            })
        if not stream_url:
            continue

        return {
            "url": stream_url,
            "headers": make_playback_headers(stream_url, referer_hint=embed_url, origin_hint=embed_origin),
            "subtitles": [],
        }

    return {}


def resolve_vidrame_embed_detail(embed_url, upstream_headers, embed_html=""):
    embed_origin = origin_of(embed_url) or "https://vidrame.pro"
    headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Accept": upstream_headers.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": upstream_headers.get("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"),
        "Referer": upstream_headers.get("Referer", HDFILMIZLETO_BASE_DOMAIN + "/"),
        "Origin": upstream_headers.get("Origin", embed_origin),
        "Cache-Control": "no-cache",
    }

    html = embed_html or fetch_text(embed_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return {}

    stream_url = decode_vidrame_stream_url(html)
    if not stream_url:
        cands = extract_m3u8_candidates(html, embed_url)
        stream_url = normalize_hdfilmizleto_media_url(cands[0]) if cands else ""
    if not stream_url:
        return {}

    subtitles = fix_hdfilmizleto_subtitles(extract_jwplayer_subtitles(html, embed_url))
    return {
        "url": hdfilmizleto_proxy_url(stream_url, embed_url),
        "headers": {},
        "subtitles": subtitles,
    }


def decode_hdfilmcehennemi_stream_url(embed_html):
    m = RE_HDFILMCEHENNEMI_DECODER.search(embed_html or "")
    if not m:
        return ""

    try:
        modulus = int(m.group(2))
        offset = int(m.group(3))
    except Exception:
        return ""

    parts_blob = m.group(5) or ""
    parts = []
    for part in re.findall(r"""["']((?:\\.|[^"'\\])*)["']""", parts_blob):
        parts.append(decode_js_string_literal(part).replace("\\/", "/"))

    value = "".join(parts)
    if not value:
        return ""

    try:
        raw = base64.b64decode(value[::-1]).decode("latin-1", errors="ignore")
    except Exception:
        return ""

    mixed = rot13_text(raw)
    decoded = []
    for idx, ch in enumerate(mixed):
        decoded.append(chr((ord(ch) - (modulus % (idx + offset)) + 256) % 256))

    stream_url = normalize_url("".join(decoded), "")
    return stream_url if is_http_url(stream_url) else ""


def extract_hdfilmcehennemi_content_url(embed_html, embed_url):
    for raw in re.findall(r'''"contentUrl"\s*:\s*"([^"]+)"''', embed_html or "", re.IGNORECASE):
        url = normalize_url(raw, embed_url)
        if is_http_url(url) and is_probable_hls_manifest_url(url):
            return url
    return ""


def resolve_hdfilmcehennemi_embed_detail(embed_url, upstream_headers, embed_html=None):
    embed_origin = origin_of(embed_url) or "https://hdfilmcehennemi.mobi"
    embed_headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Referer": upstream_headers.get("Referer", embed_origin + "/"),
        "Origin": upstream_headers.get("Origin", embed_origin),
    }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, embed_headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return {}

    subtitles = merge_subtitle_tracks(
        extract_jwplayer_subtitles(html, embed_url),
        extract_playerjs_subtitles(html, embed_url),
    )

    stream_url = decode_hdfilmcehennemi_stream_url(html)
    if not stream_url:
        stream_url = extract_hdfilmcehennemi_content_url(html, embed_url)

    if stream_url and is_probable_hls_manifest_url(stream_url):
        playback_url = hdfilmcehennemi_proxy_url(stream_url, embed_url)
        return {
            "url": playback_url,
            "headers": make_playback_headers(stream_url, referer_hint=embed_url, origin_hint=embed_origin),
            "subtitles": subtitles,
        }

    return {}


def resolve_filmmakinesi_embed_detail(embed_url, upstream_headers, embed_html=None):
    embed_origin = origin_of(embed_url) or "https://closeload.filmmakinesi.to"
    embed_headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Referer": upstream_headers.get("Referer", FILMMAKINESI_BASE_DOMAIN + "/"),
        "Origin": upstream_headers.get("Origin", embed_origin),
    }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, embed_headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return {}

    subtitles = merge_subtitle_tracks(
        extract_jwplayer_subtitles(html, embed_url),
        extract_playerjs_subtitles(html, embed_url),
    )

    stream_url = decode_hdfilmcehennemi_stream_url(html)
    if not stream_url:
        stream_url = extract_hdfilmcehennemi_content_url(html, embed_url)

    if stream_url and is_probable_hls_manifest_url(stream_url):
        playback_url = hdfilmcehennemi_proxy_url(stream_url, embed_url)
        return {
            "url": playback_url,
            "headers": make_playback_headers(stream_url, referer_hint=embed_url, origin_hint=embed_origin),
            "subtitles": subtitles,
        }

    return {}


def resolve_hdfilmcehennemi_known_embed_detail(page_url, upstream_headers):
    slug = hdfilmcehennemi_slug_from_url(page_url)
    embed_id = hdfilmcehennemi_embed_id_for_slug(slug)
    if not embed_id:
        return {}

    embed_url = hdfilmcehennemi_embed_url(embed_id)
    if not embed_url:
        return {}

    return resolve_hdfilmcehennemi_embed_detail(embed_url, upstream_headers)


def resolve_hlszone_embed_detail(embed_url, upstream_headers, embed_html=None):
    video_id = hlszone_video_id(embed_url)
    if not video_id:
        return {}

    embed_origin = origin_of(embed_url) or "https://hlszone.com"
    embed_headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Referer": upstream_headers.get("Referer", embed_origin + "/"),
        "Origin": embed_origin,
    }

    html = embed_html
    if html is None:
        html = fetch_text(embed_url, embed_headers, timeout_sec=DEFAULT_TIMEOUT)

    subtitles = extract_playerjs_subtitles(html or "", embed_url)

    api_url = f"{embed_origin}/player/index.php?data={video_id}&do=getVideo"
    parent_ref = upstream_headers.get("Referer") or embed_headers["Referer"]
    post_headers = {
        "User-Agent": embed_headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": embed_url,
        "Origin": embed_origin,
    }

    try:
        response = SESSION.post(
            api_url,
            headers=post_headers,
            data={"hash": video_id, "r": parent_ref},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return {}
        body = response.text or ""
        payload = response.json()
    except Exception:
        return {}

    stream_url = ""
    if isinstance(payload, dict):
        for key in ("securedLink", "url", "stream", "file", "videoSource"):
            raw = payload.get(key)
            if raw:
                candidate = normalize_url(str(raw), base_url=api_url)
                if is_http_url(candidate):
                    stream_url = candidate
                    break

    if not stream_url:
        stream_url = extract_url_from_jsonish(body, base_url=api_url)

    if stream_url and ".m3u8" in stream_url.lower():
        return {"url": stream_url, "subtitles": subtitles}

    return {}


def resolve_playerjs_embed_detail(embed_url, upstream_headers):
    embed_origin = origin_of(embed_url)
    embed_headers = {
        "User-Agent": upstream_headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
        "Referer": upstream_headers.get("Referer", embed_origin + "/" if embed_origin else BASE_HEADERS["Referer"]),
        "Origin": upstream_headers.get("Origin", embed_origin if embed_origin else BASE_HEADERS["Origin"]),
    }

    embed_html = fetch_text(embed_url, embed_headers, timeout_sec=DEFAULT_TIMEOUT)
    if not embed_html:
        return {}

    subtitles = extract_playerjs_subtitles(embed_html, embed_url)

    # direct m3u8 in embed HTML
    direct = extract_m3u8_candidates(embed_html, embed_url)
    if direct:
        return {"url": direct[0], "subtitles": subtitles}

    dl_url = extract_playerjs_dl_url(embed_html, embed_url)
    if not dl_url or not is_http_url(dl_url):
        return {}

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
            return {"url": u, "subtitles": subtitles}

    return {}


def resolve_playerjs_embed(embed_url, upstream_headers):
    detail = resolve_playerjs_embed_detail(embed_url, upstream_headers)
    if detail:
        return detail.get("url") or ""
    return ""


def resolve_from_page_detail(page_url, headers, depth=0, max_depth=3, trace=None):
    if is_vidmoxy_embed_url(page_url):
        fast = resolve_vidmoxy_embed_detail(page_url, headers, embed_html="")
        if fast.get("url"):
            if trace is not None:
                trace.append({
                    "stage": "vidmoxy_known",
                    "depth": depth,
                    "url": page_url,
                    "ok": True,
                    "stream_host": urlparse(fast.get("url") or "").hostname or "",
                })
            return fast

    hdf_known = resolve_hdfilmcehennemi_known_embed_detail(page_url, headers)
    if hdf_known.get("url"):
        return hdf_known

    html, effective_page_url = fetch_text_with_final_url(page_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        if trace is not None:
            trace.append({"stage": "page_fetch", "depth": depth, "url": page_url, "ok": False, "reason": "empty_html"})
        return {}
    effective_page_url = effective_page_url or page_url
    if trace is not None:
        trace.append({
            "stage": "page_fetch",
            "depth": depth,
            "url": page_url,
            "ok": True,
            "effective": effective_page_url,
            "html_len": len(html),
        })

    if is_hlszone_embed_url(effective_page_url):
        fast = resolve_hlszone_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_hdfilmcehennemi_embed_url(effective_page_url):
        fast = resolve_hdfilmcehennemi_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_filmmakinesi_embed_url(effective_page_url):
        fast = resolve_filmmakinesi_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_vidrame_embed_url(effective_page_url):
        fast = resolve_vidrame_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_vidmoxy_embed_url(effective_page_url):
        fast = resolve_vidmoxy_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_rapidvid_embed_url(effective_page_url):
        fast = resolve_rapidvid_embed_detail(effective_page_url, headers, embed_html=html)
        if fast.get("url"):
            return fast

    if is_sobreatsesuyp_embed_url(effective_page_url):
        fast = resolve_sobreatsesuyp_embed_detail(effective_page_url, headers, embed_html=html, trace=trace)
        if fast.get("url"):
            return fast

    cands = extract_m3u8_candidates(html, effective_page_url)
    if cands:
        return {"url": cands[0], "subtitles": []}

    if depth >= max_depth:
        return {}

    embeds = extract_iframe_candidates(html, effective_page_url)
    if trace is not None:
        trace.append({
            "stage": "embeds",
            "depth": depth,
            "url": effective_page_url,
            "count": len(embeds),
            "first": embeds[:6],
        })
    for u in embeds[:8]:
        low = u.lower()

        if is_hlszone_embed_url(u):
            fast = resolve_hlszone_embed_detail(u, headers)
            if fast.get("url"):
                return fast

        if is_hdfilmcehennemi_embed_url(u):
            fast = resolve_hdfilmcehennemi_embed_detail(u, headers)
            if fast.get("url"):
                return fast

        if is_filmmakinesi_embed_url(u):
            fast = resolve_filmmakinesi_embed_detail(u, {
                "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
                "Referer": effective_page_url,
                "Origin": origin_of(effective_page_url) or headers.get("Origin", BASE_HEADERS["Origin"]),
            })
            if fast.get("url"):
                return fast

        if is_vidrame_embed_url(u):
            fast = resolve_vidrame_embed_detail(u, {
                "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
                "Referer": effective_page_url,
                "Origin": origin_of(effective_page_url) or headers.get("Origin", BASE_HEADERS["Origin"]),
            })
            if fast.get("url"):
                return fast

        if is_vidmoxy_embed_url(u):
            fast = resolve_vidmoxy_embed_detail(u, {
                "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
                "Referer": effective_page_url,
                "Origin": origin_of(effective_page_url) or headers.get("Origin", BASE_HEADERS["Origin"]),
            })
            if fast.get("url"):
                return fast

        if is_rapidvid_embed_url(u):
            fast = resolve_rapidvid_embed_detail(u, {
                "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
                "Referer": effective_page_url,
                "Origin": origin_of(effective_page_url) or headers.get("Origin", BASE_HEADERS["Origin"]),
            })
            if fast.get("url"):
                return fast

        if is_sobreatsesuyp_embed_url(u):
            fast = resolve_sobreatsesuyp_embed_detail(u, {
                "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
                "Referer": effective_page_url,
                "Origin": origin_of(effective_page_url) or headers.get("Origin", BASE_HEADERS["Origin"]),
            }, trace=trace)
            if fast.get("url"):
                return fast

        # playerjs style embed (filmhane source)
        if "embed" in low or "/dl?op=get_stream" in low:
            fast = resolve_playerjs_embed_detail(u, headers)
            if fast.get("url"):
                return fast

        next_origin = origin_of(u)
        current_origin = origin_of(effective_page_url)
        next_headers = {
            "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
            "Referer": effective_page_url,
            "Origin": current_origin if current_origin else (next_origin if next_origin else headers.get("Origin", BASE_HEADERS["Origin"])),
        }
        found = resolve_from_page_detail(u, next_headers, depth + 1, max_depth, trace=trace)
        if found.get("url"):
            return found

    return {}


def resolve_from_page(page_url, headers, depth=0, max_depth=3):
    detail = resolve_from_page_detail(page_url, headers, depth=depth, max_depth=max_depth)
    return detail.get("url") or ""


def resolve_playerjs_embed_legacy(embed_url, upstream_headers):
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


def resolve_from_page_legacy(page_url, headers, depth=0, max_depth=3):
    html, effective_page_url = fetch_text_with_final_url(page_url, headers=headers, timeout_sec=DEFAULT_TIMEOUT)
    if not html:
        return ""
    effective_page_url = effective_page_url or page_url

    cands = extract_m3u8_candidates(html, effective_page_url)
    if cands:
        return cands[0]

    if depth >= max_depth:
        return ""

    embeds = extract_iframe_candidates(html, effective_page_url)
    for u in embeds[:8]:
        low = u.lower()

        # playerjs style embed (filmhane source)
        if "embed" in low or "/dl?op=get_stream" in low:
            fast = resolve_playerjs_embed(u, headers)
            if fast:
                return fast

        next_origin = origin_of(u)
        current_origin = origin_of(effective_page_url)
        next_headers = {
            "User-Agent": headers.get("User-Agent", BASE_HEADERS["User-Agent"]),
            "Referer": effective_page_url,
            "Origin": current_origin if current_origin else (next_origin if next_origin else headers.get("Origin", BASE_HEADERS["Origin"])),
        }
        found = resolve_from_page_legacy(u, next_headers, depth + 1, max_depth)
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
    base = FULLHD_BASE_DOMAIN
    return [
        f"{base}/dizi/{slug}/sezon-{sezon_no}/bolum-{bolum_no}/",
        f"{base}/dizi/{slug}/sezon-{sezon_no}/bolum-{bolum_no}",
        f"{base}/film/{slug}/",
        f"{base}/film/{slug}",
        f"{base}/{slug}/",
        f"{base}/{slug}",
    ]


def build_hdizipal_targets(slug, sezon_no, bolum_no):
    base = HDIZIPAL_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []

    return [
        f"{base}/dizi/{clean_slug}/{sezon_no}-sezon/{bolum_no}-bolum",
        f"{base}/dizi/{clean_slug}/sezon-{sezon_no}/bolum-{bolum_no}",
    ]


def build_hdfilmcehennemi_targets(slug, sezon_no, bolum_no):
    base = HDFILMCEHENNEMI_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []

    targets = []
    embed_id = hdfilmcehennemi_embed_id_for_slug(clean_slug)
    if embed_id:
        direct_embed = hdfilmcehennemi_embed_url(embed_id)
        if direct_embed:
            targets.append(direct_embed)

    targets.extend([
        f"{base}/{clean_slug}/",
        f"{base}/{clean_slug}",
        f"{base}/dizi/{clean_slug}/sezon-{sezon_no}/bolum-{bolum_no}/",
        f"{base}/dizi/{clean_slug}/sezon-{sezon_no}/bolum-{bolum_no}",
    ])
    return targets


def build_hdfilmizleto_targets(slug, sezon_no, bolum_no):
    base = HDFILMIZLETO_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []

    variants = [clean_slug]
    if not clean_slug.endswith("-izle"):
        variants.append(clean_slug + "-izle")
    if not clean_slug.endswith("-izle-hd-izle"):
        variants.append(clean_slug + "-izle-hd-izle")
    if not clean_slug.endswith("-hd-izle"):
        variants.append(clean_slug + "-hd-izle")

    targets = []
    for variant in dedup_keep_order(variants):
        targets.append(f"{base}/{variant}/")
        targets.append(f"{base}/{variant}")
        targets.append(f"{base}/dizi/{variant}/sezon-{sezon_no}/bolum-{bolum_no}/")
        targets.append(f"{base}/dizi/{variant}/sezon-{sezon_no}/bolum-{bolum_no}")
    return targets


def build_filmmakinesi_targets(slug, sezon_no, bolum_no):
    base = FILMMAKINESI_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []

    variants = [clean_slug]
    if not clean_slug.endswith("-izle"):
        variants.append(clean_slug + "-izle")

    targets = []
    for variant in dedup_keep_order(variants):
        targets.append(f"{base}/film/{variant}/")
        targets.append(f"{base}/film/{variant}")
        targets.append(f"{base}/dizi/{variant}/sezon-{sezon_no}/bolum-{bolum_no}/")
        targets.append(f"{base}/dizi/{variant}/sezon-{sezon_no}/bolum-{bolum_no}")
    return targets


def build_fullhdfilmizlesene_targets(slug, sezon_no, bolum_no):
    base = FULLHDFILMIZLESENE_BASE_DOMAIN
    clean_slug = (slug or "").strip().strip("/")
    if not clean_slug:
        return []

    variants = [clean_slug]
    if clean_slug.endswith("-izle"):
        variants.append(clean_slug[:-5])
    if not clean_slug.endswith("-2"):
        variants.append(clean_slug + "-2")

    targets = []
    for variant in dedup_keep_order([v.strip("-/") for v in variants if v.strip("-/")]):
        rapidvid_id = fullhdfilmizlesene_rapidvid_id_for_slug(variant)
        if rapidvid_id:
            targets.append(rapidvid_embed_url(rapidvid_id))
        for sobreat_id in fullhdfilmizlesene_sobreat_ids_for_slug(variant):
            targets.append(sobreat_embed_url(sobreat_id))
        targets.extend(fullhdfilmizlesene_vidmoxy_urls_for_slug(variant))
        targets.append(f"{base}/film/{variant}/")
        targets.append(f"{base}/film/{variant}")
    return dedup_keep_order(targets)


def source_order_for_yayin(slug_candidates):
    hint = (request.args.get("src") or request.args.get("source") or "").strip().lower()
    source_aliases = {
        # hdfilmcehennemi is intentionally kept out of the automatic/native pipeline:
        # its HLS media list points to JPEG-like segments that ExoPlayer cannot parse.
        "hdfilmizle": "hdfilmizleto",
        "hdfilmizle.to": "hdfilmizleto",
        "film-makinesi": "filmmakinesi",
        "filmmakinesi.to": "filmmakinesi",
        "fullhdfilmizlesene.life": "fullhdfilmizlesene",
        "fullhdfilmizlesene": "fullhdfilmizlesene",
    }
    hint = source_aliases.get(hint, hint)
    sources = ["filmhane", "fullhd", "hdizipal"]
    optional_sources = ["hdfilmizleto", "filmmakinesi", "fullhdfilmizlesene"]
    if hint in sources + optional_sources:
        return [hint] + [source for source in sources + optional_sources if source != hint]

    primary = (slug_candidates[0] if slug_candidates else "").lower()
    if (
        fullhdfilmizlesene_rapidvid_id_for_slug(primary)
        or fullhdfilmizlesene_sobreat_ids_for_slug(primary)
        or fullhdfilmizlesene_vidmoxy_urls_for_slug(primary)
    ):
        return ["fullhdfilmizlesene"] + sources + [source for source in optional_sources if source != "fullhdfilmizlesene"]

    if re.search(r"-fm\d+$", primary):
        return ["filmmakinesi"] + sources + [source for source in optional_sources if source != "filmmakinesi"]

    if primary.endswith("-izle"):
        return ["hdizipal", "filmhane", "fullhd"] + optional_sources

    return sources + optional_sources


def vaplayer_embed_url(media_type, imdb_id):
    kind = "tv" if media_type == "tv" else "movie"
    return f"https://brightpathsignals.com/embed/{kind}/{imdb_id}"


def choose_vaplayer_stream(streams):
    candidates = []
    for raw in streams or []:
        u = normalize_url(str(raw or ""), "")
        if is_http_url(u) and ".m3u8" in u.lower():
            candidates.append(u)

    if not candidates:
        return ""

    # Direct playback follows redirects without carrying custom Referer/Origin headers.
    # Prefer JustHD CDN URLs because they currently expose playlists without a referrer gate.
    for u in candidates:
        host = (urlparse(u).hostname or "").lower()
        if host.endswith("justhd.tv") or "/list.m3u8" in u.lower():
            return u

    return candidates[0]


def resolve_vaplayer_imdb(imdb_id, media_type, season_no="", episode_no=""):
    imdb_id = (imdb_id or "").strip()
    media_type = "tv" if media_type == "tv" else "movie"
    if not is_imdb_id(imdb_id):
        return ""

    params = {
        "imdb": imdb_id,
        "type": media_type,
    }
    if media_type == "tv":
        if not season_no or not episode_no:
            return ""
        params["season"] = str(season_no)
        params["episode"] = str(episode_no)

    embed_url = vaplayer_embed_url(media_type, imdb_id)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": embed_url,
        "Origin": "https://brightpathsignals.com",
    }

    try:
        response = SESSION.get(
            VAPLAYER_STREAM_API_URL,
            params=params,
            headers=headers,
            timeout=max(DEFAULT_TIMEOUT, 20),
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return ""
        payload = response.json()
    except Exception:
        return ""

    status_code = str(payload.get("status_code", "")).strip()
    if status_code and status_code != "200":
        return ""

    data = payload.get("data") if isinstance(payload, dict) else None
    streams = data.get("stream_urls") if isinstance(data, dict) else []
    return choose_vaplayer_stream(streams)


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
        "resolver": "playerjs-dl-fullhd-vaplayer-enabled",
        "cache_items": len(_CACHE),
        "api_key_enabled": bool(API_KEY),
    }


@app.route("/hdf/playlist", methods=["GET", "HEAD"])
def proxy_hdfilmcehennemi_playlist():
    target_url = unquote((request.args.get("url") or "").strip())
    referer_url = unquote((request.args.get("ref") or "").strip())
    if not is_http_url(target_url):
        return "Gecersiz URL", 400
    if not is_probable_hls_manifest_url(target_url) or not is_hdfilmcehennemi_stream_host(target_url):
        return "Kaynak desteklenmiyor.", 400

    embed_origin = origin_of(referer_url) or HDFILMCEHENNEMI_EMBED_DOMAIN
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
        "Referer": referer_url or (embed_origin + "/"),
        "Origin": embed_origin,
    }

    try:
        response = SESSION.get(
            target_url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return "Playlist alinamadi.", 502

    if response.status_code >= 400:
        return "Playlist bulunamadi.", response.status_code

    response.encoding = response.encoding or "utf-8"
    body = response.text or ""
    if not body.lstrip().startswith("#EXTM3U"):
        return "Gecersiz playlist.", 502

    final_url = response.url or target_url
    rewritten = rewrite_hdfilmcehennemi_playlist(body, final_url, referer_url)
    return Response(
        rewritten,
        status=200,
        headers={
            "Content-Type": "application/vnd.apple.mpegurl; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=0, s-maxage=15, stale-while-revalidate=60",
        },
    )


@app.route("/hdfilmizleto/playlist.m3u8", methods=["GET", "HEAD"])
def proxy_hdfilmizleto_playlist():
    target_url = unquote((request.args.get("url") or "").strip())
    referer_url = unquote((request.args.get("ref") or "").strip())
    if not is_http_url(target_url):
        return "Gecersiz URL", 400
    if ".m3u8" not in target_url.lower() or not is_hdfilmizleto_stream_host(target_url):
        return "Kaynak desteklenmiyor.", 400

    embed_origin = origin_of(referer_url) or "https://vidrame.pro"
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
        "Referer": referer_url or (embed_origin + "/"),
        "Origin": embed_origin,
    }

    try:
        response = SESSION.get(
            target_url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return "Playlist alinamadi.", 502

    if response.status_code >= 400:
        return "Playlist bulunamadi.", response.status_code

    response.encoding = response.encoding or "utf-8"
    body = response.text or ""
    if not body.lstrip().startswith("#EXTM3U"):
        return "Gecersiz playlist.", 502

    final_url = response.url or target_url
    rewritten = rewrite_hdfilmizleto_playlist(body, final_url, referer_url)
    return Response(
        rewritten,
        status=200,
        headers={
            "Content-Type": "application/vnd.apple.mpegurl; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=0, s-maxage=15, stale-while-revalidate=60",
        },
    )


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
        if isinstance(cached, dict):
            return respond_stream(
                cached.get("url") or "",
                playback_headers=cached.get("headers") or {},
                subtitles=cached.get("subtitles") or [],
                ttl=SHORT_TTL,
            )
        return redirect_light(cached, ttl=SHORT_TTL)

    dom = origin_of(target_url)
    headers = build_page_headers(target_url)

    detail = resolve_from_page_detail(target_url, headers=headers, max_depth=3)
    stream_url = detail.get("url") or ""
    if stream_url:
        playback_headers = detail.get("headers") or make_playback_headers(
            stream_url=stream_url,
            referer_hint=dom + "/" if dom else "",
            origin_hint=dom
        )
        payload = {
            "url": stream_url,
            "headers": playback_headers,
            "subtitles": detail.get("subtitles") or [],
        }
        cache_set(ck, payload, NORMAL_TTL)
        return respond_stream(
            stream_url,
            playback_headers=playback_headers,
            subtitles=payload["subtitles"],
            ttl=SHORT_TTL,
        )

    return "Video kaynagi bulunamadi.", 404


def respond_vaplayer_imdb(media_type, imdb_id, season_no="", episode_no=""):
    g = auth_guard()
    if g:
        return g

    imdb_id = (imdb_id or "").strip()
    media_type = "tv" if media_type == "tv" else "movie"
    if not is_imdb_id(imdb_id):
        return "Gecersiz IMDb ID", 400

    season_no = str(season_no or "").strip()
    episode_no = str(episode_no or "").strip()
    ck = f"imdb:{media_type}:{imdb_id}:{season_no}:{episode_no}"
    cached = cache_get(ck)
    if cached:
        stream_url = cached
    else:
        stream_url = resolve_vaplayer_imdb(imdb_id, media_type, season_no, episode_no)
        if not stream_url:
            return "Yayin bulunamadi.", 404
        cache_set(ck, stream_url, SHORT_TTL)

    embed_url = vaplayer_embed_url(media_type, imdb_id)
    playback_headers = make_playback_headers(
        stream_url=stream_url,
        referer_hint=embed_url,
        origin_hint="https://brightpathsignals.com",
    )
    return respond_stream(stream_url, playback_headers=playback_headers, ttl=SHORT_TTL)


@app.route("/imdb/movie/<imdb_id>", methods=["GET", "HEAD"])
def stream_imdb_movie(imdb_id):
    return respond_vaplayer_imdb("movie", imdb_id)


@app.route("/imdb/tv/<imdb_id>/<episode_token>", methods=["GET", "HEAD"])
def stream_imdb_tv_token(imdb_id, episode_token):
    season_no, episode_no = parse_episode_token(episode_token)
    return respond_vaplayer_imdb("tv", imdb_id, season_no, episode_no)


@app.route("/imdb/tv/<imdb_id>/<season_no>/<episode_no>", methods=["GET", "HEAD"])
def stream_imdb_tv_parts(imdb_id, season_no, episode_no):
    return respond_vaplayer_imdb("tv", imdb_id, season_no, episode_no)


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

    # Map varsa onu oncele. Sonra kaynak sirasini slug/source ipucuna gore ayarla.
    mapped_candidates = []
    filmhane_candidates = []
    fullhd_candidates = []
    hdizipal_candidates = []
    hdfilmcehennemi_candidates = []
    hdfilmizleto_candidates = []
    filmmakinesi_candidates = []
    fullhdfilmizlesene_candidates = []
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

    for slug in slug_candidates:
        hdfilmcehennemi_candidates.extend(build_hdfilmcehennemi_targets(slug, sezon_no, bolum_no))

    for slug in slug_candidates:
        hdfilmizleto_candidates.extend(build_hdfilmizleto_targets(slug, sezon_no, bolum_no))

    for slug in slug_candidates:
        filmmakinesi_candidates.extend(build_filmmakinesi_targets(slug, sezon_no, bolum_no))

    for slug in slug_candidates:
        fullhdfilmizlesene_candidates.extend(build_fullhdfilmizlesene_targets(slug, sezon_no, bolum_no))

    source_candidates = {
        "filmhane": filmhane_candidates,
        "fullhd": fullhd_candidates,
        "hdizipal": hdizipal_candidates,
        "hdfilmcehennemi": hdfilmcehennemi_candidates,
        "hdfilmizleto": hdfilmizleto_candidates,
        "filmmakinesi": filmmakinesi_candidates,
        "fullhdfilmizlesene": fullhdfilmizlesene_candidates,
    }
    source_order = source_order_for_yayin(slug_candidates)
    source_lookup = {}
    for source_name, source_list in source_candidates.items():
        for item in source_list:
            source_lookup.setdefault(item, source_name)
    for item in mapped_candidates:
        source_lookup.setdefault(item, "mapped")

    candidates = list(mapped_candidates)
    for source in source_order:
        candidates.extend(source_candidates.get(source, []))

    # dedup keep order
    ordered_candidates = []
    seen_candidates = set()
    for c in candidates:
        if c in seen_candidates:
            continue
        seen_candidates.add(c)
        ordered_candidates.append(c)

    # token links carry a long expiry, but keep the in-memory cache modest.
    ck = f"yayin:{dizi}:{bolum}"
    debug_enabled = wants_debug()
    debug_attempts = []
    cached = cache_get(ck)
    if cached and not debug_enabled:
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
        trace = []
        started = time.time()
        detail = resolve_from_page_detail(target_page, headers=headers, max_depth=3, trace=trace if debug_enabled else None)
        stream_url = detail.get("url") or ""
        if debug_enabled:
            debug_attempts.append({
                "source": source_lookup.get(target_page, "unknown"),
                "target": target_page,
                "ok": bool(stream_url),
                "elapsed_ms": int((time.time() - started) * 1000),
                "stream_host": (urlparse(stream_url).hostname or "") if stream_url else "",
                "trace": trace[-12:],
            })
        if stream_url:
            playback_headers = detail.get("headers") or make_playback_headers(stream_url=stream_url)
            payload = {
                "url": stream_url,
                "headers": playback_headers,
                "subtitles": detail.get("subtitles") or [],
            }
            cache_set(ck, payload, STREAM_CACHE_TTL)
            if debug_enabled:
                return json_response({
                    "ok": True,
                    "version": VERSION,
                    "slugCandidates": slug_candidates,
                    "sourceOrder": source_order,
                    "candidateCount": len(ordered_candidates),
                    "url": client_playback_url(stabilize_stream_url(stream_url)),
                    "headers": playback_headers,
                    "subtitles": payload["subtitles"],
                    "attempts": debug_attempts,
                })
            return respond_stream(
                stream_url,
                playback_headers=playback_headers,
                subtitles=payload["subtitles"],
                ttl=SHORT_TTL,
            )

    if debug_enabled:
        return json_response({
            "ok": False,
            "version": VERSION,
            "slugCandidates": slug_candidates,
            "sourceOrder": source_order,
            "candidateCount": len(ordered_candidates),
            "attempts": debug_attempts,
        }, status=404)

    return "Yayin bulunamadi.", 404


if __name__ == "__main__":
    app.run(debug=True)
