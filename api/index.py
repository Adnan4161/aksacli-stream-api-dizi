from flask import Flask, redirect, Response, request
import requests
import re
from urllib.parse import urlparse, urljoin

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}


def _origin(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def _clean_url(raw: str):
    if not raw:
        return None
    return raw.replace("\\/", "/").replace("\\\\", "").strip().strip('"').strip("'")


def _redirect_nocache(url: str):
    r = redirect(url, code=302)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    r.headers["Pragma"] = "no-cache"
    return r


def _extract_direct_stream(text: str):
    if not text:
        return None

    patterns = [
        r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        r'(?:file|src)\s*[:=]\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        r'"url"\s*:\s*"((?:https?:)?\\?/\\?/[^"]+?\.m3u8[^"]*)"'
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


def _resolve_playerjs_embed(embed_url: str, page_url: str, session: requests.Session):
    page_origin = _origin(page_url)
    embed_origin = _origin(embed_url)

    embed_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": page_url,
        "Origin": page_origin
    }

    embed_res = session.get(embed_url, headers=embed_headers, timeout=10)
    embed_html = embed_res.text

    # Bazı embed sayfaları m3u8'i direkt içeriyor olabilir.
    direct = _extract_direct_stream(embed_html)
    if direct:
        return direct

    # PlayerJS fetch('/dl?op=get_stream...')
    fetch_match = re.search(r"fetch\(['\"]([^'\"]*op=get_stream[^'\"]*)['\"]\)", embed_html, re.IGNORECASE)
    if not fetch_match:
        return None

    dl_url = urljoin(embed_url, fetch_match.group(1))

    cookies = {}
    for k in ("file_id", "aff", "ref_url"):
        v = _extract_cookie_value(embed_html, k)
        if v:
            cookies[k] = v

    dl_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": embed_url,
        "Origin": embed_origin,
        "Accept": "application/json, text/plain, */*"
    }

    dl_res = session.get(dl_url, headers=dl_headers, cookies=cookies or None, timeout=10)
    dl_text = dl_res.text

    try:
        data = dl_res.json()
        if isinstance(data, dict) and data.get("url"):
            return _clean_url(data["url"])
    except Exception:
        pass

    return _extract_direct_stream(dl_text)


def _resolve_stream_from_page(page_url: str, page_headers: dict):
    session = requests.Session()
    res = session.get(page_url, headers=page_headers, timeout=12)
    html = res.text

    # 1) Direkt m3u8/file/src
    stream = _extract_direct_stream(html)
    if stream:
        return stream

    # 2) iframe tara
    iframes = re.findall(r'<iframe[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html, re.IGNORECASE)

    for raw_iframe in iframes[:8]:
        if_url = raw_iframe.strip()
        if if_url.startswith("//"):
            if_url = "https:" + if_url
        elif not if_url.startswith("http"):
            if_url = urljoin(page_url, if_url)

        if not if_url.startswith("http"):
            continue

        # iframe içinde direkt m3u8 var mı?
        try:
            if_headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Referer": page_url,
                "Origin": _origin(page_url)
            }
            if_res = session.get(if_url, headers=if_headers, timeout=10)
            in_iframe = _extract_direct_stream(if_res.text)
            if in_iframe:
                return in_iframe
        except Exception:
            pass

        # PlayerJS fetch('/dl?op=get_stream') çöz
        try:
            via_playerjs = _resolve_playerjs_embed(if_url, page_url, session)
            if via_playerjs:
                return via_playerjs
        except Exception:
            continue

    return None


# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    if not target_url:
        return "URL eksik", 400

    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://amp.tvkulesi.com/",
        "Origin": "https://amp.tvkulesi.com"
    }

    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except Exception:
        return redirect(target_url)


@app.route('/canli/gold.m3u8')
def proxy_gold():
    url = "https://goldvod.site/live/hpgdisco/123456/266.m3u8"
    try:
        res = requests.get(url, headers={"User-Agent": "VLC/3.0.18 LibVLC/3.0.18"}, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except Exception:
        return redirect(url)


@app.route('/canli/sup.m3u8')
def proxy_sup():
    url = "http://sup-4k.org:80/play/live.php?mac=00:1A:79:56:7A:24&stream=10740&extension=ts"
    return Response("", status=302, headers={'Location': url, 'Access-Control-Allow-Origin': '*', 'X-Content-Type-Options': 'nosniff'})


# -----------------------------------------------------------
# 2. STANDART CANLI TV
# -----------------------------------------------------------

def fetch_dogus(url, headers):
    try:
        res = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
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
        local_headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Referer": dogus[kanal],
            "Origin": _origin(dogus[kanal])
        }
        link = fetch_dogus(dogus[kanal], local_headers)
        if link:
            return _redirect_nocache(link)

    if kanal in turkuvaz:
        return _redirect_nocache(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404


# -----------------------------------------------------------
# 3. EVRENSEL ÇÖZÜCÜ
# -----------------------------------------------------------

@app.route('/api')
def resolve_universal():
    target_url = request.args.get('url')
    if not target_url:
        return "URL eksik. Kullanım: /api?url=...", 400

    # Zaten m3u8 ise direkt geçir.
    if re.search(r'\.m3u8($|[?&])', target_url, re.IGNORECASE):
        return _redirect_nocache(target_url)

    parsed_uri = urlparse(target_url)
    domain = f"{parsed_uri.scheme}://{parsed_uri.netloc}"

    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": domain + "/",
        "Origin": domain
    }

    try:
        stream = _resolve_stream_from_page(target_url, custom_headers)
        if stream:
            return _redirect_nocache(stream)
    except Exception as e:
        print(f"[resolve_universal] {e}", flush=True)

    return "Video kaynağı bulunamadı.", 404


# -----------------------------------------------------------
# 4. DİZİ / FİLM
# -----------------------------------------------------------

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    base_domain = "https://filmhane.fit"

    sezon_no = "1"
    bolum_no = bolum

    s_match = re.search(r'[sS](\d+)', bolum)
    b_match = re.search(r'[bB](\d+)', bolum)

    if s_match and b_match:
        sezon_no = s_match.group(1)
        bolum_no = b_match.group(1)
    elif b_match:
        bolum_no = b_match.group(1)

    url = f"{base_domain}/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"

    films = {
        "28-yil-sonra": f"{base_domain}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base_domain}/film/war-machine",
        "banlieusards-3": f"{base_domain}/film/banlieusards-3",
        "zeta": f"{base_domain}/film/zeta",
        "crime-101": f"{base_domain}/film/crime-101",
        "kagittan-hayatlar": f"{base_domain}/film/kagittan-hayatlar",
        "the-wrecking-crew": f"{base_domain}/film/the-wrecking-crew",
    }

    if dizi in films:
        url = films[dizi]

    fh_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": f"{base_domain}/",
        "Origin": base_domain
    }

    try:
        stream = _resolve_stream_from_page(url, fh_headers)
        if stream:
            return _redirect_nocache(stream)
    except Exception as e:
        print(f"[stream_dizi] {url} -> {e}", flush=True)

    return "Yayın bulunamadı.", 404


@app.route('/')
def home():
    return "Aksaçlı Stream API V162.8 - Filmhane PlayerJS fetch resolver active"

if __name__ == '__main__':
    app.run(debug=True)
