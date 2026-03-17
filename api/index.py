from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}

# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ (ATV & AHABER BURADA)
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    """TV Kulesi ve benzeri zorlu linkler için header maskeleme köprüsü"""
    target_url = request.args.get('url')
    if not target_url: return "URL eksik", 400
    
    # TV Kulesi'nin istediği özel kimlik bilgileri
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://amp.tvkulesi.com/",
        "Origin": "https://amp.tvkulesi.com"
    }
    
    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        # Yayını alıp Net TV'nin anlayacağı CORS izinleriyle geri gönderiyoruz
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except:
        return redirect(target_url)

@app.route('/canli/gold.m3u8')
def proxy_gold():
    url = "https://goldvod.site/live/hpgdisco/123456/266.m3u8"
    try:
        res = requests.get(url, headers={"User-Agent": "VLC/3.0.18 LibVLC/3.0.18"}, timeout=10)
        return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})
    except: return redirect(url)

@app.route('/canli/sup.m3u8')
def proxy_sup():
    url = "http://sup-4k.org:80/play/live.php?mac=00:1A:79:56:7A:24&stream=10740&extension=ts"
    return Response("", status=302, headers={'Location': url, 'Access-Control-Allow-Origin': '*', 'X-Content-Type-Options': 'nosniff'})

# -----------------------------------------------------------
# 2. STANDART CANLI TV (DMAX, TLC, NTV, ATV, AHABER)
# -----------------------------------------------------------
def fetch_dogus(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
    return None

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    # Doğuş Grubu (Dinamik)
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    
    # Turkuvaz Grubu (Proxy Üzerinden Sabit Linkler)
    # Not: Tokenlar patlarsa TV Kulesi'nden yenileriyle güncellenebilir
    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber",
        "aspor": "https://cdn504.tvkulesi.com/aspor.m3u8?hst=amp.tvkulesi.com&ch=a-spor"
    }

    if kanal in dogus:
        HEADERS["Referer"] = dogus[kanal].replace("canli-izle", "")
        link = fetch_dogus(dogus[kanal])
        if link: return redirect(link, code=302)
        
    if kanal in turkuvaz:
        # Linki kendi proxy köprümüze sokuyoruz
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# 3. FİLM & DİZİ SİSTEMİ
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    films = {
        "28-yil-sonra": "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": "https://filmhane.art/film/war-machine",
        "banlieusards-3": "https://filmhane.art/film/banlieusards-3",
        "kagittan-hayatlar": "https://filmhane.art/film/kagittan-hayatlar",
        "ali-congun-ask-acisi": "https://filmhane.art/film/ali-congun-ask-acisi",
        "the-wrecking-crew": "https://filmhane.art/film/the-wrecking-crew", # DÜZELTİLDİ
    }
    
    if dizi in films: url = films[dizi]
    
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
        res = requests.get(url, headers=fh_headers, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
        
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            try:
                if_res = requests.get(if_url, headers=fh_headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match: return redirect(if_match.group(1).replace('\\', ''), code=302)
            except: continue
    except: pass
    return "Yayın bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V181.5 - Turkuvaz Proxy & Film Archive Active"
