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

## Results (mlnixos, Nix 2.28.4, nixpkgs 3ff0e34, 2026-11-22, a02214a)

`atoms` passes in all 132 parts. The pinned `StateLawsChunker` cut identical atoms for all 526,818 formalization-ready
sections. Every published count is recomputed exactly; the manifest's 48 jurisdictions agree row by row:

| | published | recomputed |
| --- | --- | --- |
| parent sections read | 537,665 | 537,665 |
| formalization-ready sections spanned | 526,818 | 526,818 |
| spans | 685,213 | 685,213 |
| whole / structure / sentence / hard | 448,330 / 197,725 / 36,617 / 2,541 | the same |
| NFKC changed | 0 | 0 |
| jurisdictions | 48 | 48 |

`nix-build --check` rebuilt `format` and `parts.part-000000` with the same bytes.

What the bucket holds (`format`):

| dataset | files | rows | bytes |
| --- | --- | --- | --- |
| state and territorial statutes (`us_XX_statutes.parquet`) | 50 | 1,928,555 | 1,041,749,328 |
| United States Code (`us_federal_statutes.parquet`) | 1 | 54,853 | 88,711,846 |
| state and territorial constitutions (`us_XX_constitutions.parquet`) | 51 | 7,688 | 3,447,303 |
| US Constitution (`us_federal_constitutions.parquet`) | 1 | 74 | 31,003 |
| `legal-corpora-reindex/` evidence from ipfs_datasets_py (LCR-G130, G141, G145, G146) | 7 | | 5,916,927 |
| README, SHA256SUMS.json, .gitattributes, thumbnail | 4 | | 329,718 |

- The statutes cover 48 states, DC and PR. GA and NC are absent (withdrawn 2026-08-12 for navigation and footer text).
- The README's coverage table equals the parquet row counts for all 51 rows; its 1,928,555 state sections equal the files.
- The bucket's own `SHA256SUMS.json` is stale. 102 of its 105 entries match, the two withdrawn files are still listed, and `us_federal_constitutions.parquet` is listed at 25,208 bytes while the file is 31,003 bytes.
- The bucket is only a seed of the corpus: 94,901 of the corpus's 399,531 distinct texts are byte-identical to a bucket row. They are mostly IL, NH, MS and WI, with a little of KS and TN. In 43 jurisdictions the corpus shares no text with the bucket.
