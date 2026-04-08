from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.yabantv.com/",
    "Origin": "https://www.yabantv.com"
}

# -----------------------------------------------------------
# YABAN TV ÖZEL ÇEKİCİ (SCRAPER)
# -----------------------------------------------------------
def fetch_yaban():
    broadcast_url = "https://www.yabantv.com/broadcast"
    try:
        # Ana sayfayı çek
        res = requests.get(broadcast_url, headers=HEADERS, timeout=10)
        
        # 1. Sayfa içinde direkt m3u8 ara (hash dahil)
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')
            
        # 2. Eğer bulamazsa Iframe içinde ara (canlitv.fun vb. için)
        iframe_match = re.search(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        if iframe_match:
            if_url = iframe_match.group(1)
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            if_res = requests.get(if_url, headers=HEADERS, timeout=5)
            # Iframe içindeki m3u8 linkini yakala
            if_match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', if_res.text)
            if if_match:
                return if_match.group(1).replace('\\/', '/')
    except Exception as e:
        print(f"Yaban TV Hatası: {e}")
    return None

# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ
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

# -----------------------------------------------------------
# 2. CANLI TV ROUTER (YABAN TV EKLENDİ)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    # Doğuş Grubu Scraper Fonksiyonu
    def fetch_dogus(url):
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
            if match: return match.group(1).replace('\\/', '/')
        except: return None
        return None

    # Yaban TV Kontrolü
    if kanal == "yabantv":
        link = fetch_yaban()
        if link:
            return redirect(link, code=302)
        return "Yaban TV linki çekilemedi.", 404

    # Diğer Kanallar
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
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
        
    if kanal in turkuvaz:
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# 3. FİLMHANE SİSTEMİ
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
    }
    if dizi in films: url = films[dizi]
    
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": f"{base_domain}/"}
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
    return "Aksaçlı Stream API V187.0 - Yaban TV & Filmhane Active"

if __name__ == '__main__':
    app.run(debug=True)
