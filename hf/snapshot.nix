# Writes tags.json's content: the small facets of Hugging Face's public tag lists, read from the two API responses below.
# Replaces fetch.py.  Each response is pinned by SHA-256, so a changed list is an error to look at, not a silent change.
# Languages (8,333 tags), per-dataset ids and the 74 fine task ids are left out.
#   mlnix eval --json hf/snapshot.nix > hf/tags.json
# To refresh: fetch both URLs, take their SHA-256 (shasum -a 256), put them below, and set `fetched`.
let
  fetched = "2026-11-03";
  get = kind: sha256: builtins.fromJSON (builtins.readFile (builtins.fetchurl {
    url = "https://huggingface.co/api/${kind}-tags-by-type";
    inherit sha256;
  }));
  ds = get "datasets" "9b764786ab572601c02321e56d3bf433c8563714b238051ef82f882a12d0aa55";
  md = get "models" "8af9378bee6e22394d7706c3c9bfdb115bcd9ed511b553fc3bccb7a3d9752674";
  ids = d: k: map (x: let m = builtins.match "[^:]*:(.*)" x.id; in if m == null then x.id else builtins.head m) d.${k};
  other = ids ds "other";
in
{
  source = [ "https://huggingface.co/api/datasets-tags-by-type" "https://huggingface.co/api/models-tags-by-type" ];
  inherit fetched;
  modality = ids ds "modality";
  # attrNames sorts and drops repeats: the union of the two lists, in order.
  task = builtins.attrNames (builtins.listToAttrs (map (t: { name = t; value = null; }) (ids ds "task_categories" ++ ids md "pipeline_tag")));
  license = ids ds "license";
  domain = builtins.filter (t: t != "synthetic") other;
  origin = builtins.filter (t: t == "synthetic") other;
  size = ids ds "size_categories";
  format = ids ds "format";
  library = ids ds "library";
}
