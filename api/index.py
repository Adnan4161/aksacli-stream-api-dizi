from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- ORTAK AYARLAR ---
# Gerçek bir Chrome tarayıcısı gibi görünmek için detaylı User-Agent
HEADERS_COMMON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# --- MOTOR 1: FİLMHANE MOTORU (Çalışan Eski Sistem) ---
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

# --- MOTOR 2: HDFİLMİZLE MOTORU (GÜÇLENDİRİLMİŞ DERİN TARAMA) ---
def fetch_from_hdfilmizle(target_url):
    headers = HEADERS_COMMON.copy()
    headers["Referer"] = "https://www.hdfilmizle.life/"
    
    try:
        res = requests.get(target_url, headers=headers, timeout=10)
        
        # Site açılmıyorsa zorlama
        if res.status_code != 200: return None
        
        # Taktik 1: "file": "http..." yapısını ara (Genelde playerlar böyle saklar)
        file_match = re.search(r'file\s*:\s*["\'](https?://[^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', res.text)
        if file_match: return file_match.group(1)

        # Taktik 2: Standart m3u8/mp4 arama
        link_match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', res.text)
        if link_match: return link_match.group(1).replace('\\', '')

        # Taktik 3: iFrame ve Data-Src Taraması
        # Sadece src değil, data-src özelliklerine de bakıyoruz
        iframes = re.findall(r'<iframe.*?(?:src|data-src)=["\'](.*?)["\']', res.text)
        
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if "facebook" in if_url or "twitter" in if_url: continue # Reklamları geç
            
            try:
                # İframe içine girerken o sayfanın referansını verelim
                if_headers = headers.copy()
                if_headers["Referer"] = target_url
                
                if_res = requests.get(if_url, headers=if_headers, timeout=5)
                
                # İframe içinde "file": "..." ara
                if_file = re.search(r'file\s*:\s*["\'](https?://[^"\']+\.(?:mp4|m3u8)[^"\']*)["\']', if_res.text)
                if if_file: return if_file.group(1)
                
                # İframe içinde normal link ara
                if_link = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', if_res.text)
                if if_link: return if_link.group(1).replace('\\', '')
                
            except: continue
            
    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

def get_live_link(dizi_slug, bolum_no):
    
    # --- YÖNLENDİRME MERKEZİ ---
    
    # 1. HDFilmizle Filmleri (Uçurum)
    if dizi_slug == "ucurum-2026":
        return fetch_from_hdfilmizle("https://www.hdfilmizle.life/ucurum-2026/")

    # 2. Filmhane Filmleri (28 Yıl Sonra)
    elif dizi_slug == "28-yil-sonra":
        return fetch_from_filmhane("https://filmhane.art/film/28-yil-sonra-kemik-tapinagi")

    # 3. Varsayılan Diziler (Filmhane)
    else:
        # Dizi linki
        url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
        return fetch_from_filmhane(url)

@app.route('/')
def home():
    return "Stream API V165.0 - Derin Tarama Modu"

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
