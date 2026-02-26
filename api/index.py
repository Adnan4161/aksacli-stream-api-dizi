from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- MOTOR 1: FİLMHANE MOTORU (Bu motoru daha önce test ettik, dizilerde çalışıyor) ---
def fetch_from_filmhane(target_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://filmhane.art/"
    }
    
    try:
        res = requests.get(target_url, headers=headers, timeout=15)
        if res.status_code != 200: return None
            
        # 1. Direkt m3u8
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return match.group(1).replace('\\', '')
        
        # 2. iFrame Taraması (En önemlisi bu)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                # İframe içine girerken de Filmhane kimliğini koruyoruz
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return if_match.group(1).replace('\\', '')
            except: continue
    except Exception as e:
        print(f"Filmhane Hatası: {e}")
        return None
    return None

# --- MOTOR 2: HDFİLMİZLE MOTORU (Yeni site için özel motor) ---
def fetch_from_hdfilmizle(target_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.hdfilmizle.life/"
    }
    
    try:
        res = requests.get(target_url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        
        # Bu site genelde 'file': '...' yapısını veya packed script kullanır.
        # Önce basit m3u8/mp4 arayalım
        match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', res.text)
        if match: return match.group(1).replace('\\', '')

        # iFrame Taraması
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # Bu sitenin playerları farklı domainde olabilir, referer'ı iframe linkine göre güncelleyelim
            try:
                if_headers = headers.copy()
                if_headers['Referer'] = target_url # Referer olarak filmin sayfasını gösterelim
                
                if_res = requests.get(if_url, headers=if_headers, timeout=5)
                # İframe içinde video linki ara
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', if_res.text)
                if if_match: return if_match.group(1).replace('\\', '')
            except: continue
    except Exception as e:
        print(f"HDfilmizle Hatası: {e}")
        return None
    return None

def get_live_link(dizi_slug, bolum_no):
    # --- YÖNLENDİRME MERKEZİ ---
    
    # SENARYO 1: YENİ SİTE (Uçurum 2026) -> Motor 2'ye git
    if dizi_slug == "ucurum-2026":
        url = "https://www.hdfilmizle.life/ucurum-2026/"
        return fetch_from_hdfilmizle(url)

    # SENARYO 2: FİLMHANE FİLMİ (28 Yıl Sonra) -> Motor 1'e git
    elif dizi_slug == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
        return fetch_from_filmhane(url)

    # SENARYO 3: VARSAYILAN DİZİLER (Ayşe, Asylum vb.) -> Motor 1'e git
    else:
        url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
        return fetch_from_filmhane(url)

@app.route('/')
def home():
    return "Stream API Aktif. V164.0 - Çift Motorlu Sistem."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
