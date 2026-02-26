from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

def get_live_link(dizi_slug, bolum_no):
    # 1. Varsayılan URL (Standart Diziler için)
    # Örnek: https://filmhane.art/dizi/asylum/sezon-1/bolum-1
    url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"

    # 2. ÖZEL FİLMLER (Sadece Filmhane üzerindekiler)
    if dizi_slug == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    
    elif dizi_slug == "ucurum": # Veya ucurum-2026, Filmhane linkine göre bakmak lazım
        url = "https://filmhane.art/film/ucurum"

    # 3. FİLMHANE KİMLİĞİ (En kararlı çalışan ayar)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://filmhane.art/"
    }

    try:
        # İsteği at
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return None
            
        # YÖNTEM 1: Direkt m3u8 bulma
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')
        
        # YÖNTEM 2: iFrame Taraması (En önemlisi)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                # İframe içine de Filmhane kimliğiyle giriyoruz
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match:
                    return if_match.group(1).replace('\\', '')
            except:
                continue
    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

@app.route('/')
def home():
    return "Stream API Aktif. V162.7 - Orjinal Filmhane Sürümü."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
