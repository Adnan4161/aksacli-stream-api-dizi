from flask import Flask, redirect, Response
import requests
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.atv.com.tr/",
    "Origin": "https://www.atv.com.tr"
}

# --- CANLI YAYIN ÇÖZÜCÜLER ---
def fetch_dogus(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
    return None

def fetch_turkuvaz(url):
    try:
        # ATV grubu için özel tarayıcı taklidi
        res = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://www.atv.com.tr/"}, timeout=10)
        # Sayfa içindeki gizli m3u8 linkini avla
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            link = match.group(1).replace('\\/', '/')
            if link.startswith('//'): link = "https:" + link
            return link
    except: return None
    return None

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    # Doğuş Grubu
    dogus = {"dmax": "https://www.dmax.com.tr/canli-izle", "tlc": "https://www.tlctv.com.tr/canli-izle", "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"}
    # Turkuvaz Grubu (Sürekli değişen linkler)
    turkuvaz = {
        "atv": "https://www.atv.com.tr/canli-yayin",
        "a2": "https://www.atv.com.tr/a2tv/canli-yayin",
        "ahaber": "https://www.ahaber.com.tr/video/canli-yayin",
        "aspor": "https://www.aspor.com.tr/video/canli-yayin"
    }

    if kanal in dogus:
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
    elif kanal in turkuvaz:
        link = fetch_turkuvaz(turkuvaz[kanal])
        if link: return redirect(link, code=302)
        
    return "Kanal veya yayın bulunamadı.", 404

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    films = {
        "28-yil-sonra": "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": "https://filmhane.art/film/war-machine",
        "banlieusards-3": "https://filmhane.art/film/banlieusards-3",
        "kagittan-hayatlar": "https://filmhane.art/film/kagittan-hayatlar",
        "ali-congun-ask-acisi": "https://filmhane.art/film/ali-congun-ask-acisi",
        "the-wrecking-crew": "https://filmhane.art/film/the-wrecking-crew" # TIRNAK DÜZELTİLDİ
    }
    if dizi in films: url = films[dizi]
    
    try:
        res = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
    except: pass
    return "Yayın bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V181.4 - ATV & Film Archive Active"
