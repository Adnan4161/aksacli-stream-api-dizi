from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

def get_live_link(dizi_slug, bolum_no):
    # ----------------------------------------------------------------
    # ADIM 1: URL BELİRLEME (Hangi yemeği istiyoruz?)
    # ----------------------------------------------------------------
    
    # Varsayılan: Standart Filmhane Dizi Linki
    url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
    site_tipi = "filmhane" # Varsayılan site

    # --- ÖZEL DURUMLAR (İSTİSNALAR) ---
    
    # 1. İstisna: Filmhane'deki Film (28 Yıl Sonra)
    if dizi_slug == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
        site_tipi = "filmhane"

    # 2. İstisna: Yeni Site (Uçurum 2026)
    elif dizi_slug == "ucurum-2026":
        url = "https://www.hdfilmizle.life/ucurum-2026/"
        site_tipi = "hdfilmizle"
        
    # ----------------------------------------------------------------
    # ADIM 2: KİMLİK (HEADER) AYARLAMA (Kapıdan nasıl gireceğiz?)
    # ----------------------------------------------------------------
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Siteye göre kimlik kartını değiştiriyoruz
    if site_tipi == "filmhane":
        headers["Referer"] = "https://filmhane.art/"
    elif site_tipi == "hdfilmizle":
        headers["Referer"] = "https://www.hdfilmizle.life/"

    # ----------------------------------------------------------------
    # ADIM 3: İSTEK VE VİDEO BULMA (Mutfağa girip yemeği alma)
    # ----------------------------------------------------------------
    
    try:
        # Ana sayfaya git
        res = requests.get(url, headers=headers, timeout=10)
        
        # Eğer sayfa açılmazsa (404 veya 403 hatası)
        if res.status_code != 200:
            return None
            
        # YÖNTEM A: Sayfa kaynağında direkt .m3u8 veya .mp4 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')
        
        # YÖNTEM B: Sayfa içindeki iFrame'leri (pencereleri) tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        
        for if_url in iframes:
            # Link eksikse tamamla (//site.com -> https://site.com)
            if if_url.startswith('//'): 
                if_url = "https:" + if_url
            
            # iFrame için de doğru kimliği kullanalım
            # Eğer iframe linki ana siteyle aynıysa aynı referer, farklıysa boş ver.
            if_headers = headers.copy()
            
            try:
                if_res = requests.get(if_url, headers=if_headers, timeout=5)
                # İframe içinde video linki ara
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', if_res.text)
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
    return "Stream API Aktif. V163.0 - Aksaçlı Final."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
