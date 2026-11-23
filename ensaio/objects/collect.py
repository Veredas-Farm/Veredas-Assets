#!/usr/bin/env python3
"""Recolhe imagens de jobs já enfileirados (quando o gen.py morreu no meio).

Uso: collect.py <exp> <log do gen.py com linhas 'queued <job> <nome>'>
Espera os jobs (aig wait) e copia para ensaio/runs/<exp>/<nome>-<seed>.png.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    exp, log = sys.argv[1], sys.argv[2]
    names = {}
    for line in Path(log).read_text().splitlines():
        p = line.split()
        if len(p) == 3 and p[0] == "queued":
            names[p[1]] = p[2]
    out = ROOT / "runs" / exp
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["aig", "wait", *names, "--json"], capture_output=True, text=True, cwd=ROOT.parent)
    res = json.loads(r.stdout)
    with open(out / "log.jsonl", "a") as f:
        for job in res:
            for img in job.get("images", []):
                dst = out / f"{names[img['job']]}-{img['seed']}.png"
                shutil.copy(img["path"], dst)
                f.write(json.dumps({"file": dst.name, "id": img["id"], "params": img["params"],
                                    "ms": img["duration_ms"]}) + "\n")
                print("got", dst.name, flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
