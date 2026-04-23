        if m:
            u = normalize_url(m.group(1), base_url=landing_url)
            if is_http_url(u):
                return u

    return resolve_from_page(landing_url, headers=headers, max_depth=1)


@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Aksacli Stream API V171 - redirect-first quota-safe"


@app.route("/health", methods=["GET", "HEAD"])
def health():
    return {
        "ok": True,
        "cache_items": len(_CACHE),
        "mode": "redirect-first",
        "api_key_enabled": bool(API_KEY),
    }


@app.route("/canli/proxy", methods=["GET", "HEAD"])
def proxy_general():
    g = auth_guard()
    if g:
        return g

    target_url = (request.args.get("url") or "").strip()
    if not target_url:
        return "URL eksik", 400
    if not is_http_url(target_url):
        return "Gecersiz URL", 400
    if not is_proxy_host_allowed(target_url):
        return "Host izinli degil", 403

    return redirect_light(target_url, ttl=SHORT_TTL)


@app.route("/canli/gold.m3u8", methods=["GET", "HEAD"])
def proxy_gold():
    g = auth_guard()
    if g:
        return g
    return redirect_light("https://goldvod.site/live/hpgdisco/123456/266.m3u8", ttl=SHORT_TTL)


@app.route("/canli/sup.m3u8", methods=["GET", "HEAD"])
def proxy_sup():
    g = auth_guard()
    if g:
        return g
    return redirect_light(
        "http://sup-4k.org:80/play/live.php?mac=00:1A:79:56:7A:24&stream=10740&extension=ts",
        ttl=SHORT_TTL,
    )


@app.route("/canli/<kanal>", methods=["GET", "HEAD"])
def stream_canli(kanal: str):
    g = auth_guard()
    if g:
        return g

    kanal = (kanal or "").strip().lower()

    dogus = {
        "dmax": "https://www.dmax.com.tr/canli-izle",
        "tlc": "https://www.tlctv.com.tr/canli-izle",
        "ntv": "https://www.ntv.com.tr/canli-yayin/ntv",
    }

    turkuvaz = {
        "atv": "https://cdn504.tvkulesi.com/atv.m3u8?hst=amp.tvkulesi.com&ch=atv",
        "ahaber": "https://cdn504.tvkulesi.com/ahaber.m3u8?hst=amp.tvkulesi.com&ch=a-haber",
        "aspor": "https://cdn504.tvkulesi.com/aspor.m3u8?hst=amp.tvkulesi.com&ch=a-spor",
    }

    cache_key = f"canli:{kanal}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    if kanal in turkuvaz:
        return redirect_light(turkuvaz[kanal], ttl=SHORT_TTL)

    if kanal in dogus:
        link = fetch_dogus_stream(dogus[kanal])
        if link:
            cache_set(cache_key, link, ttl_sec=60)
            return redirect_light(link, ttl=SHORT_TTL)

    return "Kanal bulunamadi.", 404


@app.route("/api", methods=["GET", "HEAD"])
def resolve_universal():
    g = auth_guard()
    if g:
        return g

    target_url = (request.args.get("url") or "").strip()
    if not target_url:
        return "URL eksik. Kullanim: /api?url=...", 400
    if not is_http_url(target_url):
        return "Gecersiz URL", 400

    cache_key = f"api:{target_url}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=SHORT_TTL)

    dom = origin_of(target_url)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": (dom + "/") if dom else BASE_HEADERS["Referer"],
        "Origin": dom if dom else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_url, headers=headers, max_depth=2)
    if stream_url:
        cache_set(cache_key, stream_url, ttl_sec=NORMAL_TTL)
        return redirect_light(stream_url, ttl=SHORT_TTL)

    return "Video kaynagi bulunamadi.", 404


@app.route("/yayin/<dizi>/<bolum>", methods=["GET", "HEAD"])
def stream_dizi(dizi: str, bolum: str):
    g = auth_guard()
    if g:
        return g

    base = FILMHANE_BASE_DOMAIN

    films = {
        "28-yil-sonra": f"{base}/film/28-yil-sonra-kemik-tapinagi",
        "war-machine": f"{base}/film/war-machine",
        "banlieusards-3": f"{base}/film/banlieusards-3",
        "zeta": f"{base}/film/zeta",
        "crime-101": f"{base}/film/crime-101",
        "kagittan-hayatlar": f"{base}/film/kagittan-hayatlar",
        "the-wrecking-crew": f"{base}/film/the-wrecking-crew",
        "ali-congun-ask-acisi": f"{base}/film/ali-congun-ask-acisi",
        "peaky-blinders-the-immortal-man": f"{base}/film/peaky-blinders-the-immortal-man",
    }

    if dizi in films:
        target_page = films[dizi]
    else:
        sezon_no, bolum_no = parse_episode_token(bolum)
        target_page = f"{base}/dizi/{dizi}/sezon-{sezon_no}/bolum-{bolum_no}"

    # tokenized stream links can expire very quickly; keep cache tiny
    cache_key = f"yayin:{target_page}"
    cached = cache_get(cache_key)
    if cached:
        return redirect_light(cached, ttl=5)

    base_origin = origin_of(base)
    headers = {
        "User-Agent": BASE_HEADERS["User-Agent"],
        "Referer": f"{base}/",
        "Origin": base_origin if base_origin else BASE_HEADERS["Origin"],
    }

    stream_url = resolve_from_page(target_page, headers=headers, max_depth=2)
    if stream_url:
        cache_set(cache_key, stream_url, ttl_sec=5)
        return redirect_light(stream_url, ttl=5)

    return "Yayin bulunamadi.", 404


if __name__ == "__main__":
    app.run(debug=True)
