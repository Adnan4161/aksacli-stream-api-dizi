from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- ORTAK TARAYICI AYARLARI ---
HEADERS_COMMON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

# -----------------------------------------------------------
# MOTOR 1: GENEL TARAYICI (Hem Diziler Hem Canlı Yayın İçin)
# -----------------------------------------------------------
def fetch_m3u8(target_url, referer):
    headers = HEADERS_COMMON.copy()
    headers["Referer"] = referer
    
    try:
        print(f"Taranıyor: {target_url}")
        res = requests.get(target_url, headers=headers, timeout=10)
        
        if res.status_code != 200: return None
        
        # 1. Direkt Link Arama (.m3u8)
        # Genellikle "file": "..." veya src="..." içinde olur
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: 
            return match.group(1).replace('\\', '')
        
        # 2. iFrame Taraması (Eğer yayın başka kutudaysa)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return if_match.group(1).replace('\\', '')
            except: continue

    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

# -----------------------------------------------------------
# ROUTER 1: DİZİ VE FİLMLER (Eski Sistem - Dokunmadık)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Varsayılan (Filmhane)
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    ref = "https://filmhane.art/"

    # Özel Filmler
    if dizi == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    elif dizi == "ucurum":
        url = "https://filmhane.art/film/ucurum"

    final_link = fetch_m3u8(url, ref)
    
    if final_link: return redirect(final_link, code=302)
    else: return "Dizi/Film Bulunamadı", 404

# -----------------------------------------------------------
# ROUTER 2: CANLI YAYINLAR (YENİ EKLENDİ! 🔴)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    url = ""
    ref = ""

    # --- KANAL LİSTESİ ---
    if kanal == "dmax":
        url = "https://www.dmax.com.tr/canli-izle"
        ref = "https://www.dmax.com.tr/"
        
    elif kanal == "tlc":
        url = "https://www.tlctv.com.tr/canli-izle"
        ref = "https://www.tlctv.com.tr/"
        
    elif kanal == "ntv":
        url = "https://www.ntv.com.tr/canli-yayin/ntv"
        ref = "https://www.ntv.com.tr/"

    # --- TARAMA VE YÖNLENDİRME ---
    if url:
        final_link = fetch_m3u8(url, ref)
        if final_link:
            return redirect(final_link, code=302)
        else:
            return f"{kanal} yayini şu an çekilemedi.", 404
    else:
        return "Tanımsız Kanal", 404

@app.route('/')
def home():
    return "Stream API V170.0 - Canlı TV Modu Eklendi."
