# Format -> atom validation of Open US Law along the endomorphosis / justicedao circuit (README.md).
#
#   nix-build law/open-us-law -A format             what the bucket holds; its SHA256SUMS.json and README against the files
#   nix-build law/open-us-law -A atoms              sections to span atoms in every part, and the published totals
#   nix-build law/open-us-law -A parts.part-000000  one part
#
# Every input is fetched by the SHA-256 pinned in pins.nix (gen-pins.py writes it), so a file changed upstream stops
# the build instead of changing the answer. nix-build --check rebuilds a result and compares the bytes.
{ pkgs ? import <nixpkgs> { } }:
let
  inherit (pkgs) lib;
  pins = import ./pins.nix;
  py = pkgs.python3.withPackages (ps: [ ps.pyarrow ]);
  hf = "https://huggingface.co";
  fetchFrom = prefix: base: f: pkgs.fetchurl {
    name = "${prefix}-${lib.strings.sanitizeDerivationName (baseNameOf f.path)}";
    url = "${base}/${f.path}";
    inherit (f) sha256;
  };
  bucketFile = fetchFrom "oul-bucket" "${hf}/buckets/${pins.bucket.id}/resolve";
  graphragFile = fetchFrom "oul-graphrag" "${hf}/datasets/${pins.sparseGraphrag.repo}/resolve/${pins.sparseGraphrag.rev}";
  spanFile = fetchFrom "oul-spans" "${hf}/datasets/${pins.spanCache.repo}/resolve/${pins.spanCache.rev}";
  githubFile = fetchFrom "ipfs-datasets-py" "https://raw.githubusercontent.com/${pins.github.repo}/${pins.github.commit}";

  # StateLawsChunker and the modules it imports, at the pinned commit. The parent packages get empty __init__.py
  # files, so importing the chunker runs none of ipfs_datasets_py's own package setup.
  chunker = pkgs.runCommand "ipfs-datasets-py-chunker-${builtins.substring 0 12 pins.github.commit}" { } (''
    mkdir -p $out
  '' + lib.concatMapStrings (f: ''
    install -D -m 0444 ${githubFile f} $out/${f.path}
  '') pins.github.files + ''
    for d in ipfs_datasets_py ipfs_datasets_py/processors ipfs_datasets_py/retrieval ipfs_datasets_py/retrieval/hf_graphrag; do
      [ -e $out/$d/__init__.py ] || install -m 0444 /dev/null $out/$d/__init__.py
    done
  '');

  # The three datasets are sharded alike: part N of formalization_prep, corpus and spans hold the same entries.
  byPart = files: lib.listToAttrs (map (f: { name = lib.removeSuffix ".parquet" (baseNameOf f.path); value = f; }) files);
  prep = byPart pins.sparseGraphrag.prep;
  corpus = byPart pins.sparseGraphrag.corpus;
  spans = byPart pins.spanCache.spans;
  partNames = builtins.attrNames prep;

  parts =
    assert partNames == builtins.attrNames corpus && partNames == builtins.attrNames spans;
    lib.genAttrs partNames (n: pkgs.runCommand "open-us-law-atoms-${n}" { nativeBuildInputs = [ py ]; } ''
      python3 ${./check_part.py} ${graphragFile prep.${n}} ${graphragFile corpus.${n}} ${spanFile spans.${n}} ${chunker} ${n} > $out
    '');

  atoms = pkgs.runCommand "open-us-law-atoms" { nativeBuildInputs = [ py ]; } ''
    python3 ${./aggregate.py} ${spanFile pins.spanCache.readme} ${spanFile pins.spanCache.manifest} \
      ${lib.concatMapStringsSep " " (n: "${parts.${n}}") partNames} > $out
  '';

  bucketDir = pkgs.linkFarm "open-us-law-bucket" (map (f: { name = f.path; path = bucketFile f; }) pins.bucket.files);
  corpusDir = pkgs.linkFarm "open-us-law-corpus" (map (n: { name = "${n}.parquet"; path = graphragFile corpus.${n}; }) partNames);
  format = pkgs.runCommand "open-us-law-format" { nativeBuildInputs = [ py ]; } ''
    python3 ${./check_format.py} ${pkgs.writeText "bucket-pins.json" (builtins.toJSON pins.bucket)} ${bucketDir} ${corpusDir} > $out
  '';
in
{
  inherit format atoms parts chunker;
}
