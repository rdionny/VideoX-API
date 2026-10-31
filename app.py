# -*- coding: utf-8 -*-
"""
API XVIDEOS para app Android
Serve em http://<host>:3778

Endpoints:
  GET /                    -> home HTML da API
  GET /docs                -> documentacao completa (HTML)
  GET /style.css           -> estilo das paginas HTML
  GET /info                -> info da API + rotas (JSON)
  GET /videos              -> lista de videos (titulo, capa, url da pagina)
       ?source=home|search|category|tag|user   (padrao: home)
       ?q=<termo ou slug>     (obrigatorio p/ search/tag/user)
       ?page=<n>              (padrao: 1; sem pagina na home)
       ?count=<n>             (opcional, limita itens por resposta)
  GET /video/<slug>        -> tela de detalhes (inclui "hls" = master m3u8 adaptativo)
  GET /categories          -> lista de categorias disponiveis
"""
import html as html_mod
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, Response, jsonify, request
from urllib.parse import quote

BASE = "https://www.xvideos.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 25
CACHE_TTL = int(os.environ.get("API_X_CACHE_TTL", "60"))  # segundos

app = Flask(__name__)

cache = {}
cache_lock = threading.Lock()
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en"})


class FetchError(Exception):
    def __init__(self, code):
        super().__init__(str(code))
        self.code = code


def fetch(url, nocache=False):
    """GET com cache em memoria por URL."""
    now = time.time()
    if not nocache:
        with cache_lock:
            hit = cache.get(url)
            if hit and now - hit[1] < CACHE_TTL:
                return hit[0]
    r = session.get(url, timeout=TIMEOUT)
    if r.status_code != 200:
        raise FetchError(r.status_code)
    text = r.text
    print("FETCH %s status=%s len=%d thumb=%d" % (url[:60], r.status_code, len(text), text.count("thumb-block")), flush=True)
    with cache_lock:
        cache[url] = (text, now)
        if len(cache) > 200:
            oldest = sorted(cache.items(), key=lambda kv: kv[1][1])[:50]
            for k, _ in oldest:
                cache.pop(k, None)
    return text


def s(text):
    """Unescape de entidades HTML."""
    return html_mod.unescape(text)


def meta(html, prop):
    m = re.search(r'<meta property="%s" content="([^"]*)"' % re.escape(prop), html)
    return s(m.group(1)) if m else None


def ld_json(html):
    m = re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def duration_seconds(iso):
    """PT10M21S -> 621"""
    if not iso:
        return None
    m = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?', iso)
    if not m:
        return None
    return int(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0))


def parse_views_html(html):
    m = re.search(r'id="v-views".*?<strong class="mobile-hide">([\d.,]+)([KkMm])?</strong>', html, re.S)
    if not m:
        return None
    t = m.group(1).strip()
    suf = (m.group(2) or "").lower()
    mult = 1
    if suf == "k":
        mult = 1000
    elif suf == "m":
        mult = 1_000_000
    # o site usa "," como separador de milhar (ex.: 23,673) ou decimal (ex.: 23,5)
    if re.fullmatch(r"\d{1,3}(?:\.\d+)?(?:,\d{3})+", t):
        t = t.replace(",", "").replace(".", "")
    else:
        t = t.replace(",", ".")
    try:
        return int(float(t) * mult)
    except ValueError:
        return None


def mp4_urls(html):
    urls = {}
    # some ocorrencias tem lixo de concatenacao JS apos o secure ('), ');
    for u in re.findall(r'https?://mp4-cdn[^"\s<>\'\\]+\?secure=[^"\s<>\'\\)\]]+', html):
        base = u.split("?")[0]
        q = base.rsplit("/", 1)[-1].replace(".mp4", "").replace("mp4_", "")
        urls.setdefault(q, u)
    if not urls:
        m = re.search(r'"url"\s*:\s*"(https?://mp4-cdn[^"]+)"', html)
        if m:
            urls["sd"] = m.group(1)
    return urls


def hls_url(html):
    """Master playlist HLS (m3u8) do player do site (adaptativo)."""
    marker = "setVideoHLS('"
    i = html.find(marker)
    if i >= 0:
        j = html.find("'", i + len(marker))
        if j > i:
            return html[i + len(marker):j]
    m = re.search(r"https?://hls-cdn\S+\.m3u8", html)
    if m:
        return m.group(0)
    return None


def quality_label(html):
    m = re.search(r'<span class="video-hd-mark">([^<]+)</span>', html)
    return m.group(1).strip() if m else None


def embed_json(html):
    """JSON embutido no player com uploader/tags/modelos."""
    i = html.find('{"action":"video"')
    if i < 0:
        return {}
    start = i  # i ja aponta para a chave inicial do objeto
    depth, end, in_str, esc = 0, None, False, False
    for k in range(start, min(start + 300000, len(html))):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
    try:
        return json.loads(html[start:end])
    except Exception:
        return {}


def build_video(ld, e, html):
    slug = e.get("encoded_id_video") or ld.get("encoded_id_video")
    page_url = ld.get("url") or meta(html, "og:url")
    if not slug and page_url:
        m = re.search(r"/video\.([a-z0-9]+)", page_url)
        if m:
            slug = m.group(1)
    thumbs = []
    for t in (ld.get("thumbnailUrl") or []):
        if t not in thumbs:
            thumbs.append(t)
    # o JSON-LD pode trazer a versao _t. (thumb); prefere a imagem completa na capa
    def thumb_full(t):
        t = t.split("?")[0]
        return t.replace("_t.", ".")
    if thumbs:
        capa = thumb_full(thumbs[0])
    else:
        capa = None
    views = (ld.get("interactionStatistic") or {}).get("userInteractionCount")
    views = int(views) if isinstance(views, (int, float)) else None
    views_html = parse_views_html(html)

    # uploader (nome completo vindo do HTML, slug vindo do JSON)
    up_name = None
    m = re.search(r'class="main-uploader".*?<span class="name">\s*<span class="icon-f icf-device-tv-v2"></span>\s*(?:\[[^\]]*\]\s*)?([^<]+?)</span>', html, re.S)
    if m:
        up_name = s(m.group(1)).strip()
    up_url = e.get("uploader_url")

    # modelos
    models = []
    for v in (e.get("video_models") or {}).values():
        if isinstance(v, dict) and v.get("uri"):
            models.append({"name": v.get("name"), "url": BASE.rstrip("/") + v["uri"]})

    def clean(x):
        return html_mod.unescape(html_mod.unescape(str(x or "").replace("&period;", "."))).strip()

    title = clean(ld.get("name")) or clean(meta(html, "og:title"))
    desc = clean(ld.get("description"))

    # tags: fonte primaria e o JSON embutido; fallback para meta name=description
    tags = [clean(t) for t in (e.get("video_tags") or []) if clean(t)]
    if not tags:
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        if m and "," in m.group(1):
            body = m.group(1)
            if body.upper().startswith("XVIDEOS "):
                body = body[len("XVIDEOS "):]
            # remove sufixo ' free' e pega a parte apos o titulo
            body = re.sub(r"\s*free\s*$", "", body, flags=re.I)
            cand = body.split(",", 1)[-1] if body.count(",") else ""
            for t in cand.split(","):
                t = clean(t)
                if len(t) >= 2 and t not in tags:
                    tags.append(t)

    # categorias especificas do video (nem toda pagina as expoe no HTML; sope o melhor esforco)
    cats = []
    seen = set()
    for cm in re.finditer(r'<a href="(/c/[A-Za-z0-9-]+-\d+)"[^>]*class="[^"]*video-cats?[^"]*"[^>]*>\s*([^<]{2,40})\s*<', html):
        name = clean(cm.group(2))
        key = cm.group(1)
        if name and key not in seen:
            seen.add(key)
            cats.append({"name": name, "url": BASE + key})

    upload = ld.get("uploadDate")
    try:
        upload_iso = datetime.fromisoformat(upload).astimezone(timezone.utc).isoformat() if upload else None
    except ValueError:
        upload_iso = upload

    # garante slug a partir da URL caso falte
    if not slug and page_url:
        mm = re.search(r"/video\.([a-z0-9]+)", page_url)
        if mm:
            slug = mm.group(1)

    return {
        "slug": slug,
        "id": e.get("id_video") or ld.get("id_video"),
        "titulo": title,
        "descricao": desc,
        "url_pagina": page_url,
        "capa": capa,
        "capas": thumbs,
        "duranca_seg": duration_seconds(ld.get("duration")),
        "duranca_texto": ld.get("duration"),
        "visualizacoes": views_html if views_html is not None else views,
        "data_publicacao": upload_iso,
        "qualidade": quality_label(html),
        "reproducao": mp4_urls(html),
        "hls": hls_url(html),
        "uploader": {
            "nome": up_name,
            "usuario": e.get("uploader"),
            "url": (BASE.rstrip("/") + up_url) if up_url else None,
        },
        "modelos": models,
        "tags": tags,
        "categorias": cats,
    }


def _clean_thumb(urls):
    """Escolhe a capa do bloco: prefere thumbnail _t. sem query string."""
    clean = [u.split("?")[0] for u in urls]
    for u in clean:
        if "_t." in u:
            return u
    return clean[-1] if clean else None


def parse_list(html, count=None):
    """Extrai a lista de videos dos blocos thumb-block (home, busca,
    categoria e tag). O site tem duas variacoes A/B de layout: em uma o
    link da lista e /video.<slug>/...; na outra e /search-video/<token>,
    onde o slug so aparece em data-eid da tag do bloco."""
    limit = int(count) if count else None
    out = []
    seen = set()
    tags = list(re.finditer(r'<div\b[^>]*\bthumb-block\b[^>]*>', html))
    for n, mtag in enumerate(tags):
        start = mtag.start()
        end = tags[n + 1].start() if n + 1 < len(tags) else min(start + 20000, len(html))
        b = html[start:end]
        head = mtag.group(0)
        tm = re.search(r'<p class="title">\s*<a href="([^"]+)"\s+title="([^"]*)"', b)
        if not tm:
            continue
        url = tm.group(1)
        sm = re.search(r"/video\.([a-z0-9]+)", url)
        if sm:
            slug = sm.group(1)
            page_rel = url
        else:
            em = re.search(r'data-eid="([a-z0-9]+)"', head)
            if not em:
                continue
            slug = em.group(1)
            page_rel = "/video." + slug + "/x"
        if slug in seen:
            continue
        seen.add(slug)
        dm = re.search(r'class="duration">([^<]+)<', b)
        hd = re.findall(r'class="video-hd-mark">([^<]+)<', b)
        tms = re.findall(r'(?:data-src|data-src-avif|src)="(https?://thumb-cdn[^"]+?)(?:\?[^"]*)?"', b)
        cm = re.search(r'<span class="name">([^<]{2,40}?)</span>', b)
        capa_thumb = _clean_thumb(tms)
        capa = capa_thumb.replace("_t.", ".") if capa_thumb else None
        out.append({
            "slug": slug,
            "titulo": s(tm.group(2)),
            "capa": capa,
            "capa_thumb": capa_thumb,
            "url_pagina": BASE + page_rel,
            "duranca_texto": dm.group(1).strip() if dm else None,
            "qualidade": hd[0].strip() if hd else None,
            "canal": s(cm.group(1)).strip() if cm else None,
        })
        if limit and len(out) >= limit:
            break
    return out


def list_categories():
    html = fetch(BASE + "/")
    seen = set()
    cats = []
    for m in re.finditer(r'href="(/c/[A-Za-z0-9-]+-\d+)"[^>]*>([^<]{2,40})<', html):
        key = m.group(1)
        if key in seen:
            continue
        seen.add(key)
        cats.append({"nome": s(m.group(2)).strip(), "slug": m.group(1).lstrip("/"), "url": BASE + key})
    return cats


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.errorhandler(FetchError)
def on_fetch(e):
    if e.code == 404:
        return jsonify({"erro": "nao encontrado"}), 404
    return jsonify({"erro": "falha ao buscar do xvideos (http %s)" % e.code}), 502


@app.errorhandler(404)
def on_404(e):
    return jsonify({"erro": "rota nao encontrada"}), 404


DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


def serve_doc(name, mimetype):
    """Serve um arquivo estatico da pasta docs/."""
    path = os.path.join(DOCS_DIR, name)
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype=mimetype)


@app.route("/")
def index():
    """Home HTML da API."""
    return serve_doc("index.html", "text/html")


@app.route("/docs")
def docs_page():
    """Documentacao completa (HTML)."""
    return serve_doc("docs.html", "text/html")


@app.route("/style.css")
def style_css():
    return serve_doc("style.css", "text/css")


@app.route("/info")
def info():
    return jsonify({
        "api": "xvideos",
        "versao": "1.0",
        "port": 3778,
        "endpoints": {
            "lista_videos": "/videos?source=home|search|category|tag|user&q=<termo>&page=<n>&count=<n>",
            "detalhes": "/video/<slug>   (aceita slug puro tipo olhipea8ed1 ou url completa da pagina)",
            "categorias": "/categories",
        },
    })


@app.route("/videos")
def videos():
    source = request.args.get("source", "home").lower()
    q = request.args.get("q", "").strip()
    try:
        page = max(int(request.args.get("page", 1) or 1), 1)
    except (TypeError, ValueError):
        return jsonify({"erro": "parametro page invalido"}), 400
    count = request.args.get("count")
    try:
        count = int(count) if count else None
    except (TypeError, ValueError):
        return jsonify({"erro": "parametro count invalido"}), 400

    if source == "home":
        url = BASE + "/"
        paginado = False
    elif source == "search":
        if not q:
            return jsonify({"erro": "parametro q e obrigatorio para source=search"}), 400
        url = "%s/?k=%s&p=%d" % (BASE, quote(q), page)
        paginado = True
    elif source == "category":
        if not q:
            return jsonify({"erro": "parametro q e obrigatorio (ex.: Latina-16) para source=category"}), 400
        slug = q.strip("/").split("?")[0]
        url = "%s/c/%s/%d" % (BASE, slug, page)
        paginado = True
    elif source == "tag":
        if not q:
            return jsonify({"erro": "parametro q e obrigatorio (ex.: pornstar) para source=tag"}), 400
        slug = q.strip("/").split("?")[0]
        url = "%s/tags/%s" % (BASE, slug) if page <= 1 else "%s/tags/%s/%d" % (BASE, slug, page - 1)
        paginado = True
    elif source == "user":
        if not q:
            return jsonify({"erro": "parametro q e obrigatorio (usuario/canal) para source=user"}), 400
        slug = q.strip("/").split("?")[0]
        url = "%s/%s" % (BASE, slug) if page <= 1 else "%s/%s/%d" % (BASE, slug, page - 1)
        paginado = True
    else:
        return jsonify({"erro": "source invalida (use home|search|category|tag|user)"}), 400

    html = fetch(url)
    items = parse_list(html, count)
    if not items:
        # o site as vezes responde uma pagina leve/anti-spam sem blocos; tenta de novo
        time.sleep(3)
        items = parse_list(fetch(url, nocache=True), count)
    return jsonify({
        "fonte": source,
        "query": q or None,
        "pagina": page,
        "total_na_pagina": len(items),
        "tem_mais_paginas": bool(paginado and items),
        "videos": items,
    })


@app.route("/video/<path:ref>")
def video(ref):
    ref = ref.strip()
    if ref.startswith("http"):
        url = ref.rstrip("/")
        m = re.search(r"/video\.([a-z0-9]+)", url)
        # URL curta (sem o trecho do titulo) retorna 404 sem um sufixo
        if m and url.endswith(m.group(1)):
            url += "/x"
    else:
        m = re.search(r"/video\.([a-z0-9]+)", ref)
        if m:
            url = BASE + "/video." + m.group(1) + "/x"
        else:
            url = BASE + "/video." + ref + "/x"
    html = fetch(url)  # levanta FetchError se nao existir
    e = embed_json(html)
    ld = ld_json(html)
    if not ld and not e:
        raise FetchError(404)
    v = build_video(ld, e, html)
    v["fonte"] = url
    return jsonify(v)


@app.route("/categories")
def categories():
    return jsonify({"categorias": list_categories()})


if __name__ == "__main__":
    # em hospedagem (ex.: Render) a porta e informada via variavel PORT;
    # localmente continua na 3778
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3778")), threaded=True)
