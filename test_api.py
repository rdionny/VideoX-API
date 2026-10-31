import requests, json
B = "http://127.0.0.1:3778"

print("== /videos?source=home&count=2 ==")
d = requests.get(B + "/videos", params={"source": "home", "count": 2}, timeout=40).json()
for v in d["videos"]:
    print(" -", v["titulo"][:50], "| capa:", (v["capa"] or "?")[-14:], "| dur:", v["duranca_texto"])

print("\n== /videos?source=search&q=pornstar&page=1&count=2 ==")
d = requests.get(B + "/videos", params={"source": "search", "q": "pornstar", "count": 2}, timeout=40).json()
print("total_na_pagina:", d["total_na_pagina"], "| tem_mais:", d["tem_mais_paginas"])
for v in d["videos"]:
    print(" -", v["titulo"][:50])

print("\n== /videos?source=category&q=Latina-16&count=2 ==")
d = requests.get(B + "/videos", params={"source": "category", "q": "Latina-16", "count": 2}, timeout=40).json()
print("total:", d["total_na_pagina"], "| tem_mais:", d["tem_mais_paginas"])
for v in d["videos"]:
    print(" -", v["titulo"][:50])

print("\n== /videos?source=tag&q=blowjob&count=1 ==")
d = requests.get(B + "/videos", params={"source": "tag", "q": "blowjob", "count": 1}, timeout=40).json()
print("total:", d["total_na_pagina"])

print("\n== /video/olhipea8ed1 (detalhes) ==")
d = requests.get(B + "/video/olhipea8ed1", timeout=40).json()
keep = ["slug", "id", "titulo", "descricao", "url_pagina", "capa", "duranca_seg", "visualizacoes", "data_publicacao", "qualidade", "reproducao", "uploader", "modelos", "tags", "categorias"]
for k in keep:
    print(" ", k, "=>", json.dumps(d.get(k), ensure_ascii=False))
