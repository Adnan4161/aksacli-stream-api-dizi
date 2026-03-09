from flask import Flask, redirect, Response
import requests
import re

app = Flask(__name__)

# --- TARAYICI AYARLARI ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}

# -----------------------------------------------------------
# MOTOR: CORS BYPASS PROXY (GOLDVOD İÇİN ÖZEL)
# -----------------------------------------------------------
@app.route('/canli/gold')
def proxy_gold():
    url = "https://goldvod.site/live/hpgdisco/123456/266.m3u8"
    try:
        # Vercel içeriği kendi üzerine alıyor
        res = requests.get(url, headers=HEADERS, timeout=15)
        
        # İçeriği 'CORS İzinli' olarak senin uygulamana paketleyip fırlatıyor
        return Response(
            res.content,
            mimetype='application/vnd.apple.mpegurl',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Cache-Control': 'no-cache'
            }
        )
    except Exception as e:
        return f"Proxy Hatası: {e}", 500

# -----------------------------------------------------------
# DİĞER KANALLAR VE DİZİLER (V180.5 STABİL YAPI KORUNDU)
# -----------------------------------------------------------
def fetch_dogus_media(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return match.group(1).replace('\\/', '/')
    except: return None
    return None

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    target_url = ""
    if kanal == "dmax": target_url = "https://www.dmax.com.tr/canli-izle"
    elif kanal == "tlc": 
        target_url = "https://www.tlctv.com.tr/canli-izle"
        HEADERS["Referer"] = "https://www.tlctv.com.tr/"
    elif kanal == "ntv":
        target_url = "https://www.ntv.com.tr/canli-yayin/ntv"
        HEADERS["Referer"] = "https://www.ntv.com.tr/"

    if target_url:
        final_link = fetch_dogus_media(target_url)
        if final_link: return redirect(final_link, code=302)
    return "Yayın bulunamadı.", 404

@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    # Senin meşhur dizi listeni buraya (V180.5'teki gibi) ekleyebilirsin
    url = f"https://filmhane.art/dizi/{dizi}/sezon-1/bolum-{bolum}"
    if dizi == "28-yil-sonra": url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
    elif dizi == "war-machine": url = "https://filmhane.art/film/war-machine"
    elif dizi == "banlieusards-3": url = "https://filmhane.art/film/banlieusards-3"
    elif dizi == "young-sherlock": url = f"https://filmhane.art/dizi/young-sherlock/sezon-1/bolum-{bolum}"
    elif dizi == "a-knight-of-the-seven-kingdoms": url = f"https://filmhane.art/dizi/a-knight-of-the-seven-kingdoms/sezon-1/bolum-{bolum}"
    
    headers_fh = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://filmhane.art/"}
    try:
        res = requests.get(url, headers=headers_fh, timeout=10)
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
    except: pass
    return "Kaynak bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V180.9 - Full Proxy Mode Active"
