from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.ahaber.com.tr/",
    "Origin": "https://www.ahaber.com.tr"
}

# -----------------------------------------------------------
# 1. YARDIMCI FONKSİYONLAR (DİNAMİK LİNK ÇEKİCİLER)
# -----------------------------------------------------------

def fetch_dogus(url):
    """NTV, DMAX, TLC için m3u8 yakalar"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
    return None

def fetch_turkuvaz(url):
    """A Haber, ATV, A Spor iframe içinden anlık m3u8 ve tokenları yakalar"""
    try:
        # İlgili kanalın iframe sayfasına gidiyoruz
        local_headers = HEADERS.copy()
        local_headers["Referer"] = url
        res = requests.get(url, headers=local_headers, timeout=10)
        
        # iframe içindeki güncel m3u8 linkini (tokenlar dahil) regex ile cımbızlıyoruz
        match = re.search(r'["\'](https?://[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')
    except:
        return None
    return None

# -----------------------------------------------------------
# 2. PROXY & KÖPRÜ SİSTEMLERİ
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
# 3. CANLI TV SİSTEMİ (DİNAMİK)
# -----------------------------------------------------------

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    # Doğuş Grubu
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    
    # Turkuvaz Grubu (Senin istediğin iframe sistemi)
    turkuvaz_iframes = {
        "ahaber": "https://www.ahaber.com.tr/iframe/canli-yayin",
        "atv": "https://www.atv.com.tr/iframe/canli-yayin",
        "aspor": "https://www.aspor.com.tr/iframe/canli-yayin",
        "a2": "https://www.a2tv.com.tr/iframe/canli-yayin"
    }

    if kanal in dogus:
        HEADERS["Referer"] = dogus[kanal].replace("canli-izle", "")
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
        
    if kanal in turkuvaz_iframes:
        # Doğrudan iframe linkine gidip güncel tokenlı linki alıyoruz
        link = fetch_turkuvaz(turkuvaz_iframes[kanal])
        if link: return redirect(link, code=302)

    return "Kanal bulunamadı veya yayın şu an aktif değil.", 404

# -----------------------------------------------------------
# 4. FİLM & DİZİ SİSTEMİ (S1B5 DESTEKLİ)
# -----------------------------------------------------------

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    sezon_no = "1"
    bolum_no = bolum

    s_match = re.search(r'[sS](\d+)', bolum)
    b_match = re.search(r'[bB](\d+)', bolum)

    if s_match and b_match:
        sezon_no = s_match.group(1)
        bolum_no = b_match.group(1)
    elif b_match:
        bolum_no = b_match.group(1)

    url = f"https://filmhane.art/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"
    
    # Film arşivi
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
    return "Dizi/Film bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V181.7 - Dynamic Turkuvaz & Series System Active"

if __name__ == '__main__':
    app.run(debug=True)
