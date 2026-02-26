from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- ORTAK TARAYICI AYARLARI ---
HEADERS_COMMON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# -----------------------------------------------------------
# MOTOR 1: FİLMHANE (Diziler ve 28 Yıl Sonra için - ÇALIŞAN)
# -----------------------------------------------------------
def fetch_from_filmhane(target_url):
    headers = HEADERS_COMMON.copy()
    headers["Referer"] = "https://filmhane.art/"
    
    try:
        res = requests.get(target_url, headers=headers, timeout=10)
        if res.status_code != 200: return None
        
        # 1. Direkt Link
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return match.group(1).replace('\\', '')
        
        # 2. iFrame Taraması
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return if_match.group(1).replace('\\', '')
            except: continue
    except: return None
    return None

# -----------------------------------------------------------
# MOTOR 2: FİLMİZYON (Yeni Site - Uçurum Filmi İçin)
# -----------------------------------------------------------
def fetch_from_filmizyon(target_url):
    headers = HEADERS_COMMON.copy()
    # En önemli kısım: Siteye "Ben senin ana sayfandan geliyorum" diyoruz
    headers["Referer"] = "https://www.filmizyon.com/"
    
    try:
        print(f"Filmizyon taranıyor: {target_url}")
        res = requests.get(target_url, headers=headers, timeout=10)
        
        if res.status_code != 200: 
            print("Siteye erişilemedi.")
            return None
        
        # 1. iFrame Taraması (Filmizyon genelde iframe kullanır)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # Reklamları atla
            if "youtube" in if_url or "google" in if_url: continue

            try:
                # İframe'in içine girerken de Filmizyon kimliğini koru
                iframe_headers = headers.copy()
                iframe_headers["Referer"] = target_url # Referans olarak filmin sayfasını göster
                
                if_res = requests.get(if_url, headers=iframe_headers, timeout=6)
                
                # İframe içinde m3u8 veya mp4 ara
                match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', if_res.text)
                if match: 
                    clean_link = match.group(1).replace('\\', '')
                    print(f"Link bulundu: {clean_link}")
                    return clean_link
            except: continue
            
        # 2. Eğer iframe yoksa sayfada direkt link ara (Yedek plan)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', res.text)
        if match: return match.group(1).replace('\\', '')

    except Exception as e:
        print(f"Filmizyon Hatası: {e}")
        return None
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ (ROUTER)
# -----------------------------------------------------------
def get_live_link(dizi_slug, bolum_no):
    
    # 1. SENARYO: "Uçurum" istenirse -> FİLMİZYON'a git
    if dizi_slug == "ucurum-2026":
        return fetch_from_filmizyon("https://www.filmizyon.com/film/ucurum/")

    # 2. SENARYO: "28 Yıl Sonra" istenirse -> FİLMHANE'ye git (Eski çalışan ayar)
    elif dizi_slug == "28-yil-sonra":
        return fetch_from_filmhane("https://filmhane.art/film/28-yil-sonra-kemik-tapinagi")

    # 3. SENARYO: Diğer her şey (Diziler) -> FİLMHANE'ye git (Standart)
    else:
        url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
        return fetch_from_filmhane(url)

@app.route('/')
def home():
    return "Stream API V166.0 - Filmizyon Entegreli."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
