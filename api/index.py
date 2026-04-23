from flask import Flask, redirect, Response, request
import requests
import re
from urllib.parse import urlparse, urljoin, urlencode

app = Flask(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr",
}


# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------

def _origin(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}"


def _is_http_url(u: str) -> bool:
    return isinstance(u, str) and (u.startswith("http://") or u.startswith("https://"))


def _clean_url(raw: str):
    if not raw:
        return None
    return raw.replace("\\/", "/").replace("\\\\", "").strip().strip('"').strip("'")


def _redirect_no_cache(url: str):
    r = redirect(url, code=302)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    r.headers["Pragma"] = "no-cache"
    return r


def _extract_m3u8_from_text(text: str):
    if not text:
        return None

    patterns = [
        r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        r'(?:file|src)\s*[:=]\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"'
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return _clean_url(m.group(1))

    m = re.search(r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', text, re.IGNORECASE)
    if m:
        return _clean_url(m.group(0))

    return None


def _extract_cookie_value(html: str, key: str):
    m = re.search(rf"\.cookie\('{re.escape(key)}',\s*'([^']+)'", html, re.IGNORECASE)
    return m.group(1) if m else None


def _parse_episode(bolum: str):
    token = (bolum or "").strip()

    # /yayin/asylum/1 -> S1B1 gibi davran
    if token.isdigit():
        return 1, int(token)

    s_match = re.search(r"[sS](\d+)", token)
    b_match = re.search(r"[bB](\d+)", token)

    if s_match and b_match:
        return int(s_match.group(1)), int(b_match.group(1))
    if b_match:
        return 1, int(b_match.group(1))

    num = re.search(r"(\d+)", token)
    if num:
        return 1, int(num.group(1))

    return 1, 1


def _build_proxy_url(stream_url: str, referer: str):
    if not referer or not _is_http_url(referer):
        referer = _origin(stream_url) + "/"
    qs = urlencode({"u": stream_url, "r": referer})
    return f"/hls/proxy?{qs}"


def _rewrite_m3u8(playlist_text: str, base_url: str, referer: str):
    out = []

    for raw_line in playlist_text.splitlines():
        line = raw_line.strip()

        if not line:
            out.append(raw_line)
            continue

        if line.startswith("#"):
            # URI="..." içeren satırlar (KEY, I-FRAME vs)
            def repl(m):
                u = m.group(1).strip()
                abs_u = urljoin(base_url, u)
                return f'URI="{_build_proxy_url(abs_u, referer)}"'

            rewritten = re.sub(r'URI="([^"]+)"', repl, raw_line)
            out.append(rewritten)
            continue

        abs_url = urljoin(base_url, line)
        out.append(_build_proxy_url(abs_url, referer))

    return "\n".join(out) + "\n"


# -----------------------------------------------------------
# PlayerJS / iframe resolver
# -----------------------------------------------------------

def _resolve_playerjs_embed(embed_url: str, page_url: str, session: requests.Session):
    page_origin = _origin(page_url)
    embed_origin = _origin(embed_url)

    embed_headers = {
        "User-Agent": USER_AGENT,
        "Referer": page_url,
        "Origin": page_origin
    }

    embed_res = session.get(embed_url, headers=embed_headers, timeout=12)
    embed_html = embed_res.text

    # Embed içinde direkt m3u8 varsa
    direct = _extract_m3u8_from_text(embed_html)
    if direct:
        return direct, embed_origin + "/"

    # fetch('/dl?op=get_stream&...')
    fetch_match = re.search(
        r"fetch\(\s*['\"]([^'\"]*op=get_stream[^'\"]*)['\"]\s*\)",
        embed_html,
        re.IGNORECASE
    )
    if not fetch_match:
        return None

    dl_url = urljoin(embed_url, fetch_match.group(1))

    cookies = {}
    for k in ("file_id", "aff", "ref_url"):
        v = _extract_cookie_value(embed_html, k)
        if v:
            cookies[k] = v

    dl_headers = {
        "User-Agent": USER_AGENT,
        "Referer": embed_url,
        "Origin": embed_origin,
        "Accept": "application/json, text/plain, */*"
    }

    dl_res = session.get(dl_url, headers=dl_headers, cookies=(cookies or None), timeout=12)

    try:
        data = dl_res.json()
        if isinstance(data, dict) and data.get("url"):
            return _clean_url(data["url"]), embed_origin + "/"
    except Exception:
        pass

    fallback = _extract_m3u8_from_text(dl_res.text)
    if fallback:
        return fallback, embed_origin + "/"

    return None


def _resolve_stream_from_page(page_url: str, page_headers: dict):
    session = requests.Session()
    res = session.get(page_url, headers=page_headers, timeout=15)
    html = res.text

    # 1) Direkt m3u8
    direct = _extract_m3u8_from_text(html)
    if direct:
        return direct, _origin(page_url) + "/"

    # 2) iframe tara
    iframes = re.findall(r'<iframe[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html, re.IGNORECASE)

    for raw_iframe in iframes[:10]:
        if_url = raw_iframe.strip()
        if if_url.startswith("//"):
            if_url = "https:" + if_url
        elif not if_url.startswith("http"):
            if_url = urljoin(page_url, if_url)

        if not _is_http_url(if_url):
            continue

        # iframe içinde direkt m3u8
        try:
            if_headers = {
                "User-Agent": USER_AGENT,
                "Referer": page_url,
                "Origin": _origin(page_url)
            }
            if_res = session.get(if_url, headers=if_headers, timeout=12)
            in_iframe = _extract_m3u8_from_text(if_res.text)
            if in_iframe:
                return in_iframe, _origin(if_url) + "/"
        except Exception:
            pass

        # PlayerJS fetch çözümü
        try:
            solved = _resolve_playerjs_embed(if_url, page_url, session)
            if solved:
                return solved
        except Exception:
            continue

    return None


# -----------------------------------------------------------
# HLS Proxy (referer/origin korumalı kaynaklar için)
# -----------------------------------------------------------

@app.route("/hls/proxy")
def hls_proxy():
    target = (request.args.get("u") or "").strip()
    referer = (request.args.get("r") or "").strip()

    if not _is_http_url(target):
        return "Geçersiz URL", 400

    if not _is_http_url(referer):
        referer = _origin(target) + "/"

    req_headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Origin": _origin(referer) or _origin(target)
    }

    try:
        up = requests.get(target, headers=req_headers, timeout=20, allow_redirects=True)
    except Exception:
        return "Proxy upstream hatası", 502

    ctype = up.headers.get("Content-Type", "")
    text_head = up.text[:120] if up.text else ""

    is_playlist = (
        ".m3u8" in (up.url or "").lower()
        or "application/vnd.apple.mpegurl" in ctype.lower()
        or "application/x-mpegurl" in ctype.lower()
        or "#EXTM3U" in text_head
    )

    if is_playlist:
        rewritten = _rewrite_m3u8(up.text, up.url, referer)
        resp = Response(rewritten, status=200, mimetype="application/vnd.apple.mpegurl")
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    resp = Response(up.content, status=up.status_code)
    if ctype:
        resp.headers["Content-Type"] = ctype
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# -----------------------------------------------------------
# 1) Özel canlı proxy
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    if not target_url:
        return "URL eksik", 400

    custom_headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://amp.tvkulesi.com/",
        "Origin": "https://amp.tvkulesi.com"
    }

    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        return Response(
            res.content,
            mimetype='application/vnd.apple.mpegurl',
            headers={'Access-Control-Allow-Origin': '*'}
        )
    except Exception:
        return redirect(target_url)


@app.route('/canli/gold.m3u8')
def proxy_gold():
    url = "https://goldvod.site/live/hpgdisco/123456/266.m3u8"
    try:
        res = requests.get(url, headers={"User-Agent": "VLC/3.0.18 LibVLC/3.0.18"}, timeout=10)
        return Response(
            res.content,
            mimetype='application/vnd.apple.mpegurl',
            headers={'Access-Control-Allow-Origin': '*'}
        )
    except Exception:
        return redirect(url)


@app.route('/canli/sup.m3u8')
def proxy_sup():
    url = "http://sup-4k.org:80/play/live.php?mac=00:1A:79:56:7A:24&stream=10740&extension=ts"
    return Response(
        "",
        status=302,
        headers={
            'Location': url,
            'Access-Control-Allow-Origin': '*',
            'X-Content-Type-Options': 'nosniff'
        }
    )


# -----------------------------------------------------------
# 2) Standart canlı TV
# -----------------------------------------------------------

def fetch_dogus(url, headers):
    try:
        res = requests.get(url, headers=headers, timeout=10)
        match = re.search(
            r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']',
            res.text
        )
        if match:
            return match.group(1).replace('\\/', '/')
    except Exception:
        return None
    return None


@app.route('/canli/<kanal>')
def stream_canli(kanal):
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }

    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber",
        "aspor": "https://cdn504.tvkulesi.com/aspor.m3u8?hst=amp.tvkulesi.com&ch=a-spor"
    }

    if kanal in dogus:
        ref = dogus[kanal]
        local_headers = {
            "User-Agent": USER_AGENT,
            "Referer": ref,
            "Origin": _origin(ref)
        }
        link = fetch_dogus(dogus[kanal], local_headers)
        if link:
            return _redirect_no_cache(link)

    if kanal in turkuvaz:
        return _redirect_no_cache(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404


# -----------------------------------------------------------
# 3) Evrensel çözücü
# -----------------------------------------------------------

@app.route('/api')
def resolve_universal():
    target_url = (request.args.get('url') or "").strip()
    if not target_url:
        return "URL eksik. Kullanım: /api?url=...", 400

    if re.search(r'\.m3u8($|[?&])', target_url, re.IGNORECASE):
        # Direkt m3u8 ise proxy üzerinden ver
        return _redirect_no_cache(_build_proxy_url(target_url, _origin(target_url) + "/"))

    domain = _origin(target_url)
    custom_headers = {
        "User-Agent": USER_AGENT,
        "Referer": domain + "/",
        "Origin": domain
    }

    try:
        solved = _resolve_stream_from_page(target_url, custom_headers)
        if solved:
            stream_url, ref = solved
            return _redirect_no_cache(_build_proxy_url(stream_url, ref))
    except Exception as e:
        print(f"[resolve_universal] {e}", flush=True)

    return "Video kaynağı bulunamadı.", 404


# -----------------------------------------------------------
# 4) Dizi / Film route
# -----------------------------------------------------------

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    base_domain = "https://filmhane.fit"

    sezon_no, bolum_no = _parse_episode(bolum)
    dizi_url = f"{base_domain}/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"
    film_url = f"{base_domain}/film/{dizi}"

    # Eski özel film eşleştirmeleri
    films = {
        "28-yil-sonra": f"{base_domain}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base_domain}/film/war-machine",
        "banlieusards-3": f"{base_domain}/film/banlieusards-3",
        "zeta": f"{base_domain}/film/zeta",
        "crime-101": f"{base_domain}/film/crime-101",
        "kagittan-hayatlar": f"{base_domain}/film/kagittan-hayatlar",
        "the-wrecking-crew": f"{base_domain}/film/the-wrecking-crew",
        "soyut-disavurumcu-bir-dostlugun-anatomisi-veyahut-yan-yana": f"{base_domain}/film/soyut-disavurumcu-bir-dostlugun-anatomisi-veyahut-yan-yana",
    }

    candidates = []
    if dizi in films:
        candidates.append(films[dizi])
        candidates.append(dizi_url)  # fallback
    else:
        candidates.append(dizi_url)
        candidates.append(film_url)  # kritik fallback

    # duplicate temizliği
    seen = set()
    ordered_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered_candidates.append(c)

    fh_headers = {
        "User-Agent": USER_AGENT,
        "Referer": f"{base_domain}/",
        "Origin": base_domain
    }

    for candidate in ordered_candidates:
        try:
            solved = _resolve_stream_from_page(candidate, fh_headers)
            if solved:
                stream_url, ref = solved
                return _redirect_no_cache(_build_proxy_url(stream_url, ref))
        except Exception as e:
            print(f"[stream_dizi] fail {candidate} -> {e}", flush=True)

    return "Yayın bulunamadı.", 404


# -----------------------------------------------------------
# Ana sayfa
# -----------------------------------------------------------

@app.route('/')
def home():
    return "Aksaçlı Stream API V163.0 - Film fallback + HLS proxy active"


if __name__ == '__main__':
    app.run(debug=True)
