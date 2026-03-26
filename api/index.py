from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# -----------------------------------------------------------
# 1. YOUTUBE RESOLVER (YouTube Canlı Yayını m3u8'e Çevirir)
# -----------------------------------------------------------
def resolve_youtube(video_id):
    """YouTube Canlı Yayın sayfasından taze m3u8 linkini cımbızlar"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        # hlsManifestUrl içindeki taze linki arıyoruz
        match = re.search(r'hlsManifestUrl["\']:\s*["\']([^"\'\s<>]+?index\.m3u8[^"\'\s<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')
    except:
        return None
    return None

@app.route('/youtube/<vid>')
def youtube_stream(vid):
    # m3u8 linkini çözüyoruz
    m3u8_link = resolve_youtube(vid)
    if m3u8_link:
        # Doğrudan m3u8 linkine yönlendiriyoruz, kontrol senin player'ında kalıyor
        return redirect(m3u8_link, code=302)
    return "YouTube linki çözülemedi.", 404

# -----------------------------------------------------------
# 2. CANLI TV (Doğuş & Turkuvaz Proxy)
# -----------------------------------------------------------
@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    if not target_url: return "URL eksik", 400
    custom_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://amp.tvkulesi.com/", "Origin": "https://amp.tvkulesi.com"}
    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except: return redirect(target_url)

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber",
        "aspor": "https://cdn504.tvkulesi.com/aspor.m3u8?hst=amp.tvkulesi.com&ch=a-spor"
    }
    if kanal in turkuvaz:
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")
    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# 3. FİLM & DİZİ SİSTEMİ (S1B5 Desteği)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    sezon_no, bolum_no = "1", bolum
    s_match = re.search(r'[sS](\d+)', bolum)
    b_match = re.search(r'[bB](\d+)', bolum)
    if s_match and b_match:
        sezon_no, bolum_no = s_match.group(1), b_match.group(1)
    elif b_match:
        bolum_no = b_match.group(1)

    url = f"https://filmhane.art/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"
    
    films = {
        "28-yil-sonra": "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": "https://filmhane.art/film/war-machine",
        "zeta": "https://filmhane.art/film/zeta"
    }
    if dizi in films: url = films[dizi]
    
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
        res = requests.get(url, headers=fh_headers, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=fh_headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return redirect(if_match.group(1).replace('\\', ''), code=302)
            except: continue
    except: pass
    return "Yayın bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V182.0 - YouTube Resolver & Series System Active"
