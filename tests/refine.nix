# mlnix eval tests/refine.nix  ->  "ok" or a failed assertion
#
# refine.nix against what it has to satisfy, not against numbers copied from its own output:
#   discriminate  the laws that fix it: it keeps only classes of the set, no kept class refines another, every class of the set is above a kept
#                 class (so the kept classes are exactly the most specific ones), the order of the set does not matter, and a second pass changes
#                 nothing.  Checked on every thing of the pinned Merge.kif that has a class (565 things, 297 of them with several classes), and again on each of them with the classes above its own.
#   balance       the order of the contributions and a repeated contribution do not change the answer; a key that all agree on stays; a key they
#                 disagree on is named with every claim and is not in the value.
#   refine        a small ontology with a diamond and a thing of two classes: a subclass changes what its parent gives, two siblings that agree
#                 are one answer, two that disagree are refused with both claims, and the order the classes are written in changes nothing.
let
  kif = import ../kif.nix;
  pins = import ../pins.nix;
  forms = kif.parse (builtins.readFile pins.merge);
  onto = import ../sumo.nix { inherit forms; };
  r = import ../refine.nix { ontology = onto; };
  inherit (builtins) all any attrNames elem filter genList length elemAt head;
  check = what: ok: if ok then true else throw "failed: ${what}";
  reverse = xs: let n = length xs; in genList (i: elemAt xs (n - 1 - i)) n;
  sameSet = a: b: all (x: elem x b) a && all (x: elem x a) b && length a == length b;

  # --- discriminate, on the real ontology
  things = attrNames onto.classOf;
  lawsOf = cs:
    let m = r.discriminate cs; in
    all (c: elem c cs) m
    && all (c: all (d: !(r.strictly d c)) m) m
    && all (c: any (d: onto.isSubclass d c) m) cs
    && sameSet m (r.discriminate (reverse cs))
    && sameSet m (r.discriminate m);
  multi = filter (t: length onto.classOf.${t} > 1) things;
  lawsHold = all (t: lawsOf onto.classOf.${t}) things;
  # every class of a thing, and the classes above them: a long set with chains in it
  withAncestors = t: onto.classOf.${t} ++ builtins.concatMap (c: onto.ancestors.${c} or [ ]) onto.classOf.${t};
  lawsHoldLong = all (t: lawsOf (withAncestors t)) things;

  # --- balance
  c = class: value: { inherit class value; };
  one = c "A" { k1 = 1; k2 = 2; };
  two = c "B" { k1 = 1; k3 = 3; };
  three = c "C" { k1 = 9; k2 = 2; };
  perms = [ [ one two three ] [ one three two ] [ two one three ] [ two three one ] [ three one two ] [ three two one ] ];
  b0 = r.balance (head perms);

  # --- refine, on a small ontology: Top > Package, Service; Service > WebService, Daemon
  small = import ../sumo.nix {
    forms = [
      [ "subclass" "Package" "Top" ] [ "subclass" "Service" "Top" ] [ "subclass" "WebService" "Service" ] [ "subclass" "Daemon" "Service" ]
      [ "instance" "nginx" "WebService" ] [ "instance" "nginx" "Package" ]
      [ "instance" "sshd" "Daemon" ]
      [ "instance" "caddy" "Package" ] [ "instance" "caddy" "WebService" ]
      [ "instance" "oddity" "WebService" ] [ "instance" "oddity" "Daemon" ]
      [ "instance" "plain" "Top" ]
    ];
  };
  sr = import ../refine.nix { ontology = small; };
  table = {
    Top = _: _: { lowering = "generic"; };
    Package = _: _: { buildInputs = true; };
    Service = _: _: { lifecycle = "systemd"; };
    WebService = _: up: { lifecycle = "${up.lifecycle}-socket"; port = 80; };
    Daemon = _: _: { lifecycle = "forking"; };
  };
  nginx = sr.refine table "nginx";
  oddity = sr.refine table "oddity";
in
if builtins.all (x: x) [
  # discriminate
  (check "a spot check" (r.discriminate [ "Human" "Mammal" "Animal" "Entity" ] == [ "Human" ]))
  (check "a set with two unrelated classes keeps both" (r.discriminate [ "Human" "Corporation" "Entity" ] == [ "Corporation" "Human" ]))
  (check "the empty set" (r.discriminate [ ] == [ ]))
  (check "a repeated class" (r.discriminate [ "Human" "Human" ] == [ "Human" ]))
  (check "there are things with several classes" (length multi > 100))
  (check "discriminate laws, every thing of Merge.kif" lawsHold)
  (check "discriminate laws, every thing with the classes above its own" lawsHoldLong)

  # balance
  (check "balance: the order of the contributions" (all (p: r.balance p == b0) perms))
  (check "balance: a repeated contribution" (r.balance [ one one two three ] == b0))
  (check "balance: what all agree on stays" (b0.value == { k2 = 2; k3 = 3; }) )
  (check "balance: a clash is named with every claim" (b0.conflicts == [ { key = "k1"; claims = [ { class = "A"; value = 1; } { class = "B"; value = 1; } { class = "C"; value = 9; } ]; } ]))
  (check "balance: nothing" (r.balance [ ] == { value = { }; conflicts = [ ]; }))
  (check "balance: one" (r.balance [ one ] == { value = one.value; conflicts = [ ]; }))

  # refine
  (check "refine: a class with no function above it" ((sr.refine table "plain").value == { lowering = "generic"; }))
  (check "refine: a subclass changes its parent's answer" (nginx.value.lifecycle == "systemd-socket" && nginx.value.port == 80))
  (check "refine: a thing of two classes gets both answers" (nginx.value == { lowering = "generic"; buildInputs = true; lifecycle = "systemd-socket"; port = 80; }))
  (check "refine: the most specific classes apply" (nginx.applied == [ "Package" "WebService" ] && (sr.refine table "sshd").applied == [ "Daemon" ]))
  (check "refine: no conflict when the answers agree" (nginx.conflicts == [ ]))
  (check "refine: the order the classes are written in" ((sr.refine table "caddy") == nginx))
  (check "refine: a clash is refused" (oddity.conflicts == [ { key = "lifecycle"; claims = [ { class = "Daemon"; value = "forking"; } { class = "WebService"; value = "systemd-socket"; } ]; } ]))
  (check "refine: a clashed key is not decided" (!(oddity.value ? lifecycle) && oddity.value.port == 80))
  (check "refine: a function that sets the key settles the clash" ((sr.refine (table // { WebService = _: _: { lifecycle = "forking"; }; }) "oddity").conflicts == [ ]))
]
then "ok" else throw "failed"
