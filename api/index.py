from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

def get_live_link(dizi_slug, bolum_no):
    # 1. Varsayılan URL yapısını belirle (Filmhane Dizileri için)
    # Örnek: https://filmhane.art/dizi/asylum/sezon-1/bolum-1
    url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"

    # 2. ÖZEL DURUMLAR (FİLMLER VE FARKLI SİTELER)
    # Buraya eklediğimiz her yeni film veya site için 'elif' bloğu açacağız.
    
    if dizi_slug == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"

    elif dizi_slug == "ucurum-2026":
        url = "https://www.hdfilmizle.life/ucurum-2026/"

    # --- Başka özel diziler veya filmler buraya eklenebilir ---
    
    # 3. KİMLİK (HEADER) AYARLARI
    # Varsayılan olarak Filmhane kimliğiyle başlıyoruz
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://filmhane.art/"
    }
    
    # EĞER url içinde "hdfilmizle.life" geçiyorsa, kimliği ona göre değiştir!
    if "hdfilmizle.life" in url:
        headers["Referer"] = "https://www.hdfilmizle.life/"
    
    try:
        # Belirlenen URL'e istek at
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return None
            
        # 1. Yöntem: Sayfa içinde direkt m3u8 ara
        match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')
        
        # 2. Yöntem: iFrame/Script içindeki linkleri tara
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # iFrame tararken de doğru kimliği (headers) kullanmak önemli
            try:
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.m3u8[^\s^"^\']*)["\']', if_res.text)
                if if_match:
                    return if_match.group(1).replace('\\', '')
            except:
                continue
    except Exception as e:
        print(f"Hata: {e}")
        return None
    return None

@app.route('/')
def home():
    return "Stream API Aktif. V162.6 - Aksaçlı Edt."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Taze link bulunamadı. Site yapısı değişmiş veya video silinmiş olabilir.", 404
