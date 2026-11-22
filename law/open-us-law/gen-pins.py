#!/usr/bin/env python3
"""Writes pins.nix: every input of the format -> atom check, pinned by SHA-256.

  hf buckets list jnorthrup/open-us-law-bucket -R --json > listing.json
  (download every file of the bucket and run sha256sum: path TAB size TAB sha256 per line) > sha256.tsv
  python3 gen-pins.py listing.json sha256.tsv > pins.nix

The Hugging Face datasets are pinned at the revisions below by their LFS SHA-256 (the Hub API's `lfs.oid`).
The chunker is pinned at a commit of endomorphosis/ipfs_datasets_py: the modules state_laws_chunker.py reaches by
module-level imports, plus the two data files its identity code reads. Stdlib only.
"""
import ast, hashlib, json, sys, urllib.error, urllib.request

BUCKET = "jnorthrup/open-us-law-bucket"          # the capture of justicedao/open-us-law-bucket (identical Xet hashes)
GRAPHRAG = ("justicedao/open-us-law-sparse-graphrag", "483790cec429f895798022c2cd97abcc1c4a3b91")
SPANS = ("justicedao/open-us-law-autoformal-span-cache", "70602676f7ebd5db4297c859a0bc740d3afc74fb")
GITHUB = ("endomorphosis/ipfs_datasets_py", "1d2fe946fdb8341c49a38c58ef1d91a334a87085")
CHUNKER = "ipfs_datasets_py/processors/legal_data/state_laws_chunker.py"
DATA_FILES = ["data/legal/state_laws/official_source_catalog.json", "data/legal/open_us_law/release.schema.json"]


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read(), r.headers


def tree(repo, rev, path):
    out, url = [], f"https://huggingface.co/api/datasets/{repo}/tree/{rev}/{path}?recursive=true"
    while url:
        body, headers = get(url)
        out += json.loads(body)
        link = headers.get("Link", "") or ""
        url = link.split(";")[0].strip("<> ") if 'rel="next"' in link else None
    return [f for f in out if f["type"] == "file"]


def lfs_pins(repo, rev, path):
    pins = []
    for f in tree(repo, rev, path):
        if not f["path"].endswith(".parquet"):
            continue
        if "lfs" not in f:
            raise SystemExit(f"{repo}@{rev}:{f['path']} has no LFS SHA-256")
        pins.append({"path": f["path"], "size": f["size"], "sha256": f["lfs"]["oid"]})
    return sorted(pins, key=lambda p: p["path"])


def github_closure(repo, commit):
    base = f"https://raw.githubusercontent.com/{repo}/{commit}/"
    cache = {}

    def fetch(path):
        if path not in cache:
            try:
                cache[path] = get(base + path)[0]
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                cache[path] = None
        return cache[path]

    def resolve(mod):
        p = mod.replace(".", "/")
        for cand in (p + ".py", p + "/__init__.py"):
            if fetch(cand) is not None:
                return cand
        return None

    seen, todo = {}, [CHUNKER]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        src = fetch(path)
        seen[path] = hashlib.sha256(src).hexdigest()
        pkg = path.rsplit("/", 1)[0].replace("/", ".")
        for node in ast.parse(src).body:
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                m = node.module or ""
                if node.level:
                    parts = pkg.split(".")
                    m = ".".join(parts[: len(parts) - node.level + 1] + ([m] if m else []))
                mods = [m] + [m + "." + a.name for a in node.names]
            for m in mods:
                if m.split(".")[0] == "ipfs_datasets_py":
                    r = resolve(m)
                    if r and r not in seen:
                        todo.append(r)
    for path in DATA_FILES:
        seen[path] = hashlib.sha256(fetch(path)).hexdigest()
    return [{"path": p, "sha256": seen[p]} for p in sorted(seen)]


def nix(v, ind=""):
    if isinstance(v, dict):
        inner = ind + "  "
        return "{\n" + "".join(f"{inner}{k} = {nix(x, inner)};\n" for k, x in v.items()) + ind + "}"
    if isinstance(v, list):
        if all(isinstance(x, dict) for x in v):
            inner = ind + "  "
            return "[\n" + "".join(f"{inner}{nix(x, inner)}\n" for x in v) + ind + "]"
        return "[ " + " ".join(nix(x, ind) for x in v) + " ]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return json.dumps(v)


def flat(d):  # one-line attrsets for file entries
    return "{ " + " ".join(f"{k} = {nix(x)};" for k, x in d.items()) + " }"


def main():
    listing, sums = sys.argv[1], sys.argv[2]
    sha = {}
    for line in open(sums):
        path, size, digest = line.rstrip("\n").split("\t")
        sha[path] = (int(size), digest)
    files = []
    for f in sorted(json.load(open(listing)), key=lambda f: f["path"]):
        if f.get("type") != "file":
            continue
        size, digest = sha[f["path"]]
        if size != f["size"]:
            raise SystemExit(f"size differs for {f['path']}: listing {f['size']}, download {size}")
        files.append({"path": f["path"], "size": size, "xet": f["xet_hash"], "sha256": digest})
    readme, _ = get(f"https://huggingface.co/datasets/{SPANS[0]}/resolve/{SPANS[1]}/README.md")
    manifest = [p for p in lfs_pins(*SPANS, "data") if p["path"] == "data/manifest.parquet"]
    pins = {
        "bucket": {"id": BUCKET, "files": files},
        "sparseGraphrag": {"repo": GRAPHRAG[0], "rev": GRAPHRAG[1],
                           "prep": lfs_pins(*GRAPHRAG, "data/formalization_prep"),
                           "corpus": lfs_pins(*GRAPHRAG, "data/corpus")},
        "spanCache": {"repo": SPANS[0], "rev": SPANS[1], "spans": lfs_pins(*SPANS, "data/spans"),
                      "manifest": manifest[0],
                      "readme": {"path": "README.md", "size": len(readme), "sha256": hashlib.sha256(readme).hexdigest()}},
        "github": {"repo": GITHUB[0], "commit": GITHUB[1], "files": github_closure(*GITHUB)},
    }
    out = ["# Generated by gen-pins.py; do not edit. Every input of default.nix, pinned by SHA-256.", "{"]
    for section, body in pins.items():
        out.append(f"  {section} = {{")
        for k, v in body.items():
            if isinstance(v, list):
                out.append(f"    {k} = [")
                out += [f"      {flat(x)}" for x in v]
                out.append("    ];")
            elif isinstance(v, dict):
                out.append(f"    {k} = {flat(v)};")
            else:
                out.append(f"    {k} = {nix(v)};")
        out.append("  };")
    out.append("}")
    print("\n".join(out))


main()
