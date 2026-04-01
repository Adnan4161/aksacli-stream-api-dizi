from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}

# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ (ATV & AHABER BURADA)
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    if not target_url: return "URL eksik", 400
    
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://amp.tvkulesi.com/",
        "Origin": "https://amp.tvkulesi.com"
    }
    
    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except:
        return redirect(target_url)

@app.route('/canli/gold.m3u8')
def proxy_gold():
    url = "https://goldvod.site/live/hpgdisco/123456/266.m3u8"
    try:
        res = requests.get(url, headers={"User-Agent": "VLC/3.0.18 LibVLC/3.0.18"}, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except: return redirect(url)

# -----------------------------------------------------------
# 2. STANDART CANLI TV (DMAX, TLC, NTV, ATV, AHABER)
# -----------------------------------------------------------
def fetch_dogus(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
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
        HEADERS["Referer"] = dogus[kanal].replace("canli-izle", "")
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
        
    if kanal in turkuvaz:
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# 3. FİLMHANE SİSTEMİ (S1B5 DESTEĞİYLE)
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
    films = {"28-yil-sonra": "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi", "war-machine": "https://filmhane.art/film/war-machine", "zeta": "https://filmhane.art/film/zeta"}
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

# -----------------------------------------------------------
# 4. DİZİPAL SİSTEMİ (YENİ EKLEDİĞİMİZ BÖLÜM)
# -----------------------------------------------------------
@app.route('/yayin/dizipal/<slug>')
def stream_dizipal(slug):
    base_url = "https://dizipal.im"
    url = f"{base_url}/bolum/{slug}/"
    try:
        dp_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": base_url}
        res = requests.get(url, headers=dp_headers, timeout=10)
        
        # Sayfa içinde m3u8 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
        
        # Iframe'leri tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if any(x in if_url for x in ['vidmoly', 'fembed', 'upstream', 'moly', 'dizipal']):
                try:
                    if_res = requests.get(if_url, headers=dp_headers, timeout=5)
                    if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                    if if_match: return redirect(if_match.group(1).replace('\\', ''), code=302)
                except: continue
    except: pass
    return "Dizipal yayını bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V182.2 - Dizipal & Filmhane Multi-Source Active"

if __name__ == '__main__':
    app.run(debug=True)
