"""Organiza galeria/ por categoria e gera as versões repixeladas.

Uso: python galeria.py mover [--dry]   move cada PNG para galeria/<categoria>/... e atualiza
                                        image.location no banco do aig (senão o aig perde o arquivo)
     python galeria.py repixelate       <img>-repixelate.png ao lado de cada imagem
     python galeria.py indice           galeria/indice.csv e indice.json

A categoria sai das tags e do prompt; as imagens importadas sem prompt (bases de img2img,
folhas de entrada do sweep) vão para <categoria>/bases, pela tabela BASES.
"""
import csv
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAL = ROOT / "galeria"
DB = Path.home() / ".local/share/ai-gallery/gallery.db"
SUF = "-repixelate"  # versão reduzida: <nome>-<w>x<h>-repixelate.png


def repix_of(p):
    """Versão repixelada de p, se existir."""
    m = sorted(p.parent.glob(p.stem + "-*x*" + SUF + ".png"))
    return m[0] if m else None

# imagens importadas (sem prompt), classificadas olhando a folha de contato
BASES = {
    "personagens/bases": "00a5b36259df 09b4db2f0d34 1273f108d4bc 178d3bf99dee 20770f166def 21c663d90e12 23ef6c0f6db6 "
                         "2433ab0c7152 291066df4b47 2d76a0c75a04 333e0b452fc6 35616aef7391 4f94234f4d49 51332d5a197a "
                         "533062aa1aad 5364f1fc953d 54069631da08 5512cc5f5f76 5a46ad986c4b 5e0ebecd0afc 5ec7cfc2f82c "
                         "6c5f2f78d992 6d31beb58346 718841481a04 73313d2284fb 79509a6d2b28 7d1fb12488d7 85a4bf093b01 "
                         "875784ded522 8950f616665d 8bff580e758b 8e76201babac 9a0bd21db7b4 a1dc1e3d5bd3 acb5f291b4f2 "
                         "b58ed21b8488 b619bb72944c ca3366c14772 cca5b17ef555 d5d72e22aec8 e08ca4d6e9bc e44ca10c0e9e",
    "arvores/bases": "10f1bd6cc955 15191314ab80 259345fac1f0 287149eb7c9e 5e73b7aaab98 c9609a089238 6a07eb1b81ab "
                     "7b256a3ca740 96160c7eba27 9d15a9181dad a9a9f900c291 bd5fd1c7b5a9 be5237c3f1f7 c0ddd81ecb9a "
                     "c84390cb9b97 e992101bffaf f0a62947e5d4",
    "sombras/bases": "48af019a2505 f838ddc13f18",
    "objetos/bases": "55fb634cab5e 5a34c892eed2 723619d0c32c 8138917d5880 87bd5817672f 90f748bc8f5a 954804eaabb9 "
                     "a1b036643025 c34bc4f061d5 c76b7d60baca d0cbc3fede0f dc7e80a19794 e7b36fc988e0 "
                     "f03c0f818381 f56dc78366bb",
    "terreno/bases": "4f8942dd027a dd41de2d0381 5fdd0c11639b",
    "comparativos/sweep/entradas": "b6edc5fedcda 262c1675bbee 2a17c1b137dd 96cb6a2388e9 9e3fc2264a95 d9c8ca12d867 ddcc60f26ea4",
}
BASE_OF = {i: k for k, v in BASES.items() for i in v.split()}

TREES = ["ipe amarelo", "ipe roxo", "paineira", "jatoba", "pequi", "baru", "cagaita", "buriti"]
OBJS = [("ox cart", "carro-de-boi"), ("two-wheeled cart", "carroca"), ("wooden two-wheeled cart", "carroca"),
        ("fence", "cerca"), ("pilao", "pilao"), ("mortar", "pilao"), ("water wheel", "moinho"),
        ("termite", "cupinzeiro"), ("house", "casa"), ("trailer", "reboque")]
NPCS = [("shopkeeper", "dona-da-venda"), ("cowboy", "vaqueiro"), ("child", "crianca")]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def categoria(r):
    """Pasta relativa a galeria/ para o registro r do índice."""
    p, tags = r["prompt"].lower(), r["tags"].split()
    if "sweep" in tags:
        m = [t[6:] for t in tags if t.startswith("sweep-")]
        return f"comparativos/sweep/{m[0] if m else 'outros'}"
    if not p:
        return BASE_OF.get(r["id"], "outros/importadas")
    if "shadow" in p:
        return "sombras"
    if "chibi" in p or "character" in p:
        return "personagens/" + next((d for k, d in NPCS if k in p), "fazendeiro")
    if "item icon" in p or "inventory" in p:
        return "itens"
    if "growth stages" in p or "plant clump" in p:
        return "colheitas"
    if "tree" in p:
        sp = next((t for t in TREES if t in p), "ipe-seco" if " ipe " in p else "outras")
        return "arvores/" + slug(sp)
    for k, d in OBJS:
        if k in p:
            return "objetos/" + d
    if "tileset" in p or "blocks" in p:
        return "terreno/folhas-isometricas"
    if ("tuft" in p or "pebble" in p) and "sprite sheet" in p:
        return "terreno/decoracao"
    if "texture" in p or "tile" in p or "soil" in p:
        return "terreno/texturas"
    return "outros"


def aig_rows():
    out = subprocess.run(["aig", "img", "ls", "-p", "veredas-assets", "--state", "exported", "--json"],
                         capture_output=True, text=True, check=True, cwd=ROOT).stdout
    rows = []
    for x in json.loads(out):
        p = x["params"]
        rv = x["review"]
        rows.append({"arquivo": str(Path(x["path"]).relative_to(ROOT)), "id": x["id"], "pai": x["parent"] or "",
                     "estilo": p.get("style", ""), "template": p.get("template", ""), "seed": x["seed"],
                     "denoise": p.get("denoise", ""), "review": rv.get("state", "") if isinstance(rv, dict) else "",
                     "tags": " ".join(x["tags"]), "criada": x["created_at"], "prompt": p.get("prompt", "")})
    return sorted(rows, key=lambda r: r["arquivo"])


def mover(dry=False):
    rows = aig_rows()
    con = sqlite3.connect(DB)
    n = 0
    for r in rows:
        src = ROOT / r["arquivo"]
        dst = GAL / categoria(r) / src.name
        if dst == src:
            continue
        print(r["arquivo"], "->", dst.relative_to(ROOT))
        if dry:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        rp = repix_of(src)
        if rp:
            rp.rename(dst.parent / rp.name)
        con.execute("UPDATE image SET location = ? WHERE id = ?", (str(dst), r["id"]))
        con.commit()
        n += 1
    con.close()
    # pastas vazias que sobraram
    for d in sorted(GAL.rglob("*"), key=lambda p: -len(p.parts)):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print(n, "movidas")


def repixelate():
    imgs = [p for p in sorted(GAL.rglob("*.png")) if not p.stem.endswith(SUF)]
    for k, p in enumerate(imgs):
        if repix_of(p):
            continue
        dst = p.with_name(p.stem + SUF + ".png")
        from PIL import Image
        im = Image.open(p).convert("RGBA")
        c = im.getpixel((2, 2))
        white = c[3] == 0 or min(c[:3]) > 235  # fundo branco: o repixelate tira; senão, mantém
        cmd = ["repixelate", str(p), "-o", str(dst)] + ([] if white else ["--no-bg"])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            w, h = Image.open(dst).size
            dst.rename(p.with_name(f"{p.stem}-{w}x{h}{SUF}.png"))
        print(k + 1, len(imgs), p.relative_to(GAL), "ok" if r.returncode == 0 else "ERRO " + r.stderr[-200:],
              flush=True)


def indice():
    rows = aig_rows()
    for r in rows:
        r["categoria"] = str(Path(r["arquivo"]).parent.relative_to("galeria"))
        rp = repix_of(ROOT / r["arquivo"])
        r["repixelate"] = str(rp.relative_to(ROOT)) if rp else ""
    keys = ["categoria", "arquivo", "repixelate"] + [k for k in rows[0] if k not in ("categoria", "arquivo", "repixelate")]
    rows = [{k: r[k] for k in keys} for r in rows]
    (GAL / "indice.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    with open(GAL / "indice.csv", "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "no índice")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "mover":
        mover("--dry" in sys.argv)
    elif cmd == "repixelate":
        repixelate()
    elif cmd == "indice":
        indice()
