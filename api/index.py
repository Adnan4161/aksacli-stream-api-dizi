from flask import Flask, redirect, request
import requests
import re

app = Flask(__name__)

def get_live_link(dizi_adi, bolum):
    # Örnek olarak diziyo.sh üzerinden gidelim
    url = f"https://diziyo.sh/izle/{dizi_adi}-{bolum}-bolum"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        # m3u8 linkini ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')

        # iFrame taraması
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            if_res = requests.get(if_url, headers=headers, timeout=5)
            if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
            if if_match:
                return if_match.group(1).replace('\\', '')
    except:
        return None
    return None

@app.route('/')
def home():
    return "Aksaçlı Stream API Aktif! Kullanım: /yayin/dizi-adi/bolum-no"

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    return "Link bulunamadı Aksaçlı!", 404

def handler(event, context):
    return app(event, context)
