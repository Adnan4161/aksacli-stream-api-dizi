from flask import Flask, redirect
import requests
import re

app = Flask(__name__)

# --- ORTAK AYARLAR ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def scrape_m3u8(target_url, referer_url):
    """
    Verilen URL'e gider, o sitenin Referer'ını kullanarak m3u8 veya mp4 arar.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer_url
    }
    
    try:
        print(f"İstek atılıyor: {target_url} (Ref: {referer_url})")
        res = requests.get(target_url, headers=headers, timeout=10)
        
        if res.status_code != 200:
            return None

        # 1. Direkt Link Arama (.m3u8 veya .mp4)
        # Tırnak işaretleri arasındaki linkleri bulur
        match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', res.text)
        if match:
            return match.group(1).replace('\\', '')

        # 2. iFrame Arama (Video başka bir kutu içindeyse)
        iframes = re.findall(r'<iframe.*?src=["\'](.*?)["\']', res.text)
        for if_url in iframes:
            if if_url.startswith('//'): if_url = "https:" + if_url
            
            # iFrame'in kendi domainine göre referer gerekebilir ama genellikle ana site yeterlidir.
            # Yine de iframe'e giderken de aynı kimliği gösterelim.
            try:
                if_res = requests.get(if_url, headers=headers, timeout=5)
                if_match = re.search(r'["\'](https?://[^\s^"^\']+\.(?:m3u8|mp4)[^\s^"^\']*)["\']', if_res.text)
                if if_match:
                    return if_match.group(1).replace('\\', '')
            except:
                continue

    except Exception as e:
        print(f"Hata oluştu: {e}")
        return None
    
    return None

def get_live_link(dizi_slug, bolum_no):
    
    # -----------------------------------------------------------
    # SENARYO 1: HDfilmizle Sitesinden İstenen Filmler
    # -----------------------------------------------------------
    if dizi_slug == "ucurum-2026":
        url = "https://www.hdfilmizle.life/ucurum-2026/"
        # Bu sitenin kapısından girerken bu kimliği göstereceğiz
        return scrape_m3u8(url, "https://www.hdfilmizle.life/")

    # -----------------------------------------------------------
    # SENARYO 2: Filmhane Sitesinden İstenen Özel Filmler
    # -----------------------------------------------------------
    elif dizi_slug == "28-yil-sonra":
        url = "https://filmhane.art/film/28-yil-sonra-kemik-tapinagi"
        return scrape_m3u8(url, "https://filmhane.art/")

    # -----------------------------------------------------------
    # SENARYO 3: Varsayılan (Standart Diziler - Filmhane)
    # -----------------------------------------------------------
    else:
        # Standart dizi link yapısı
        url = f"https://filmhane.art/dizi/{dizi_slug}/sezon-1/bolum-{bolum_no}"
        return scrape_m3u8(url, "https://filmhane.art/")

@app.route('/')
def home():
    return "Stream API Aktif. V163.5 - Modüler Sistem."

@app.route('/yayin/<dizi>/<bolum>')
def stream(dizi, bolum):
    final_link = get_live_link(dizi, bolum)
    if final_link:
        return redirect(final_link, code=302)
    else:
        return "Kaynak bulunamadı.", 404
