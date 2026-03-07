from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- DERİN TARAYICI KİMLİĞİ ---
# Sitenin bizi bot olarak görmemesi için tam teşekküllü headers seti
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

# -----------------------------------------------------------
# MOTOR: ANTI-BLOCK YAYIN AYIKLAYICI
# -----------------------------------------------------------
def fetch_protected_media(url, referer_url):
    try:
        # requests.Session kullanarak çerez (cookie) takibi yapıyoruz, bot engelini aşmak için şarttır
        session = requests.Session()
        headers = BROWSER_HEADERS.copy()
        headers["Referer"] = referer_url
        
        # İlk istek: Sayfayı ve çerezleri al
        res = session.get(url, headers=headers, timeout=12)
        if res.status_code != 200: return None
        
        # 1. Standart m3u8 linkini ara
        # 2. Kaçış karakterli (https:\/\/...) linkleri de yakalayacak geliştirilmiş Regex
        regex_list = [
            r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']',
            r'videoSrc\s*:\s*["\'](.*?)["\']',
            r'src\s*:\s*["\'](.*?\.m3u8.*?)["\']'
        ]
        
        for pattern in regex_list:
            match = re.search(pattern, res.text)
            if match:
                clean_link = match.group(1).replace('\\/', '/').replace('\\', '')
                # Eğer link // ile başlıyorsa protokol ekle
                if clean_link.startswith('//'): clean_link = "https:" + clean_link
                return clean_link

    except Exception as e:
        print(f"Sistem Hatası: {e}")
        return None
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ (CANLI TV)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    target_url = ""
    ref = "https://www.google.com/" # Güvenli başlangıç refererı
    
    if kanal == "dmax":
        target_url = "https://www.dmax.com.tr/canli-izle"
        ref = "https://www.dmax.com.tr/"
    elif kanal == "tlc":
        target_url = "https://www.tlctv.com.tr/canli-izle"
        ref = "https://www.tlctv.com.tr/"
    elif kanal == "ntv":
        target_url = "https://www.ntv.com.tr/canli-yayin/ntv"
        ref = "https://www.ntv.com.tr/"
    elif kanal == "atv":
        # ATV Iframe linki
        target_url = "https://www.atv.com.tr/iframe/canli-yayin"
        ref = "https://www.atv.com.tr/"

    if target_url:
        final_link = fetch_protected_media(target_url, ref)
        if final_link:
            return redirect(final_link, code=302)
    
    return f"{kanal} yayını şu an engellendi veya bulunamadı.", 404

# -----------------------------------------------------------
# FİLM/DİZİ MOTORU (FİLMHANE) - Mevcut yapı korundu
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Filmhane linkleri için mevcut mantık...
    # (Buradaki kodun geri kalanını önceki versiyondaki gibi bırakabilirsin)
    return "Filmhane motoru aktif", 200

@app.route('/')
def home():
    return "Aksaçlı Stream API V182.0 - Deep Browser Mimicry Aktif"
