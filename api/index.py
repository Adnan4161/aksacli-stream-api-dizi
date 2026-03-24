from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- GÜÇLENDİRİLMİŞ HEADERS ---
# Turkuvaz Grubu bazen çok spesifik bir UA bekleyebilir
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# -----------------------------------------------------------
# 1. TURKUVAZ ÖZEL ÇEKİCİ (A HABER, ATV, A SPOR)
# -----------------------------------------------------------

def fetch_turkuvaz(url):
    """Sıkı güvenlikli Turkuvaz iframe'lerinden m3u8 yakalar"""
    try:
        session = requests.Session() # Çerezleri yönetmek için session başlattık
        
        # Ana site referansını ekliyoruz (Önemli!)
        main_domain = "https://www.ahaber.com.tr/"
        if "atv" in url: main_domain = "https://www.atv.com.tr/"
        elif "aspor" in url: main_domain = "https://www.aspor.com.tr/"
        
        local_headers = HEADERS.copy()
        local_headers["Referer"] = main_domain
        
        # Önce iframe'e gidiyoruz
        res = session.get(url, headers=local_headers, timeout=12)
        
        # HTML içinde m3u8 arıyoruz (Farklı yazım türlerini de kapsar)
        # Regex: Tırnaklar arasındaki, içinde daioncdn ve .m3u8 geçen her şeyi alır
        match = re.search(r'["\'](https?[:\\]+[^"\'\s<>]+?daioncdn[^"\'\s<>]+?\.m3u8[^"\'\s<>]*?)["\']', res.text)
        
        if match:
            raw_link = match.group(1)
            # Ters bölüleri ve kaçış karakterlerini temizle
            clean_link = raw_link.replace('\\/', '/').replace('\\', '')
            return clean_link
            
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return None
    return None

# -----------------------------------------------------------
# 2. DOĞUŞ ÖZEL ÇEKİCİ (NTV, DMAX, TLC)
# -----------------------------------------------------------

def fetch_dogus(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
    return None

# -----------------------------------------------------------
# 3. ANA YÖNLENDİRİCİ
# -----------------------------------------------------------

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    # Doğuş Linkleri
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    
    # Turkuvaz İframe Linkleri
    turkuvaz = {
        "ahaber": "https://www.ahaber.com.tr/iframe/canli-yayin",
        "atv": "https://www.atv.com.tr/iframe/canli-yayin",
        "aspor": "https://www.aspor.com.tr/iframe/canli-yayin",
        "a2": "https://www.a2tv.com.tr/iframe/canli-yayin"
    }

    if kanal in dogus:
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
        
    if kanal in turkuvaz:
        link = fetch_turkuvaz(turkuvaz[kanal])
        if link: return redirect(link, code=302)

    return f"Hata: {kanal} yayını şu an çekilemiyor. Lütfen sonra tekrar dene.", 404

# -----------------------------------------------------------
# 4. DİZİ SİSTEMİ (S1B5)
# -----------------------------------------------------------

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    sezon_no = "1"
    bolum_no = bolum
    s_match = re.search(r'[sS](\d+)', bolum)
    b_match = re.search(r'[bB](\d+)', bolum)
    if s_match and b_match:
        sezon_no = s_match.group(1)
        bolum_no = b_match.group(1)
    elif b_match:
        bolum_no = b_match.group(1)

    url = f"https://filmhane.art/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
        res = requests.get(url, headers=fh_headers, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
    except: pass
    return "Yayın bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V181.8 - Stealth Turkuvaz Active"

if __name__ == '__main__':
    app.run(debug=True)
