from flask import Flask, redirect
import requests
import re
import json

app = Flask(__name__)

# --- TARAYICI AYARLARI ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}

# -----------------------------------------------------------
# MOTOR: DOĞUŞ GRUBU TARAYICI (DMAX, TLC, NTV, STAR)
# -----------------------------------------------------------
def fetch_dogus_media(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return None
        
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        
        if match:
            clean_link = match.group(1).replace('\\/', '/')
            return clean_link

    except Exception as e:
        return None
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ (CANLI TV)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    target_url = ""
    if kanal == "dmax":
        target_url = "https://www.dmax.com.tr/canli-izle"
    elif kanal == "tlc":
        target_url = "https://www.tlctv.com.tr/canli-izle" 
        HEADERS["Referer"] = "https://www.tlctv.com.tr/"
    elif kanal == "ntv":
        target_url = "https://www.ntv.com.tr/canli-yayin/ntv"
        HEADERS["Referer"] = "https://www.ntv.com.tr/"

    if target_url:
        final_link = fetch_dogus_media(target_url)
        if final_link:
            return redirect(final_link, code=302)
        else:
            return f"{kanal} bulunamadı.", 404
    return "Bilinmeyen kanal.", 404

# -----------------------------------------------------------
# MOTOR: FİLM VE DİZİ AYIKLAYICI (FİLMHANE)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Varsayılan Dizi Şablonu
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    
    # --- ÖZEL DURUMLAR VE FİLMLER ---
    # Yeni bir film eklediğinde altına bir 'elif' eklemen yeterlidir.
    if dizi == "28-yil-sonra": 
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    elif dizi == "war-machine": 
        url = "https://filmhane.art/film/war-machine"
    elif dizi == "banlieusards-3": 
        url = "https://filmhane.art/film/banlieusards-3"
    
    # --------------------------------
    
    headers_fh = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
    try:
        res = requests.get(url, headers=headers_fh, timeout=10)
        
        # 1. Ham sayfada m3u8 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: 
            return redirect(match.group(1).replace('\\', ''), code=302)
        
        # 2. İframe içinde ara (Alternatif Playerlar)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=headers_fh, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: 
                    return redirect(if_match.group(1).replace('\\', ''), code=302)
            except: 
                continue
                
    except Exception as e:
        print(f"Sistem Hatası: {e}")
        pass
        
    return "Yayın kaynağı şu an bulunamadı veya link değişmiş.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V180.5 - War Machine Online"
