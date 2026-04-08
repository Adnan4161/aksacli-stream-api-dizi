from flask import Flask, redirect, Response, request
import requests
import re

app = Flask(__name__)

# --- STABİL HEADERS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.canlitv.diy/"
}

# -----------------------------------------------------------
# YABAN TV ÖZEL ÇEKİCİ (V2 - canlitv.diy)
# -----------------------------------------------------------
def fetch_yaban_new():
    target_url = "https://www.canlitv.diy/yaban-tv?kat=belgesel"
    try:
        # 1. Ana sayfayı çek
        res = requests.get(target_url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8' # Türkçe karakter sorunu olmasın
        
        # 2. Sayfa içinde m3u8 ara (Daha geniş kapsamlı regex)
        # Genellikle "file: '...m3u8'" veya "source: '...m3u8'" şeklinde olur
        match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match:
            return match.group(1).replace('\\/', '/')

        # 3. Eğer bulamazsa, iframe içinde ara
        iframe_match = re.search(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        if iframe_match:
            if_url = iframe_match.group(1)
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # Iframe'e giderken referer olarak ana siteyi gösterelim
            if_headers = HEADERS.copy()
            if_headers["Referer"] = target_url
            
            if_res = requests.get(if_url, headers=if_headers, timeout=5)
            if_match = re.search(r'["\'](https?://[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', if_res.text)
            if if_match:
                return if_match.group(1).replace('\\/', '/')
                
        # 4. Son çare: "fun" veya "stream" kelimelerini içeren linkleri tara
        stream_match = re.search(r'source\s*:\s*["\'](http[^\s"\'<>]*?)["\']', res.text)
        if stream_match:
            return stream_match.group(1).replace('\\/', '/')

    except Exception as e:
        print(f"Hata: {e}")
    return None

# -----------------------------------------------------------
# 1. ÖZEL PROXY SİSTEMLERİ
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

# -----------------------------------------------------------
# 2. CANLI TV ROUTER
# -----------------------------------------------------------
@app.route('/canli/<kanal>')
def stream_canli(kanal):
    if kanal == "yabantv":
        link = fetch_yaban_new()
        if link:
            # Vercel loglarında linki görmek için (opsiyonel)
            print(f"Bulunan Link: {link}")
            return redirect(link, code=302)
        return "Yaban TV linki bu sitede de bulunamadı.", 404

    # --- Diğer kanallar (Dmax, TLC vb. aynı kalıyor) ---
    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv"
    }
    if kanal in dogus:
        # (fetch_dogus fonksiyonu burada olmalı veya global tanımlanmalı)
        res = requests.get(dogus[kanal], headers=HEADERS, timeout=10)
        match = re.search(r'["\'](https?:?\\?/\\?/[^\s"\'<>]*?daioncdn[^\s"\'<>]*?\.m3u8[^\s"\'<>]*?)["\']', res.text)
        if match: return redirect(match.group(1).replace('\\/', '/'), code=302)

    return "Kanal bulunamadı.", 404

@app.route('/')
def home():
    return "Aksaçlı Stream API V188.0 - canlitv.diy mod active"

if __name__ == '__main__':
    app.run(debug=True)
