from flask import Flask, redirect, Response, request
import requests
import re
from urllib.parse import urlparse

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@app.route('/api')
def resolve_universal():
    target_url = request.args.get('url')
    if not target_url: return "URL eksik", 400

    # Dinamik Domain & Referer Tespiti
    parsed_uri = urlparse(target_url)
    domain = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
    
    custom_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": domain + "/",
        "Origin": domain
    }

    try:
        # 1. Ana sayfayı tara
        res = requests.get(target_url, headers=custom_headers, timeout=10)
        res.encoding = 'utf-8'
        
        # Sayfada m3u8 ara (Regex geliştirildi)
        m3u8_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if m3u8_match:
            return redirect(m3u8_match.group(1).replace('\\', ''), code=302)

        # 2. Iframe (Oynatıcı) içini tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if not if_url.startswith('http'): continue
            
            try:
                if_res = requests.get(if_url, headers=custom_headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match:
                    return redirect(if_match.group(1).replace('\\', ''), code=302)
            except: continue

    except Exception as e:
        return f"Hata: {str(e)}", 500

    return "Video bulunamadı.", 404

# --- Canlı TV Proxy ve Diğer Rotalar (Eski kodundaki gibi kalsın) ---
@app.route('/canli/proxy')
def proxy_general():
    target_url = request.args.get('url')
    custom_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://amp.tvkulesi.com/"}
    res = requests.get(target_url, headers=custom_headers, timeout=10)
    return Response(res.content, mimetype='application/vnd.apple.mpegurl', headers={'Access-Control-Allow-Origin': '*'})

@app.route('/')
def home(): return "Aksaçlı Stream API V162.9 Active"

if __name__ == '__main__':
    app.run(debug=True)
