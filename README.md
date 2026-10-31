# API X — dados de vídeo para app Android

API REST em **Flask** que busca dados de vídeos do XVideos em tempo real e devolve **JSON pronto** para consumo no seu app Android. Feita para o caso de uso: grade de vídeos + tela de detalhes + player (HLS adaptativo ou MP4).

**Conteúdo adulto (18+).**

## Recursos

- Sem chave de API, sem login — tudo via GET
- CORS aberto
- Scraping em tempo real com cache de 60 s por página e nova tentativa automática em página leve/anti-bot
- **HLS (M3U8) adaptativo** no campo `hls` — o player escolhe a qualidade sozinho (vimos vídeos com 250p a 1080p); MP4 direto como fallback em `reproducao`
- Home e documentação interativas em HTML servidas pela própria API

## Rodando localmente

Requer Python 3.10+.

```bash
pip install -r requirements.txt
python app.py
# servidor sobe em http://localhost:3778
```

Variáveis de ambiente opcionais:

| Variável | Padrão | Descrição |
|---|---|---|
| `API_X_CACHE_TTL` | `60` | Cache em memória, em segundos |

### Páginas servidas pela API

| URL | O que é |
|---|---|
| `/` | Home da API (HTML) |
| `/docs` | Documentação completa passo a passo (HTML) |
| `/info` | Metadados + health-check (JSON) |
| `/style.css` | Estilo das páginas acima |

## Endpoints

### `GET /videos` — listas

```
GET /videos?source=home|search|category|tag|user&q=<termo>&page=<n>&count=<n>```

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `source` | opcional (padrão `home`) | `home`, `search`, `category` (slug tipo `Latina-16`), `tag` (ex.: `blowjob`), `user` (best-effort) |
| `q` | sim para search/category/tag/user | Termo, slug da categoria, tag ou usuário |
| `page` | opcional (padrão 1) | Página; ignorado em `home` |
| `count` | opcional | Limita itens por resposta |

Resposta (envelope):

```json
{
  "fonte": "search", "query": "maga", "pagina": 1,
  "tem_mais_paginas": true, "total_na_pagina": 2,
  "videos": [
    {
      "slug": "imkbbcm0731",
      "titulo": "...",
      "canal": "...",
      "capa": "https://...jpg",
      "capa_thumb": "https://..._t.jpg",
      "url_pagina": "https://www.xvideos.com/video.imkbbcm0731/x",
      "duranca_texto": "8 min",
      "qualidade": "1080p"
    }
  ]
}```

### `GET /video/<slug>` — detalhes

Aceita slug puro (`/video/olimpkf8bba`) ou a URL da página inteira. Campos principais:

```json
{
  "slug": "olimpkf8bba",
  "id": 92436031,
  "titulo": "...",
  "descricao": "...",
  "url_pagina": "https://www.xvideos.com/video.olimpkf8bba/...",
  "capa": "https://...jpg",
  "capas": ["https://..._t.jpg"],
  "duranca_seg": 1048,
  "visualizacoes": 280364,
  "data_publicacao": "2026-10-29T14:25:21+00:00",
  "qualidade": "1440p",
  "reproducao": { "sd": "https://mp4-cdn77.xvideos-cdn.com/.../mp4_sd.mp4?secure=..." },
  "hls": "https://hls-cdn77.xvideos-cdn.com/.../hls.m3u8",
  "uploader": { "nome": "...", "usuario": "...", "url": "https://..." },
  "modelos": [{ "name": "...", "url": "https://..." }],
  "tags": ["..."],
  "categorias": []
}```

**Dica:** use `hls` no player (Media3/ExoPlayer detecta `.m3u8` sozinho e faz troca automática de qualidade conforme a rede). Se vier `null`, use qualquer URL de `reproducao`. Os links (HLS e MP4) expiram em ~1 dia — busque os detalhes na hora de tocar.

### `GET /categories` — categorias

```json
{ "categorias": [ { "nome": "AI", "slug": "c/AI-239", "url": "https://www.xvideos.com/c/AI-239" } ] }```

O valor após `c/` no `slug` é o `q` para `source=category`.

### `GET /info` — metadados / health-check

```json
{ "api": "xvideos", "versao": "1.0", "port": 3778, "endpoints": { ... } }```

## Erros

| Status | Significado |
|---|---|
| `400` | Parâmetro inválido (`q` faltando, `page`//`count` não numéricos) |
| `404` | `"nao encontrado"` (slug inexistente) ou `"rota nao encontrada"` |
| `502` | Falha ao buscar do site (anti-bot, 429, 5xx) — vale retry com alguns segundos |

Todos os erros são JSON com o campo `erro`.

## Estrutura

```
app.py           # API Flask (scraping, parsers, rotas)
docs/index.html  # home da API
docs/docs.html   # documentação completa
docs/style.css   # tema das páginas HTML
test_api.py      # teste manual rápido (API precisa estar no ar)
test_all.py      # varre todas as sources
requirements.txt
```

## Observações / limitações

- `source=user` é best-effort: a página de usuário usa JS/XHR e às vezes retorna lista vazia
- `categorias` no detalhe é frequentemente vazio; navegue por categoria via `/categories`
- O site faz A/B test de layout; os parsers cobrem as duas variações atuais
- `visualizacoes` usa o número exibido pelo site (já arredondado)
