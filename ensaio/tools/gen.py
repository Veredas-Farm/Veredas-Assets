"""Enfileira jobs no aig, espera e copia as imagens para ensaio/runs/<exp>/.

Uso: python gen.py <exp> <spec.json>
spec.json: lista de {"name", "template", "set": {...}, "n": 1, "base": id, "mask": png, "feather": px}
Grava runs/<exp>/<name>-<seed>.png e runs/<exp>/log.jsonl.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = {
    "sdxl-pixel-lcm": "pixel-art-xl-lcm",
    "sdxl-pixel": "pixel-art-xl",
    "sdxl-pad": "sdxl-pixel-art-diffusion",
    "moss-pixel": "moss-pixel-lora",
    "sd15-pixel": "sd15-pixel-toolkit",
    "sdxl-pokemon": "sdxl-pokemon-sprite",
    "sd15-survivors": "sd15-pixel-survivors",
    "moss-refiner": "moss-pixel-refiner",
    "flux-pixel": "flux-pixel-lora",
}


def aig(*args):
    r = subprocess.run(["aig", *args, "--json"], capture_output=True, text=True, cwd=ROOT.parent)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-2000:])
    return json.loads(r.stdout)


def main():
    exp, spec_path = sys.argv[1], sys.argv[2]
    spec = json.loads(Path(spec_path).read_text())
    out = ROOT / "runs" / exp
    out.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for s in spec:
        sets = dict(s.get("set", {}))
        if "style" not in sets and s["template"] in STYLE and not s.get("nostyle"):
            sets["style"] = STYLE[s["template"]]
        args = ["job", "add", s["template"], "-n", str(s.get("n", 1)), "--tag", f"ensaio-{exp}"]
        for k, v in sets.items():
            args += ["--set", f"{k}={v}"]
        if s.get("base"):
            args += ["--base", s["base"]]
        if s.get("mask"):  # inpaint: PNG da máscara (relativo a ensaio/), branco = refazer
            args += ["--mask", str((ROOT / s["mask"]).resolve()), "--feather", str(s.get("feather", 24))]
        jid = aig(*args)["jobs"][0]
        jobs[jid] = s
        print("queued", jid, s["name"], flush=True)
    res = aig("wait", *jobs, "--timeout", "7200") if False else None
    r = subprocess.run(["aig", "wait", *jobs, "--json"], capture_output=True, text=True, cwd=ROOT.parent)
    res = json.loads(r.stdout)
    with open(out / "log.jsonl", "a") as log:
        for job in res:
            s = jobs[job["id"]] if "id" in job else None
            for img in job.get("images", []):
                s = jobs[img["job"]]
                dst = out / f"{s['name']}-{img['seed']}.png"
                shutil.copy(img["path"], dst)
                log.write(json.dumps({"file": dst.name, "id": img["id"], "template": s["template"],
                                      "params": img["params"], "ms": img["duration_ms"]}) + "\n")
                print("got", dst.name, img["duration_ms"] // 1000, "s", flush=True)
            if job.get("state") not in (None, "done"):
                print("job", job.get("id"), job.get("state"), job.get("error"), flush=True)


if __name__ == "__main__":
    main()
