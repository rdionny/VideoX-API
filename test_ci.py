# -*- coding: utf-8 -*-
"""Testes leves sem rede: validam parsers e rotas da API usando dados de exemplo.
Rode localmente com:  python -m pytest -q test_ci.py
(ou apenas: python test_ci.py)"""
import app as appmod
from app import (
    duration_seconds, parse_views_html, mp4_urls, hls_url, quality_label,
    ld_json, meta, s, embed_json, parse_list, FetchError,
)

LIST_HTML = """
<html><body>
<div class="thumb-block" data-eid="abc123">
  <p class="title"><a href="/video.abc123/x" title="Titulo Um">x</a></p>
  <span class="duration">01:23</span>
  <span class="video-hd-mark">HD</span>
  <img data-src="https://thumb-cdn.xvcdn.com/i/abc_t.jpg?w=250">
  <span class="name">canal_a</span>
</div>
<div class="thumb-block" data-eid="def456">
  <p class="title"><a href="/search-video/tok?x=1" title="Titulo Dois">x</a></p>
  <span class="duration">05:00</span>
  <img data-src="https://thumb-cdn.xvcdn.com/i/def_t.jpg">
  <span class="name">canal_b</span>
</div>
<div class="thumb-block" data-eid="abc123">
  <p class="title"><a href="/video.abc123/y" title="Replicado">x</a></p>
</div>
</body></html>"""

DETAIL_HTML = """
<html><head>
<meta property="og:title" content="Meta &amp; Titulo">
<meta property="og:url" content="https://www.xvideos.com/video.abc123/x">
<script type="application/ld+json">{"name":"LD Titulo","duration":"PT1M2S",
"thumbnailUrl":["https://thumb-cdn.xvcdn.com/i/abc_t.jpg"],
"uploadDate":"2026-10-29T14:25:21+00:00"}</script>
</head><body>
<div id="v-views"><strong class="mobile-hide">280,364</strong></div>
<span class="video-hd-mark">HD</span>
<p>var u = 'https://mp4-cdn.xvcdn.com/v/a/mp4_sd.mp4?secure=111,123', v;</p>
<script>player.setVideoHLS('https://hls-cdn.xvcdn.com/m/abc.m3u8');</script>
<script>{"action":"video","encoded_id_video":"abc123","id_video":999,"uploader":"user_x","uploader_url":"/user_x"}</script>
</body></html>"""


def test_duration_seconds():
    assert duration_seconds("PT10M21S") == 621
    assert duration_seconds("PT1H2M3S") == 3723
    assert duration_seconds(None) is None


def test_parse_views_html():
    assert parse_views_html(DETAIL_HTML) == 280364
    assert parse_views_html('<id="v-views"><strong class="mobile-hide">23,5M</strong>') == 23500000
    assert parse_views_html('<id="v-views"><strong class="mobile-hide">1,2K</strong>') == 1200
    assert parse_views_html("<html></html>") is None


def test_mp4_urls():
    urls = mp4_urls(DETAIL_HTML)
    assert set(urls) == {"sd"}
    assert urls["sd"].endswith("?secure=111,123")
    urls2 = mp4_urls('<p>"url": "https://mp4-cdn.xvcdn.com/v/b.mp4"</p>')
    assert urls2.get("sd") == "https://mp4-cdn.xvcdn.com/v/b.mp4"


def test_hls_url():
    assert hls_url(DETAIL_HTML) == "https://hls-cdn.xvcdn.com/m/abc.m3u8"
    assert hls_url("<p>src=https://hls-cdn.xvcdn.com/z/q.m3u8 fim") == "https://hls-cdn.xvcdn.com/z/q.m3u8"
    assert hls_url("<html></html>") is None


def test_quality_label():
    assert quality_label(DETAIL_HTML) == "HD"
    assert quality_label("<html></html>") is None


def test_ld_and_meta():
    ld = ld_json(DETAIL_HTML)
    assert ld["duration"] == "PT1M2S"
    assert meta(DETAIL_HTML, "og:title") == "Meta & Titulo"
    assert s("&amp;period;fhd") == "&period;fhd"


def test_embed_json():
    e = embed_json(DETAIL_HTML)
    assert e["id_video"] == 999
    assert e["encoded_id_video"] == "abc123"
    assert embed_json("<html></html>") == {}


def test_parse_list():
    items = parse_list(LIST_HTML)
    assert [i["slug"] for i in items] == ["abc123", "def456"]
    i0 = items[0]
    assert i0["titulo"] == "Titulo Um"
    assert i0["duranca_texto"] == "01:23"
    assert i0["qualidade"] == "HD"
    assert i0["capa"] == "https://thumb-cdn.xvcdn.com/i/abc.jpg"
    assert i0["capa_thumb"].endswith("abc_t.jpg")
    assert i0["url_pagina"].startswith("https://www.xvideos.com/video.abc123")
    # limite de count
    assert len(parse_list(LIST_HTML, count=1)) == 1


def _client():
    return appmod.app.test_client()


def test_rotas_basicas():
    c = _client()
    r = c.get("/info")
    assert r.status_code == 200
    body = r.get_json()
    assert body["port"] == 3778
    assert "lista_videos" in body["endpoints"]
    assert r.headers["Access-Control-Allow-Origin"] == "*"

    r = c.get("/")
    assert r.status_code == 200
    assert b"VideoX API" in r.data

    r = c.get("/style.css")
    assert r.status_code == 200

    r = c.get("/rota-que-nao-existe")
    assert r.status_code == 404
    assert r.get_json()["erro"] == "rota nao encontrada"


def test_parametros_invalidos():
    c = _client()
    for qs in ("?source=bogus", "?source=search", "?source=search&q=x&page=abc",
               "?source=search&q=x&count=abc"):
        r = c.get("/videos" + qs)
        assert r.status_code == 400, qs
        assert "erro" in r.get_json()


def test_erro_fetch():
    orig = appmod.fetch
    try:
        def boom(*a, **k):
            raise FetchError(404)
        appmod.fetch = boom
        r = _client().get("/categories")
        assert r.status_code == 404
        assert r.get_json()["erro"] == "nao encontrado"

        def boom503(*a, **k):
            raise FetchError(503)
        appmod.fetch = boom503
        r = _client().get("/categories")
        assert r.status_code == 502
    finally:
        appmod.fetch = orig


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("ok  ", fn.__name__)
        except Exception as ex:
            failed += 1
            print("FAIL", fn.__name__, "->", ex)
    sys.exit(1 if failed else 0)
