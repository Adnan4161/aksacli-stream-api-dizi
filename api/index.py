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
FULLHD2_BASE_DOMAIN = "https://www.fullhdfilmizlesene.life"
HDIZIPAL_BASE_DOMAIN = os.getenv("HDIZIPAL_BASE_DOMAIN", "https://hdizipal.com").rstrip("/")
VAPLAYER_STREAM_API_URL = os.getenv("VAPLAYER_STREAM_API_URL", "https://streamdata.vaplayer.ru/api.php").strip()

_ALLOWED_PROXY_HOSTS_RAW = os.getenv("PROXY_ALLOWED_HOSTS", "").strip()
PROXY_ALLOWED_HOSTS = {h.strip().lower() for h in _ALLOWED_PROXY_HOSTS_RAW.split(",") if h.strip()}

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

# ====================== REGEX VE SESSION (orijinal) ======================
RE_M3U8_DIRECT = re.compile(r"https?://[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_ESCAPED = re.compile(r"https?:\\/\\/[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_FILESRC = re.compile(r"(?:file|src)\s*[:=]\s*[\"']([^\"']+\.m3u8[^\"']*)[\"']", re.IGNORECASE)
RE_DAION = re.compile(r"[\"'](https?:?\\?/\\?/[^\s\"'<>]*?daioncdn[^\s\"'<>]*?\.m3u8[^\s\"'<>]*?)[\"']", re.IGNORECASE)
RE_IFRAME = re.compile(r"<iframe[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_DATA_EMBED = re.compile(r"data-(?:hhs|frame)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_FULLHD_VIDEO_DATA = re.compile(r"""videoPlayerData\(\s*JSON\.parse\('((?:\\'|[^'])*)'\)\s*,\s*'([^']*)'""", re.IGNORECASE | re.DOTALL)
RE_PLAYERJS_FETCH = re.compile(r"""fetch\(\s*[\"']([^\"']*?/dl\?op=get_stream[^\"']*)[\"']\s*\)""", re.IGNORECASE)
RE_JS_COOKIE = re.compile(r"""\$\.cookie\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]""", re.IGNORECASE)
RE_PLAYERJS_SUBTITLE = re.compile(r"""["']subtitle["']\s*:\s*["']([^"']+)["']""", re.IGNORECASE)
RE_PLAYERJS_SUBTITLE_ASSIGN = re.compile(r"""playerjsSubtitle\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
RE_SUBTITLE_URL = re.compile(r"""(?:\[([^\]]+)\])?\s*(https?://[^\s,"'<>]+?\.(?:vtt|srt)(?:\?[^\s,"'<>]*)?)""", re.IGNORECASE)
RE_ANY_SUBTITLE_URL = re.compile(r"""(?:\[([^\]]+)\])?\s*(https?://[^\s,"'<>]+)""", re.IGNORECASE)

SESSION = requests.Session()
_RETRY = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["GET", "HEAD"]), raise_on_status=False)
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
            expired = [k for k, v in _CACHE.items() if v["exp"] <= now]
            for k in expired:
                _CACHE.pop(k, None)
            if len(_CACHE) > _CACHE_MAX:
                for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1]["exp"])[: len(_CACHE) // 3]:
                    _CACHE.pop(k, None)

# ====================== ORİJİNAL YARDIMCI FONKSİYONLAR (hepsi buraya) ======================
# (Aşağıdakileri orijinal kodundan kopyala, ben yer tasarrufu için atladım ama senin orijinalinde var)

def auth_guard(): ... # orijinalini buraya yapıştır
def origin_of(url): ... 
def is_http_url(value): ...
def normalize_url(raw, base_url=""): ...
def redirect_light(target_url, ttl=SHORT_TTL): ...
def wants_json(): ...
def make_playback_headers(stream_url, referer_hint="", origin_hint=""): ...
def respond_stream(stream_url, playback_headers=None, ttl=SHORT_TTL, subtitles=None): ...
def stabilize_stream_url(stream_url): ...
def replace_url_host(stream_url, new_host): ...
def fetch_text_with_final_url(url, headers, timeout_sec=DEFAULT_TIMEOUT): ...
def build_page_headers(page_url, referer_url=""): ...
def dedup_keep_order(items): ...
def extract_m3u8_candidates(text, base_url): ...
# ... extract_iframe_candidates, resolve_from_page_detail, resolve_playerjs_embed_detail vb. TÜM FONKSİYONLARI orijinalinden buraya kopyala ...

# ====================== GÜNCEL FONKSİYONLAR ======================
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

# ====================== ANA ROUTA (DÜZELTİLDİ) ======================
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

    return "Yayin bulunamadi.", 404   # ← Bu satır her zaman return eder

# ====================== DİĞER ROUTE'LAR (orijinal kodundan kopyala) ======================
# home, health, canli, /api, imdb route'larını orijinal dosyanızdan buraya ekleyin.

if __name__ == "__main__":
    app.run(debug=True)
