# Recursive refinement over the SUMO classes: what discriminates, what balances, and a Nix function on each class that has one.
#
#   r = import ./refine.nix { ontology = import ./sumo.nix { inherit forms; }; };
#
#   r.discriminate [ "Human" "Mammal" "Animal" ]        -> [ "Human" ]      the classes no other class of the set refines
#   r.balance [ { class; value; } ... ]                  -> { value; conflicts; }   several parents, one answer, or a named refusal
#   r.refine table thing                                 -> { value; conflicts; applied; }
#
# `table` maps a class name to a function  thing: up: attrs.  `up` is what the nearest classes above it that have a function give, balanced; the
# function returns what it adds or changes.  So a subclass refines its parents' answer, and a thing of several classes is answered by all the
# most specific functions that apply, balanced.  Values are data (equal or not), never functions: a clash has to be decidable.
#
# Nothing here depends on the order of a list: KIF's `subclass` has no order, so there is no linearization to choose (C3 would give an answer
# that depends on how the parents are written down).  Equal bytes, equal answer.
{ ontology }:
let
  inherit (builtins) all any attrNames concatMap elem filter head length listToAttrs map mapAttrs sort;

  unique = xs: attrNames (listToAttrs (map (name: { inherit name; value = null; }) xs));   # sorted, without repeats

  # d is below c, and the two are not the same class named twice round a cycle
  strictly = d: c: d != c && ontology.isSubclass d c && !(ontology.isSubclass c d);

  # The most specific classes of a set: those that no other class of the set refines.  A set of classes is read as "the thing is all of these".
  discriminate = classes:
    let cs = unique classes; in filter (c: !any (d: strictly d c) cs) cs;

  # Several answers, each from a class: a key the answers agree on stays; a key they give different values for is not decided here, and is
  # named with every claim.  Nothing is overridden by the order it came in.
  #   contributions: [ { class; value; conflicts ? [ ]; } ]
  balance = contributions:
    let
      cs = contributions;
      keys = unique (concatMap (c: attrNames c.value) cs);
      claims = k: map (c: { inherit (c) class; value = c.value.${k}; }) (filter (c: c.value ? ${k}) cs);
      agree = k: let vs = claims k; in all (c: c.value == (head vs).value) vs;
      inherited = concatMap (c: c.conflicts or [ ]) cs;
      clash = filter (k: !agree k) keys;
      held = unique (clash ++ map (c: c.key) inherited);
    in {
      value = listToAttrs (map (k: { name = k; value = (head (claims k)).value; }) (filter (k: !(elem k held)) keys));
      conflicts = map (k: { key = k; claims = unique' (concatMap (c: if c.key == k then c.claims else [ ]) inherited ++ (if elem k clash then claims k else [ ])); }) held;
    };

  # claims, without repeats and in an order that does not depend on how they arrived
  unique' = xs: sort (a: b: a.class < b.class || (a.class == b.class && builtins.toJSON a.value < builtins.toJSON b.value)) (builtins.foldl' (acc: x: if elem x acc then acc else acc ++ [ x ]) [ ] xs);

  # The thing's answer.  A class that has a function applies when a class of the thing is it or below it; of those, the most specific apply, each on
  # top of the balanced answer of the nearest classes above it that have a function.  The knot is lazy: a class's answer is computed once, and only
  # when something below it asks.
  refine = table: thing:
    let
      bearing = attrNames table;
      classesOf = ontology.classOf.${thing} or [ ];
      applicable = filter (f: any (c: ontology.isSubclass c f) classesOf) bearing;
      above = c: discriminate (filter (f: strictly c f) bearing);
      answers = mapAttrs
        (c: f:
          let
            up = balance (map (p: answers.${p}) (above c));
            own = f thing up.value;
          in { class = c; value = up.value // own; conflicts = filter (k: !(own ? ${k.key})) up.conflicts; })
        table;
      top = discriminate applicable;
    in
    (balance (map (c: answers.${c}) top)) // { applied = top; };
in
{ inherit discriminate balance refine strictly; }
