from flask import Flask, redirect
import requests
import re
import json

app = Flask(__name__)

# --- TARAYICI AYARLARI ---
# DMAX, bot olduğumuzu anlamasın diye tam teçhizatlı kimlik
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
        # 1. Sayfaya git
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return None
        
        # 2. "daioncdn" içeren linki ara (DMAX'in sunucusu)
        # Linkler genellikle JSON içinde olduğu için "escape" edilmiş olabilir (https:\/\/...)
        # Bu Regex hem normal hem de kaçış karakterli linkleri bulur.
        
        # Örnek Aranan: https://dogus.daioncdn.net/dmax/dmax.m3u8?token=...
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        
        if match:
            # Bulunan linkteki ters slaşları (\) temizle
            clean_link = match.group(1).replace('\\/', '/')
            print(f"Buldum!: {clean_link}")
            return clean_link

    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    
    target_url = ""
    
    # KANAL LİSTESİ
    if kanal == "dmax":
        target_url = "https://www.dmax.com.tr/canli-izle"
        
    elif kanal == "tlc":
        # TLC de aynı altyapıyı kullanır
        target_url = "https://www.tlctv.com.tr/canli-izle" 
        HEADERS["Referer"] = "https://www.tlctv.com.tr/"

    elif kanal == "ntv":
        # NTV de aynı altyapıyı kullanır
        target_url = "https://www.ntv.com.tr/canli-yayin/ntv"
        HEADERS["Referer"] = "https://www.ntv.com.tr/"

    # --- İŞLEM ---
    if target_url:
        # Doğuş Grubu (DaionCDN) için özel tarayıcıyı kullan
        final_link = fetch_dogus_media(target_url)
        
        if final_link:
            return redirect(final_link, code=302)
        else:
            return f"{kanal} linki sayfada bulunamadı. Token sistemi değişmiş olabilir.", 404
    else:
        return "Bilinmeyen kanal.", 404

# --- ESKİ DİZİ SİSTEMİ (ÇALIŞAN HALİYLE) ---
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Filmhane ayarları
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    if dizi == "28-yil-sonra": url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    
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
    return "Stream API V180.0 - DMAX Token Avcısı"
