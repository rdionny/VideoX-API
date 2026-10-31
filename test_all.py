import requests, json
B = "http://127.0.0.1:3778"

def run(src, **p):
    params = dict(p); params["source"] = src; params.setdefault("count", 2)
    d = requests.get(B + "/videos", params=params, timeout=45).json()
    print("== source=%s params=%s ==" % (src, {k:v for k,v in params.items() if k!='count'}))
    if "erro" in d:
        print("   ERRO:", d["erro"]); return
    print("   total=%s tem_mais=%s" % (d["total_na_pagina"], d["tem_mais_paginas"]))
    for v in d["videos"]:
        capa = (v["capa"] or "-")[-18:]
        print("   - %-46s dur=%-7s q=%-6s capa=...%s" % (v["titulo"][:46], v["duranca_texto"], v["qualidade"], capa))

run("home")
run("search", q="maga")
run("search", q="pornstar", page=2)
run("category", q="Latina-16")
run("category", q="Latina-16", page=3)
run("tag", q="blowjob")
