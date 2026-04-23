from flask import Flask, redirect, Response, request
import requests
import re
from urllib.parse import urlparse

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dmax.com.tr/",
    "Origin": "https://www.dmax.com.tr"
}

# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ (ATV & AHABER & GOLD)
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    """TV Kulesi ve zorlu linkler için header maskeleme köprüsü"""
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
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    
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
        return redirect(f"/canli/proxy?url={turkuvaz[kanal]}")

    return "Kanal bulunamadı.", 404

# -----------------------------------------------------------
# 3. YENİ: EVRENSEL ÇÖZÜCÜ (Genişletilmiş Regex ile)
# -----------------------------------------------------------
@app.route('/api')
def resolve_universal():
    target_url = request.args.get('url')
    if not target_url: 
        return "URL eksik. Kullanım: /api?url=...", 400

    parsed_uri = urlparse(target_url)
    domain = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
    
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": domain + "/",
        "Origin": domain
    }

    try:
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        res.encoding = 'utf-8'
        html_content = res.text
        
        # 1. Genişletilmiş m3u8 Taraması (Kaçış karakterlerini temizler)
        m3u8_matches = re.findall(r'["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', html_content)
        if m3u8_matches:
            clean_url = m3u8_matches[0].replace('\\/', '/').replace('\\', '')
            return redirect(clean_url, code=302)

        # 2. Player içi alternatif (file: veya src:)
        alt_match = re.search(r'(?:file|src)\s*:\s*["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', html_content)
        if alt_match:
            clean_url = alt_match.group(1).replace('\\/', '/').replace('\\', '')
            return redirect(clean_url, code=302)

        # 3. İyileştirilmiş Iframe Taraması (Hem src hem data-src destekler)
        iframes = re.findall(r'<iframe[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if not if_url.startswith('http'): continue
            
            try:
                if_res = requests.get(if_url, headers=custom_headers, timeout=5)
                
                # Iframe içi m3u8
                if_m3u8 = re.search(r'["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', if_res.text)
                if if_m3u8:
                    clean_url = if_m3u8.group(1).replace('\\/', '/').replace('\\', '')
                    return redirect(clean_url, code=302)
                
                # Iframe içi alternatif
                if_alt = re.search(r'(?:file|src)\s*:\s*["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', if_res.text)
                if if_alt:
                    clean_url = if_alt.group(1).replace('\\/', '/').replace('\\', '')
                    return redirect(clean_url, code=302)
            except: 
                continue

    except Exception:
        pass

    return "Video kaynağı bulunamadı.", 404

# -----------------------------------------------------------
# 4. ESKİ FİLMHANE SİSTEMİ (Genişletilmiş Regex ile Güncellendi)
# -----------------------------------------------------------
@app.route('/yayin/<dizi>/<bolum>')
def stream_dizi(dizi, bolum):
    base_domain = "https://filmhane.fit" 
    
    sezon_no = "1"
    bolum_no = bolum

    s_match = re.search(r'[sS](\d+)', bolum)
    b_match = re.search(r'[bB](\d+)', bolum)

    if s_match and b_match:
        sezon_no = s_match.group(1)
        bolum_no = b_match.group(1)
    elif b_match:
        bolum_no = b_match.group(1)

    url = f"{base_domain}/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"
    
    films = {
        "28-yil-sonra": f"{base_domain}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base_domain}/film/war-machine",
        "banlieusards-3": f"{base_domain}/film/banlieusards-3",
        "zeta": f"{base_domain}/film/zeta",
        "crime-101": f"{base_domain}/film/crime-101",
        "kagittan-hayatlar": f"{base_domain}/film/kagittan-hayatlar",
        "the-wrecking-crew": f"{base_domain}/film/the-wrecking-crew",
    }
    
    if dizi in films: url = films[dizi]
    
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": f"{base_domain}/"}
        res = requests.get(url, headers=fh_headers, timeout=10)
        html_content = res.text
        
        # 1. Genişletilmiş m3u8 Taraması
        m3u8_matches = re.findall(r'["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', html_content)
        if m3u8_matches:
            clean_url = m3u8_matches[0].replace('\\/', '/').replace('\\', '')
            return redirect(clean_url, code=302)

        # 2. Player içi alternatif
        alt_match = re.search(r'(?:file|src)\s*:\s*["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', html_content)
        if alt_match:
            clean_url = alt_match.group(1).replace('\\/', '/').replace('\\', '')
            return redirect(clean_url, code=302)

        # 3. İyileştirilmiş Iframe Taraması
        iframes = re.findall(r'<iframe[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if not if_url.startswith('http'): continue
            
            try:
                if_res = requests.get(if_url, headers=fh_headers, timeout=5)
                
                if_m3u8 = re.search(r'["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', if_res.text)
                if if_m3u8:
                    clean_url = if_m3u8.group(1).replace('\\/', '/').replace('\\', '')
                    return redirect(clean_url, code=302)
                
                if_alt = re.search(r'(?:file|src)\s*:\s*["\'](https?://[^"\'\s]+\.m3u8[^"\'\s]*)["\']', if_res.text)
                if if_alt:
                    clean_url = if_alt.group(1).replace('\\/', '/').replace('\\', '')
                    return redirect(clean_url, code=302)
            except: 
                continue
    except: pass
    return "Yayın bulunamadı.", 404

# -----------------------------------------------------------
# ANA SAYFA
# -----------------------------------------------------------
@app.route('/')
def home():
    return "Aksaçlı Stream API V162.7 - Filmhane & Canlı TV Active (Genişletilmiş Regex Sürümü)"

if __name__ == '__main__':
    app.run(debug=True)
