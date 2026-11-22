#!/usr/bin/env python3
"""Adds up the per-part reports and checks the totals the span cache publishes.

  aggregate.py README.md manifest.parquet PART_REPORT... > atoms.json

The counts table of justicedao/open-us-law-autoformal-span-cache's README (parent sections read, sections spanned,
spans, each split mode, NFKC changed, jurisdictions) and its manifest.parquet (documents and spans per jurisdiction)
must equal the sums of the parts. Any difference exits 1.
"""
import collections, json, re, sys
import pyarrow.parquet as pq

readme_path, manifest_path, *parts = sys.argv[1:]
reports = [json.load(open(p)) for p in parts]

tot = collections.Counter()
modes, jur = collections.Counter(), collections.defaultdict(collections.Counter)
for r in reports:
    tot["parent sections read"] += r["formalization_prep_rows"]
    tot["formalization-ready sections spanned"] += r["sections_spanned"]
    tot["spans"] += r["spans"]
    tot["NFKC changed"] += r["nfkc_changed"]
    tot["rechunk identical"] += r["rechunk_identical"]
    modes.update(r["split_modes"])
    for code, v in r["jurisdictions"].items():
        jur[code].update(v)
for mode in ("whole", "structure", "sentence", "hard"):
    tot[mode] = modes.get(mode, 0)
tot["jurisdictions"] = len(jur)

claimed = {}
for line in open(readme_path, encoding="utf-8"):
    m = re.match(r"\|\s*([A-Za-z][A-Za-z -]*?)\s*\|\s*(\d+)\s*\|\s*$", line)
    if m:
        claimed[m.group(1)] = int(m.group(2))
diffs = {k: {"published": v, "recomputed": tot[k]} for k, v in claimed.items() if tot[k] != v}

manifest = pq.read_table(manifest_path, columns=["jurisdiction", "documents", "spans"]).to_pylist()
mdiffs = []
for m in manifest:
    got = jur.get(m["jurisdiction"], collections.Counter())
    if got["sections"] != m["documents"] or got["spans"] != m["spans"]:
        mdiffs.append({"jurisdiction": m["jurisdiction"], "published": [m["documents"], m["spans"]],
                       "recomputed": [got["sections"], got["spans"]]})
missing = sorted(set(jur) - {m["jurisdiction"] for m in manifest})

out = {
    "parts": len(reports),
    "published_counts": claimed,
    "recomputed": dict(sorted(tot.items())),
    "counts_differing": diffs,
    "manifest_rows": len(manifest),
    "manifest_differing": mdiffs,
    "jurisdictions_missing_from_manifest": missing,
    "jurisdictions": {k: dict(v) for k, v in sorted(jur.items())},
}
json.dump(out, sys.stdout, indent=1, sort_keys=True)
sys.stdout.write("\n")
if diffs or mdiffs or missing or not claimed:
    sys.stderr.write(f"published totals differ: {diffs} {mdiffs} {missing}\n")
    sys.exit(1)
