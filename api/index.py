from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- GENEL AYARLAR ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.google.com/"
}

# -----------------------------------------------------------
# 1. KÖPRÜ (PROXY) SİSTEMİ - Link var ama oynamıyorsa burası kurtarır
# -----------------------------------------------------------
@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    ref = request.args.get('ref', url) # Referer yoksa kendi URL'sini kullan
    if not url: return "URL eksik", 400
    
    try:
        # Siteyi kandıran sahte kimlik
        proxy_headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Referer": ref,
            "Origin": ref.split('/')[2] if '/' in ref else ""
        }
        res = requests.get(url, headers=proxy_headers, timeout=10, verify=False)
        
        # İçeriği tarayıcıya/player'a olduğu gibi pasla
        return Response(res.content, mimetype=res.headers.get('Content-Type'), headers={
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache'
        })
    except Exception as e:
        return str(e), 500

# -----------------------------------------------------------
# 2. YABAN TV ÇEKİCİ (canlitv.diy üzerinden)
# -----------------------------------------------------------
def fetch_yaban_diy():
    url = "https://www.canlitv.diy/yaban-tv?kat=belgesel"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        # Regex: tırnak içindeki m3u8'i bul
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            raw_link = match.group(1).replace('\\/', '/')
            # Linki direkt değil, bizim proxy üzerinden gönderelim (Referer koruması için)
            return f"/proxy?url={raw_link}&ref=https://www.canlitv.diy/"
    except: pass
    return None

# -----------------------------------------------------------
# 3. FİLMHANE SİSTEMİ (Domain Güncellendi)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    base = "https://filmhane.fit" # Burası patlarsa .net veya .org dene
    url = f"{base}/dizi/{dizi}/sezon-1/bolum-{bolum}"
    
    # Özel film tanımları
    films = {"28-yil-sonra": f"{base}/film/28-yil-sonra-kemik-tapinagi", "war-machine": f"{base}/film/war-machine"}
    if dizi in films: url = films[dizi]

    try:
        res = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"], "Referer": base}, timeout=10)
        # Sayfada m3u8 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            found_link = match.group(1).replace('\\', '')
            return redirect(found_link) # Dizilerde genelde direkt redirect yeter
    except: pass
    return "Dizi/Film bulunamadı veya site yapısı değişti.", 404

# -----------------------------------------------------------
# 4. CANLI TV ROUTER
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    if kanal == "yabantv":
        link = fetch_yaban_diy()
        if link: return redirect(link)
        return "Yaban TV linki bulunamadı.", 404
    
    # DMAX, TLC, NTV
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    if kanal in dogus:
        try:
            r = requests.get(dogus[kanal], headers=HEADERS, timeout=10)
            m = re.search(r'["\'](https?:?//[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', r.text)
            if m: return redirect(m.group(1).replace('\\/', '/'))
        except: pass

    return "Kanal bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı V190.0 - Köprü Sistemi Aktif"
