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
# 1. KÖPRÜ (PROXY) - Referer engelini aşmak için
# -----------------------------------------------------------
@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    ref = request.args.get('ref', "https://www.google.com/")
    if not url: return "URL eksik", 400
    
    try:
        p_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": ref}
        res = requests.get(url, headers=p_headers, timeout=10, stream=True, verify=False)
        return Response(res.content, mimetype=res.headers.get('Content-Type'), headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return str(e), 500

# -----------------------------------------------------------
# 2. YABAN TV ÇEKİCİ (canlitv.diy)
# -----------------------------------------------------------
def fetch_yaban():
    # Site adresini buradan çekiyoruz
    url = "https://www.canlitv.diy/yaban-tv?kat=belgesel"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        # 1. Ham m3u8 ara
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')
        
        # 2. Iframe içinde ara
        iframe = re.search(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        if iframe:
            if_url = iframe.group(1)
            if if_url.startswith('//'): if_url = "https:" + if_url
            if_res = requests.get(if_url, headers={"User-Agent": HEADERS["User-Agent"], "Referer": url}, timeout=5)
            if_match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', if_res.text)
            if if_match: return if_match.group(1).replace('\\/', '/')
    except: pass
    return None

# -----------------------------------------------------------
# 3. FİLMHANE / DİZİ SİSTEMİ (Restore Edildi)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Dizi siteleri domain değiştirince burayı güncellemek gerekir
    base = "https://filmhane.fit" 
    
    # Sezon/Bölüm ayrıştırma (V186'daki mantık korundu)
    sezon = "1"
    b_no = bolum
    s_match = re.search(r'[sS](\d+)', bolum)
    if s_match: sezon = s_match.group(1)
    
    url = f"{base}/dizi/{dizi}/sezon-{sezon}/bolum-{bolum}"
    
    # Film mi dizi mi kontrolü
    films = {
        "28-yil-sonra": f"{base}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base}/film/war-machine"
    }
    if dizi in films: url = films[dizi]

    try:
        res = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"], "Referer": base}, timeout=10)
        # Sayfadaki ilk m3u8'i çek
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            return redirect(match.group(1).replace('\\', ''), code=302)
    except: pass
    return "Yayın bulunamadı. Site adresi (domain) değişmiş olabilir.", 404

# -----------------------------------------------------------
# 4. CANLI TV ROUTER
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    if kanal == "yabantv":
        link = fetch_yaban()
        if link: return redirect(link)
        return "Yaban TV çekilemedi.", 404
        
    # Standart kanallar (NTV, DMAX vb.)
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle"
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
    return "Aksaçlı Stream API V195.0 - All Systems Restored"
