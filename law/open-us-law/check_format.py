#!/usr/bin/env python3
"""What the Open US Law bucket holds, and how its rows reach the corpus (format checks).

  check_format.py PINS.json BUCKET_DIR CORPUS_DIR > format.json

PINS.json is pins.nix's bucket section; BUCKET_DIR holds the bucket's files under their paths, CORPUS_DIR the corpus
parts of justicedao/open-us-law-sparse-graphrag. Every file was fetched by its pinned SHA-256, so the bytes are known.
The report says:

  inventory   each dataset in the bucket: statutes per jurisdiction, constitutions, the US Code, and the
              legal-corpora-reindex evidence files endomorphosis added, with rows, bytes, SHA-256 and Xet hash
  sums        the bucket's own SHA256SUMS.json against the files: matching, differing, listed but absent, unlisted
  readme      the bucket README's coverage table against the parquet row counts
  seed        per jurisdiction, how many corpus rows have a text byte-identical to a bucket row, and the reverse

It exits 1 only when a parquet file cannot be read; the rest are findings, not failures.
"""
import collections, hashlib, json, os, re, sys
import pyarrow.parquet as pq

pins_path, bucket_dir, corpus_dir = sys.argv[1:4]
pins = json.load(open(pins_path))
files = {f["path"]: f for f in pins["files"]}
NAME = re.compile(r"us_([a-z]+)_(statutes|constitutions)\.parquet$")


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


per_file, groups = [], collections.defaultdict(lambda: {"files": 0, "rows": 0, "bytes": 0, "jurisdictions": []})
rows_of, text_hashes = {}, collections.defaultdict(set)
for path in sorted(files):
    f = files[path]
    entry = {"path": path, "bytes": f["size"], "sha256": f["sha256"], "xet": f["xet"]}
    m = NAME.match(path)
    if path.endswith(".parquet"):
        pf = pq.ParquetFile(os.path.join(bucket_dir, path))
        entry["rows"] = pf.metadata.num_rows
        entry["columns"] = pf.schema_arrow.names
        rows_of[path] = entry["rows"]
        if m and m.group(2) == "statutes":
            code = m.group(1).upper()
            for batch in pf.iter_batches(columns=["text"], batch_size=65536):
                for t in batch.column(0).to_pylist():
                    if t is not None:
                        text_hashes[code].add(sha(t))
    if m:
        kind = m.group(2) if m.group(1) != "federal" else ("us_code" if m.group(2) == "statutes" else "us_constitution")
        g = groups[kind]
        g["files"] += 1; g["bytes"] += f["size"]; g["rows"] += entry.get("rows", 0)
        g["jurisdictions"].append(m.group(1).upper())
    elif path.startswith("legal-corpora-reindex/"):
        doc = json.load(open(os.path.join(bucket_dir, path))) if f["size"] < 1_000_000 else {}
        keys = ("schema", "producer", "program_id", "goal_id", "status", "reasons", "authorizing_for_publication")
        found = {k: doc[k] for k in keys if k in doc}
        for v in doc.values():  # the bundles keep their schema and goal one level down
            if isinstance(v, dict):
                found.update({k: v[k] for k in keys if k in v and k not in found})
        entry["evidence"] = found
        g = groups["legal-corpora-reindex evidence"]
        g["files"] += 1; g["bytes"] += f["size"]
    else:
        g = groups["control and media"]
        g["files"] += 1; g["bytes"] += f["size"]
    per_file.append(entry)

# The bucket's SHA256SUMS.json
sums = json.load(open(os.path.join(bucket_dir, "SHA256SUMS.json")))
listed = {e["file"]: e for e in sums}
check = {"listed": len(listed), "matching": [], "differing": [], "listed_but_absent": [], "unlisted": []}
for name, e in sorted(listed.items()):
    if name not in files:
        check["listed_but_absent"].append(name); continue
    got = {"sha256": files[name]["sha256"], "bytes": files[name]["size"], "rows": rows_of.get(name)}
    diff = {k: {"listed": e.get(k), "file": got[k]} for k in ("sha256", "bytes", "rows") if k in e and e[k] != got[k]}
    (check["differing"].append({"file": name, **diff}) if diff else check["matching"].append(name))
check["unlisted"] = sorted(p for p in files if p.endswith(".parquet") and p not in listed)
check["matching"] = len(check["matching"])

# The README's coverage table
readme = open(os.path.join(bucket_dir, "README.md"), encoding="utf-8").read()
table = {}
for line in readme.splitlines():
    m = re.match(r"\|\s*(\*\*United States Code\*\* \(federal\)|[A-Z]{2})\s*\|\s*([\d,]+)\s*\|", line)
    if m:
        code = "FEDERAL" if m.group(1).startswith("**") else m.group(1)
        table[code] = int(m.group(2).replace(",", ""))
readme_check = {"jurisdictions_in_table": len(table), "matching": 0, "differing": []}
for code, n in sorted(table.items()):
    got = rows_of.get(f"us_{code.lower()}_statutes.parquet")
    if got == n:
        readme_check["matching"] += 1
    else:
        readme_check["differing"].append({"jurisdiction": code, "readme": n, "parquet": got})
total_state = sum(n for c, n in table.items() if c != "FEDERAL")
m = re.search(r"\*\*([\d,]+) state and territorial statute sections\*\*", readme)
readme_check["state_sections_claimed"] = int(m.group(1).replace(",", "")) if m else None
readme_check["state_sections_in_table"] = total_state
readme_check["state_sections_in_parquet"] = sum(n for p, n in rows_of.items()
                                                if p.endswith("_statutes.parquet") and "federal" not in p)

# The seed: corpus rows whose text is byte-identical to a bucket row
corpus_hashes, corpus_rows = collections.defaultdict(set), collections.Counter()
for name in sorted(os.listdir(corpus_dir)):
    t = pq.read_table(os.path.join(corpus_dir, name), columns=["jurisdiction_code", "text_hash"])
    for code, h in zip(t.column(0).to_pylist(), t.column(1).to_pylist()):
        corpus_rows[code] += 1
        corpus_hashes[code].add(h)
seed = {}
for code in sorted(set(corpus_rows) | set(text_hashes)):
    b, c = text_hashes.get(code, set()), corpus_hashes.get(code, set())
    seed[code] = {"bucket_distinct_texts": len(b), "corpus_rows": corpus_rows.get(code, 0),
                  "corpus_distinct_texts": len(c), "shared_distinct_texts": len(b & c)}

expected = sorted(["AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS",
                   "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
                   "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI",
                   "WV", "WY"])
present = sorted(groups["statutes"]["jurisdictions"])
report = {
    "bucket": {"id": pins["id"], "files": len(files), "bytes": sum(f["size"] for f in files.values())},
    "inventory": {k: dict(v, jurisdictions=sorted(v["jurisdictions"])) for k, v in sorted(groups.items())},
    "statute_jurisdictions": {"present": present, "missing_of_50_states_and_dc": sorted(set(expected) - set(present)),
                              "beyond_50_states_and_dc": sorted(set(present) - set(expected))},
    "sha256sums_json": check,
    "readme_coverage_table": readme_check,
    "seed": seed,
    "files": per_file,
}
json.dump(report, sys.stdout, indent=1, sort_keys=True)
sys.stdout.write("\n")
