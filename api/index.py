from flask import Flask, Response, request
import os
import re
import time
from threading import Lock
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

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

SESSION = requests.Session()

_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_MAX = 4000


RE_M3U8_DIRECT = re.compile(r"https?://[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_ESCAPED = re.compile(r"https?:\\/\\/[^\"'<>\s]+\.m3u8[^\"'<>\s]*", re.IGNORECASE)
RE_M3U8_FILESRC = re.compile(r"(?:file|src)\s*[:=]\s*[\"']([^\"']+\.m3u8[^\"']*)[\"']", re.IGNORECASE)
RE_DAION = re.compile(r"[\"'](https?:?\\?/\\?/[^\s\"'<>]*?daioncdn[^\s\"'<>]*?\.m3u8[^\s\"'<>]*?)[\"']", re.IGNORECASE)
RE_IFRAME = re.compile(r"<iframe[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
RE_PLAYERJS_FETCH = re.compile(
    r"""fetch\(\s*["']([^"']*?/dl\?op=get_stream[^"']*)["']\s*\)""",
    re.IGNORECASE,
)
RE_JS_COOKIE = re.compile(
    r"""\$\.cookie\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]*)['"]""",
    re.IGNORECASE,
)


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


def origin_of(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


def is_http_url(value: str) -> bool:
    try:
