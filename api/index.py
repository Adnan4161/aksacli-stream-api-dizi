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
# MOTOR: EVRENSEL CANLI YAYIN AYIKLAYICI
# -----------------------------------------------------------
def fetch_live_stream(url, custom_referer):
    try:
        # Her kanalın kendi referer adresini kullanması güvenlik için şarttır
        current_headers = HEADERS.copy()
        current_headers["Referer"] = custom_referer
        
        res = requests.get(url, headers=current_headers, timeout=10)
        if res.status_code != 200: return None
        
        # ARTIK DAIONCDN ŞARTI YOK: Herhangi bir .m3u8 uzantılı linki yakalar (ATV dahil)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        
        if match:
            clean_link = match.group(1).replace('\\/', '/')
            return clean_link

    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ (CANLI TV)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    target_url = ""
    referer_url = HEADERS["Referer"] # Varsayılan referer
    
    if kanal == "dmax":
        target_url = "https://www.dmax.com.tr/canli-izle"
    elif kanal == "tlc":
        target_url = "https://www.tlctv.com.tr/canli-izle" 
        referer_url = "https://www.tlctv.com.tr/"
    elif kanal == "ntv":
        target_url = "https://www.ntv.com.tr/canli-yayin/ntv"
        referer_url = "https://www.ntv.com.tr/"
    elif kanal == "atv":
        # ATV'nin iframe üzerinden yayın veren resmi adresi
        target_url = "https://www.atv.com.tr/iframe/canli-yayin"
        referer_url = "https://www.atv.com.tr/"

    if target_url:
        final_link = fetch_live_stream(target_url, referer_url)
        if final_link:
            return redirect(final_link, code=302)
        else:
            return f"{kanal} yayını sayfada bulunamadı.", 404
    return "Bilinmeyen kanal.", 404

# -----------------------------------------------------------
# MOTOR: FİLM VE DİZİ AYIKLAYICI (FİLMHANE) - Mevcut hali korundu
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    if dizi == "28-yil-sonra": 
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    elif dizi == "war-machine": 
        url = "https://filmhane.art/film/war-machine"
    elif dizi == "banlieusards-3": 
        url = "https://filmhane.art/film/banlieusards-3"
    
    headers_fh = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
    try:
        res = requests.get(url, headers=headers_fh, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
        
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=headers_fh, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return redirect(if_match.group(1).replace('\\', ''), code=302)
            except: continue
    except: pass
    return "Kaynak bulunamadı", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V181.0 - Evrensel CDN Aktif"
