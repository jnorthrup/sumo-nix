# Open US Law: format -> atom, checked by Nix

`hf://buckets/jnorthrup/open-us-law-bucket` is a capture of `justicedao/open-us-law-bucket` (2026-11-22): 114 files,
1,140,186,125 bytes, every Xet hash equal to the source's. This directory checks, with every input pinned by SHA-256,
how that bucket's statute rows become the span atoms that endomorphosis's projects publish:

| step | where | what |
| --- | --- | --- |
| format | `justicedao/open-us-law-bucket` (HF Bucket) | Vaquill's `v2026.07` snapshot: one parquet of sections per jurisdiction, plus the US Code, constitutions, and the `legal-corpora-reindex/` evidence that ipfs_datasets_py's reindex wrote back |
| section | `justicedao/open-us-law-sparse-graphrag` @ `483790ce` (HF Dataset) | the reindexed corpus (`corpus`) and its normalized sections (`formalization_prep`); the bucket is a seed, most rows were fetched again from official sources |
| atom | `justicedao/open-us-law-autoformal-span-cache` @ `70602676` (HF Dataset) | the span atoms: exclusive slices of each formalization-ready section, at most 512 whitespace tokens |
| cut | `endomorphosis/ipfs_datasets_py` @ `1d2fe946` (GitHub) | `StateLawsChunker`, which cuts the atoms; 11 modules and 2 data files, fetched by SHA-256 |

```
nix-build -I nixpkgs=PATH law/open-us-law -A format    # what the bucket holds; its own SHA256SUMS.json and README against the files
nix-build -I nixpkgs=PATH law/open-us-law -A atoms     # every part: section -> atom, the chunker re-run, the published totals
nix-build -I nixpkgs=PATH law/open-us-law -A parts.part-000000 --check   # rebuild one part and compare the bytes
```

`atoms` fails the build if any part breaks a rule (`check_part.py` lists them):

- each `formalization_prep` row is the corpus row with the same `entry_cid`, with the same text unless `text_changed`, and the corpus `text_hash` is the SHA-256 of its text;
- the spans of a formalization-ready section tile its NFKC text exactly (no gap, no overlap, `chunk_index` 0..n-1), each span's text is its slice and `text_sha256` its hash, the parent and normalized hashes are the section's, and no span is over 512 tokens unless `limit_exempt`;
- the pinned `StateLawsChunker`, run again on every section, cuts the same atoms (`chunk_index`, `char_start`, `char_end`, `split_mode`, `token_count`);
- the sums equal the span cache's README counts and its manifest, jurisdiction by jurisdiction.

`format` reports and does not fail on findings: the bucket's datasets with rows, bytes, SHA-256 and Xet hash; its
`SHA256SUMS.json` against the files; its README's coverage table against the parquet row counts; and, per
jurisdiction, how many corpus texts are byte-identical to a bucket row.

`gen-pins.py` writes `pins.nix` from the bucket listing, the SHA-256 of each downloaded bucket file, the Hub's LFS
hashes at the pinned revisions, and the chunker's import closure at the pinned commit.
