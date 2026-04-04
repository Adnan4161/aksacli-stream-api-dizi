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
# 1. ÖZEL PROXY SİSTEMLERİ (ATV & AHABER & GOLD)
# -----------------------------------------------------------

@app.route('/canli/proxy')
def proxy_general():
    """TV Kulesi ve benzeri zorlu linkler için header maskeleme köprüsü"""
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
# 3. FİLMHANE SİSTEMİ (DOMAIN: .FIT)
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
    }
    
    if dizi in films: url = films[dizi]
    
    try:
        fh_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": f"{base_domain}/"}
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

# -----------------------------------------------------------
# 4. DİZİPAL SİSTEMİ
# -----------------------------------------------------------
@app.route('/yayin/dizipal/<slug>')
def stream_dizipal(slug):
    base_url = "https://dizipal.im"
    url = f"{base_url}/bolum/{slug}/"
    try:
        dp_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": base_url}
        res = requests.get(url, headers=dp_headers, timeout=10)
        
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\', ''), code=302)
        
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if any(x in if_url for x in ['vidmoly', 'fembed', 'upstream', 'moly', 'dizipal']):
                try:
                    if_res = requests.get(if_url, headers=dp_headers, timeout=5)
                    if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                    if if_match: return redirect(if_match.group(1).replace('\\', ''), code=302)
                except: continue
    except: pass
    return "Dizipal yayını bulunamadı.", 404

# -----------------------------------------------------------
# 5. DİZİYOU SİSTEMİ (YENİ SİSTEM - TR DUBLAJ ODAKLI)
# -----------------------------------------------------------
@app.route('/yayin/diziyou/<slug>')
def stream_diziyou(slug):
    """
    Kullanım: /yayin/diziyou/daredevil-born-again-1-sezon-9-bolum
    """
    base_url = "https://www.diziyou.one"
    url = f"{base_url}/{slug}/"
    try:
        dy_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": base_url}
        res = requests.get(url, headers=dy_headers, timeout=10)
        
        # Sayfa içindeki 'episode_id' veya 'video-id' gibi sayısal kimliği yakala
        # Genellikle JavaScript değişkeni veya data-id olarak bulunur.
        id_match = re.search(r'(?:episode_id|id|data-id)\s*[:=]\s*["\'](\d+)["\']', res.text)
        
        if id_match:
            episode_id = id_match.group(1)
            # Senin verdiğin TR dublaj mantığına göre linki inşa et
            # Örnek: https://storage.diziyou.one/episodes/120409_tr/1080p.m3u8
            final_m3u8 = f"https://storage.diziyou.one/episodes/{episode_id}_tr/1080p.m3u8"
            return redirect(final_m3u8, code=302)
        
        # Eğer yukarıdaki ID bulunamazsa standart m3u8 araması yap
        m3u_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if m3u_match: return redirect(m3u_match.group(1).replace('\\', ''), code=302)
        
    except Exception as e:
        print(f"Diziyou Error: {e}")
        
    return "Diziyou yayını bulunamadı.", 404

# -----------------------------------------------------------
# ANA SAYFA
# -----------------------------------------------------------
@app.route('/')
def home():
    return "Aksaçlı Stream API V184.5 - Diziyou (TR Dublaj) & Filmhane & Dizipal & Turkuvaz Active"

if __name__ == '__main__':
    app.run(debug=True)
