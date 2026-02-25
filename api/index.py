from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

def get_live_link(dizi_slug, bolum_no):
    # Yeni site yapısına göre link oluşturma
    # Örnek: https://filmhane.art/dizi/asylum/sezon-1/bolum-1
    url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://filmhane.art/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return None
            
        # 1. Yöntem: Sayfa içinde m3u8 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')
        
        # 2. Yöntem: iFrame/Script içindeki linkleri tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
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
    return "Stream API Aktif. Filmhane altyapısı devrede."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Taze link bulunamadı, site yapısı veya dizi adı hatalı olabilir.", 404
# ... üstteki dizi kodları ...

    # --- FİLMLER ---
    elif dizi_adi == "28-yil-sonra":
        # Filmin direkt sayfa linki
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"

    # ... kodun devamı (requests.get vs.) ...
