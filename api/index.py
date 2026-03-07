from flask import Flask, redirect, Response
import requests
import re

app = Flask(__name__)

# --- ELİT TARAYICI KİMLİĞİ (FULL SET) ---
# ATV'nin 'Gerçek İnsan' olduğumuza inanması için gereken tüm donanım
CHROME_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
}

# -----------------------------------------------------------
# MOTOR: ULTRA YAYIN AYIKLAYICI (PERSISTENT SESSION)
# -----------------------------------------------------------
def fetch_final_stream(url, ref):
    try:
        # Session kullanarak çerez ve oturum takibini zorunlu kılıyoruz
        session = requests.Session()
        session.headers.update(CHROME_HEADERS)
        session.headers.update({"Referer": ref, "Origin": "https://www.atv.com.tr"})

        # 1. Adım: Sayfayı derinlemesine tarıyoruz
        res = session.get(url, timeout=15)
        if res.status_code != 200: return None
        
        # 2. Adım: Karmaşık ve gizlenmiş m3u8 yollarını yakalamak için çoklu Regex
        # ATV bazen linki 'src' içinde, bazen 'hls' değişkeni içinde saklar
        patterns = [
            r'["\'](https?[:\\]+[/\\/]+[^"\'\s<>]+?\.m3u8[^"\'\s<>]*?)["\']',
            r'file\s*:\s*["\'](.*?)["\']',
            r'source\s*:\s*["\'](.*?)["\']'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, res.text)
            if match:
                # Linkteki kaçış karakterlerini (\) ve gereksiz boşlukları temizle
                raw_url = match.group(1)
                clean_url = raw_url.replace('\\/', '/').replace('\\', '').strip()
                
                # Protokol kontrolü
                if clean_url.startswith('//'): clean_url = "https:" + clean_url
                
                # Sadece geçerli bir URL ise döndür
                if clean_url.startswith('http'):
                    return clean_url

    except Exception as e:
        print(f"Hata detayı: {e}")
    return None

# -----------------------------------------------------------
# YÖNLENDİRME MERKEZİ
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    target = ""
    referer = "https://www.google.com/"
    
    if kanal == "atv":
        target = "https://www.atv.com.tr/iframe/canli-yayin"
        referer = "https://www.atv.com.tr/"
    elif kanal == "dmax":
        target = "https://www.dmax.com.tr/canli-izle"
        referer = "https://www.dmax.com.tr/"
    elif kanal == "tlc":
        target = "https://www.tlctv.com.tr/canli-izle"
        referer = "https://www.tlctv.com.tr/"
    elif kanal == "ntv":
        target = "https://www.ntv.com.tr/canli-yayin/ntv"
        referer = "https://www.ntv.com.tr/"

    if target:
        stream_link = fetch_final_stream(target, referer)
        if stream_link:
            # 302 Yönlendirmesi yerine bazen 301 veya doğrudan yanıt gerekebilir
            return redirect(stream_link, code=302)
            
    return f"Hata: {kanal} yayını şu an koruma altında (IP Block).", 404

# --- FİLM VE DİZİ AYIKLAYICI (FİLMHANE) ---
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # (Buradaki mevcut Filmhane kodunu önceki çalışan haliyle bırakabilirsin)
    # War Machine ve Banlieusards 3 için olan elif bloklarını koru!
    return "Film/Dizi sistemi aktif", 200

@app.route('/')
def home():
    return "Aksaçlı Stream API V182.5 - Final Strike Ready"
