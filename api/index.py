from flask import Flask, redirect, Response, request
import requests
import re
from urllib.parse import urlparse

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# -----------------------------------------------------------
# 1. UNIVERSAL RESOLVER (FİLMHANE .INK & .FIT ÇÖZÜCÜ)
# -----------------------------------------------------------

@app.route('/api')
def resolve_universal():
    """Gelen herhangi bir URL'den m3u8 linkini ayıklar"""
    target_url = request.args.get('url')
    if not target_url: 
        return "URL parametresi eksik. Kullanım: /api?url=TARGET_URL", 400

    # Dinamik Referer Belirleme
    parsed_uri = urlparse(target_url)
    domain = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)
    
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": domain + "/",
        "Origin": domain
    }

    try:
        # 1. Ana sayfayı tara
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        res.encoding = 'utf-8'
        
        # Sayfada direkt m3u8 ara
        m3u8_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if m3u8_match:
            return redirect(m3u8_match.group(1).replace('\\', ''), code=302)

        # 2. Eğer bulamazsa Iframe'leri tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if not if_url.startswith('http'): continue # geçersiz linkleri atla
            
            try:
                # Oynatıcı iframe'ine gir
                if_res = requests.get(if_url, headers=custom_headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match:
                    return redirect(if_match.group(1).replace('\\', ''), code=302)
            except:
                continue

        # 3. Hala bulunamadıysa (Alternatif regex denemesi)
        alt_match = re.search(r'file:\s*["\'](.*?\.m3u8.*?)["\']', res.text)
        if alt_match:
            return redirect(alt_match.group(1).replace('\\', ''), code=302)

    except Exception as e:
        return f"Hata oluştu: {str(e)}", 500

    return "Video kaynağı bulunamadı.", 404

# -----------------------------------------------------------
# 2. ÖZEL PROXY SİSTEMLERİ (TV Kulesi, Gold, Sup)
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    if not target_url: return "URL eksik", 400
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://amp.tvkulesi.com/",
        "Origin": "https://amp.tvkulesi.com"
    }
    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
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

# -----------------------------------------------------------
# 3. CANLI TV KANALLARI (DMAX, TLC, NTV, ATV)
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber"
    }
    if kanal in dogus:
        try:
            res = requests.get(dogus[kanal], headers=HEADERS, timeout=10)
            match = re.search(r'["\'](https?:?//[^"\'<>]*?daioncdn[^"\'<>]*?\.m3u8[^"\'<>]*?)["\']', res.text)
            if match: return redirect(match.group(1).replace('\\/', '/'), code=302)
        except: pass
    if kanal in turkuvaz:
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")
    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# ANA SAYFA
# -----------------------------------------------------------
@app.route('/')
def home():
    return "Aksaçlı Stream API V162.9 - Universal Filmhane & TV Active"

if __name__ == '__main__':
    app.run(debug=True)
