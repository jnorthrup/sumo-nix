#!/usr/bin/env python3
"""Format -> atom check of one part of Open US Law: sections (formalization_prep) to span atoms.

  check_part.py PREP CORPUS SPANS CHUNKER_DIR PART > report.json

PREP, CORPUS and SPANS are part PART of justicedao/open-us-law-sparse-graphrag's formalization_prep and corpus
configs and of justicedao/open-us-law-autoformal-span-cache's spans: the three hold the same entries. CHUNKER_DIR
holds endomorphosis/ipfs_datasets_py's StateLawsChunker. Three checks; any violation exits 1, so the Nix build fails:

  section  each formalization_prep row is the corpus row with the same entry_cid; its text is the corpus text when
           text_changed is false, and the corpus text_hash is the SHA-256 of the corpus text.
  atoms    the published spans of each formalization-ready section are its exact atoms: chunk_index 0..n-1, exclusive
           char ranges that tile the NFKC text with no gap or overlap, each span's text the slice and text_sha256 its
           SHA-256, parent and normalized hashes those of the section, token_count within model_token_limit unless
           limit_exempt; no spans for any other row.
  rechunk  the pinned StateLawsChunker, run on each formalization-ready section with the published 512-token ceiling,
           cuts the same (chunk_index, char_start, char_end, split_mode, token_count) atoms.

The report has no times or paths, so a rebuild (nix-build --check) gives the same bytes.
"""
import collections, hashlib, json, sys, unicodedata
import pyarrow.parquet as pq

prep_path, corpus_path, spans_path, chunker_dir, part = sys.argv[1:6]
sys.path.insert(0, chunker_dir)
from ipfs_datasets_py.processors.legal_data.state_laws_chunker import StateLawsChunker  # noqa: E402

LIMIT = 512


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


prep = pq.read_table(prep_path, columns=[
    "entry_cid", "legal_id", "jurisdiction_code", "section", "heading", "normalization_status", "text",
    "text_changed", "formalization_ready"]).to_pylist()
corpus = {r["entry_cid"]: r for r in pq.read_table(
    corpus_path, columns=["entry_cid", "legal_id", "jurisdiction_code", "text", "text_hash"]).to_pylist()}
spans = pq.read_table(spans_path, columns=[
    "entry_cid", "legal_id", "jurisdiction_code", "chunk_index", "text", "text_sha256", "char_start", "char_end",
    "token_count", "split_mode", "limit_exempt", "model_token_limit", "parent_text_sha256",
    "normalized_text_sha256", "nfkc_changed"]).to_pylist()

violations = collections.Counter()
examples = collections.defaultdict(list)


def bad(kind, what):
    violations[kind] += 1
    if len(examples[kind]) < 3:
        examples[kind].append(what)


# section: formalization_prep against the corpus
statuses = collections.Counter()
for r in prep:
    statuses[f"{r['normalization_status']} text_changed={r['text_changed']} ready={r['formalization_ready']}"] += 1
    c = corpus.get(r["entry_cid"])
    if c is None:
        bad("section: entry not in the corpus part", r["legal_id"]); continue
    if c["legal_id"] != r["legal_id"] or c["jurisdiction_code"] != r["jurisdiction_code"]:
        bad("section: legal_id or jurisdiction differs from the corpus", r["legal_id"])
    if not r["text_changed"] and r["text"] != c["text"]:
        bad("section: unchanged text differs from the corpus", r["legal_id"])
    if c["text_hash"] != sha(c["text"]):
        bad("section: corpus text_hash is not the SHA-256 of its text", r["legal_id"])
if len(corpus) != len(prep):
    bad("section: corpus part and formalization_prep part differ in size", f"{len(corpus)} != {len(prep)}")

# atoms: the published spans against their sections
by_entry = collections.defaultdict(list)
for s in spans:
    by_entry[s["entry_cid"]].append(s)
rows = {r["entry_cid"]: r for r in prep}
for cid in by_entry:
    if cid not in rows:
        bad("atoms: spans for an entry not in formalization_prep", by_entry[cid][0]["legal_id"])
    elif not rows[cid]["formalization_ready"]:
        bad("atoms: spans for a section that is not formalization-ready", rows[cid]["legal_id"])

split_modes, jurisdictions = collections.Counter(), collections.defaultdict(lambda: [0, 0])
nfkc_changed = spanned = 0
chunker = StateLawsChunker()
rechunk = collections.Counter()
for r in prep:
    if not r["formalization_ready"]:
        continue
    ss = sorted(by_entry.get(r["entry_cid"], []), key=lambda s: s["chunk_index"])
    if not ss:
        bad("atoms: formalization-ready section without spans", r["legal_id"]); continue
    spanned += 1
    jurisdictions[r["jurisdiction_code"]][0] += 1
    jurisdictions[r["jurisdiction_code"]][1] += len(ss)
    text = r["text"]
    nf = unicodedata.normalize("NFKC", text)
    nfkc_changed += nf != text
    if [s["chunk_index"] for s in ss] != list(range(len(ss))):
        bad("atoms: chunk_index is not 0..n-1", r["legal_id"])
    for s in ss:
        split_modes[s["split_mode"]] += 1
        if s["legal_id"] != r["legal_id"] or s["jurisdiction_code"] != r["jurisdiction_code"]:
            bad("atoms: span legal_id or jurisdiction differs from its section", r["legal_id"])
        if s["parent_text_sha256"] != sha(text):
            bad("atoms: parent_text_sha256 is not the section's", r["legal_id"])
        if s["normalized_text_sha256"] != sha(nf):
            bad("atoms: normalized_text_sha256 is not the section's NFKC text", r["legal_id"])
        if bool(s["nfkc_changed"]) != (nf != text):
            bad("atoms: nfkc_changed is wrong", r["legal_id"])
        if sha(s["text"]) != s["text_sha256"]:
            bad("atoms: text_sha256 is not the span text's", r["legal_id"])
        if s["model_token_limit"] != LIMIT:
            bad("atoms: model_token_limit is not 512", r["legal_id"])
        if s["token_count"] > s["model_token_limit"] and not s["limit_exempt"]:
            bad("atoms: span over the token limit", r["legal_id"])
    pos = 0
    for s in ss:
        if s["char_start"] != pos or s["char_end"] < s["char_start"]:
            bad("atoms: spans do not tile the section (gap or overlap)", r["legal_id"]); break
        if nf[s["char_start"]:s["char_end"]] != s["text"]:
            bad("atoms: span text is not its slice of the section", r["legal_id"]); break
        pos = s["char_end"]
    else:
        if pos != len(nf):
            bad("atoms: spans stop before the end of the section", r["legal_id"])
    # rechunk: the pinned chunker on the same section
    try:
        result = chunker.chunk_statute(text, model_token_limit=LIMIT, jurisdiction=r["jurisdiction_code"],
                                       section=r["section"] or r["legal_id"], heading=r["heading"] or "")
    except Exception as e:  # the chunker refusing a section is a finding, not a crash
        bad("rechunk: the chunker refused the section", f"{r['legal_id']}: {type(e).__name__}: {e}"[:300])
        continue
    mine = [(c.chunk_index, c.char_start, c.char_end, c.split_mode, c.token_count) for c in result.chunks]
    theirs = [(s["chunk_index"], s["char_start"], s["char_end"], s["split_mode"], s["token_count"]) for s in ss]
    if mine == theirs:
        rechunk["identical"] += 1
    else:
        bad("rechunk: the chunker cuts different atoms", {"legal_id": r["legal_id"], "pinned": mine[:4],
                                                           "published": theirs[:4]})

report = {
    "part": part,
    "formalization_prep_rows": len(prep),
    "row_status": dict(sorted(statuses.items())),
    "sections_spanned": spanned,
    "spans": sum(len(v) for v in by_entry.values()),
    "split_modes": dict(sorted(split_modes.items())),
    "nfkc_changed": nfkc_changed,
    "jurisdictions": {k: {"sections": v[0], "spans": v[1]} for k, v in sorted(jurisdictions.items())},
    "rechunk_identical": rechunk["identical"],
    "violations": dict(sorted(violations.items())),
    "examples": {k: v for k, v in sorted(examples.items())},
}
json.dump(report, sys.stdout, indent=1, sort_keys=True, default=str)
sys.stdout.write("\n")
if violations:
    sys.stderr.write(f"part {part}: {sum(violations.values())} violations: {dict(violations)}\n")
    sys.exit(1)
