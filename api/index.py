from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.yabantv.com/"
}

def fetch_yaban():
    broadcast_url = "https://www.yabantv.com/broadcast"
    try:
        res = requests.get(broadcast_url, headers=HEADERS, timeout=10)
        
        # DEBUG: Eğer Cloudflare veya engel varsa HTTP koduna bakalım
        if res.status_code != 200:
            return f"Hata: Siteye girilemedi (Kod: {res.status_code})"

        # 1. Ham m3u8 ara (Daha esnek regex)
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')
            
        # 2. Iframe içinde m3u8 ara
        iframe_match = re.search(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        if iframe_match:
            if_url = iframe_match.group(1)
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # Iframe referer'ını kendisi yapalım
            if_headers = HEADERS.copy()
            if_headers["Referer"] = broadcast_url
            
            if_res = requests.get(if_url, headers=if_headers, timeout=5)
            if_match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', if_res.text)
            if if_match:
                return if_match.group(1).replace('\\/', '/')
        
        return "Hata: Sayfada m3u8 linki bulunamadı."
    except Exception as e:
        return f"Hata: {str(e)}"

@app.route('/canli/<kanal>')
def stream_canli(kanal):
    if kanal == "yabantv":
        link = fetch_yaban()
        if link.startswith("http"): # Eğer link geldiyse yönlendir
            return redirect(link, code=302)
        else: # Hata mesajı geldiyse ekrana yaz
            return link, 500
    return "Kanal bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API Active"

if __name__ == '__main__':
    app.run(debug=True)
