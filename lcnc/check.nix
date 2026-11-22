# Checks lcnc/anchors.kif against lcnc/vocabulary.kif and the SUMO files, and says what SUMO adds to LCNC's typing.
#   import ./lcnc/check.nix { merge; midLevel; qos; computerInput; }
#     -> { kinds, types, unanchored, new, sides, accepts, carriesCode, violations }
# sides: [TYPE WORK CODE] for each node type anchored on both sides.
# accepts: [SOURCE TARGET] when a wire of kind SOURCE may plug into a port of kind TARGET because SUMO puts SOURCE's
#   class at or below TARGET's, and TARGET is its class (anchored exact or new; a broader anchor is only a bound).
#   LCNC's own typing is exact, so these are the pairs subsumption adds.
# carriesCode: the kinds whose values hold a computer program: code travelling as data.
{ merge, midLevel, qos, computerInput, anchorsText ? builtins.readFile ./anchors.kif, vocabularyText ? builtins.readFile ./vocabulary.kif }:
let
  inherit (builtins) all any attrNames concatMap elem elemAt filter head isList isString length listToAttrs map readFile sort lessThan;
  kif = import ../kif.nix;
  at = elemAt;
  mine = kif.parse anchorsText;
  vocab = kif.parse vocabularyText;
  base = concatMap (f: kif.parse (readFile f)) [ merge midLevel qos computerInput ];
  plain = f: all isString f;
  withHead = h: fs: filter (f: isList f && f != [ ] && head f == h) fs;
  subclassForms = fs: filter (f: isList f && f != [ ] && head f == "subclass" && length f == 3 && plain f) fs;
  onto = import ../sumo.nix { forms = subclassForms (base ++ mine); };
  inSumo = import ../sumo.nix { forms = subclassForms base; };
  known = c: inSumo.parents ? ${c} || any (p: elem c p) (builtins.attrValues inSumo.parents);
  unique = xs: attrNames (listToAttrs (map (name: { inherit name; value = null; }) xs));
  byJson = sort (a: b: lessThan (builtins.toJSON a) (builtins.toJSON b));

  groups = listToAttrs (map (f: { name = at f 1; value = at f 2; }) (withHead "lcncGroup" mine));
  anchor = axis: f: { inherit axis; subject = at f 1; how = at f 2; cls = at f 3; };
  kindAnchors = map (anchor "kind") (withHead "lcncKind" mine);
  workAnchors = map (anchor "work") (withHead "lcncWork" mine);
  codeAnchors = map (anchor "code") (withHead "lcncCode" mine);
  contents = map (f: { axis = "content"; subject = at f 1; how = "content"; cls = at f 2; }) (withHead "lcncContent" mine);
  anchors = kindAnchors ++ workAnchors ++ codeAnchors;
  unanchored = map (f: [ (at f 1) (at f 2) ]) (withHead "lcncUnanchored" mine);
  declared = map (f: at f 1) (subclassForms mine);

  # The vocabulary: every kind told as a kind or carried by a port, every node type.
  kinds = unique (map (f: at f 1) (filter (f: length f == 2) (withHead "kind" vocab))
    ++ map (f: at f 3) (filter (f: length f == 4) (withHead "inKind" vocab ++ withHead "outKind" vocab)));
  types = map (f: at f 1) (filter (f: length f == 2) (withHead "nodeType" vocab));
  subjects = { kind = kinds; work = types; code = types; content = kinds; };

  problems = a:
    (if !(elem a.subject subjects.${a.axis}) then [ [ (if elem a.axis [ "kind" "content" ] then "no such kind" else "no such node type") a.axis a.subject ] ] else [ ])
    ++ (if !(elem a.how [ "exact" "broader" "new" "content" ]) then [ [ "unknown anchor" a.axis a.subject a.how ] ] else [ ])
    ++ (if (a.how == "exact" || a.how == "broader") && !(known a.cls) then [ [ "class not in SUMO" a.axis a.subject a.cls ] ] else [ ])
    ++ (if a.how == "content" && !(known a.cls) && !(elem a.cls declared) then [ [ "class not in SUMO" a.axis a.subject a.cls ] ] else [ ])
    ++ (if a.how == "new" && (!(elem a.cls declared) || known a.cls) then [ [ "new class missing or already in SUMO" a.axis a.subject a.cls ] ] else [ ])
    ++ (if !(onto.isSubclass a.cls groups.${a.axis}) then [ [ "outside its group" a.axis a.subject a.cls groups.${a.axis} ] ] else [ ]);
  parentProblems = map (f: [ "parent not in SUMO" (at f 1) (at f 2) ])
    (filter (f: !(known (at f 2)) && !(elem (at f 2) declared)) (subclassForms mine));
  covered = map (a: a.subject) kindAnchors ++ map (u: at u 1) (filter (u: head u == "kind") unanchored);
  missing = map (k: [ "kind has no anchor" k ]) (filter (k: !(elem k covered)) kinds);
  workTypes = map (a: a.subject) workAnchors;
  codeTypes = map (a: a.subject) codeAnchors;
  oneSided = map (t: [ "work without code" t ]) (filter (t: !(elem t codeTypes)) workTypes)
    ++ map (t: [ "code without work" t ]) (filter (t: !(elem t workTypes)) codeTypes);
  both = c: all (s: onto.isSubclass c s);
  duality = (if both "LcncProgram" [ "Plan" "ComputerProgram" ] then [ ] else [ [ "a program is not both work and code" "LcncProgram" ] ])
    ++ (if both "LcncStep" [ "IntentionalProcess" "ComputerProcess" ] then [ ] else [ [ "a step is not both work and code" "LcncStep" ] ]);

  count = axis: how: length (filter (a: a.axis == axis && a.how == how) anchors);
  kindAnchor = listToAttrs (map (a: { name = a.subject; value = a; }) kindAnchors);
  workOf = listToAttrs (map (a: { name = a.subject; value = a.cls; }) workAnchors);
  codeOf = listToAttrs (map (a: { name = a.subject; value = a.cls; }) codeAnchors);
  anchored = attrNames kindAnchor;
in
{
  kinds = listToAttrs (map (how: { name = how; value = count "kind" how; }) (filter (h: count "kind" h > 0) [ "broader" "exact" "new" ]));
  types = { anchored = length (filter (t: codeOf ? ${t}) workTypes); of = length types; };
  unanchored = byJson unanchored;
  new = sort lessThan declared;
  sides = byJson (map (t: [ t workOf.${t} codeOf.${t} ]) (filter (t: codeOf ? ${t}) workTypes));
  accepts = byJson (concatMap (s: concatMap (t:
      if s != t && kindAnchor.${t}.how != "broader" && onto.isSubclass kindAnchor.${s}.cls kindAnchor.${t}.cls then [ [ s t ] ] else [ ])
    anchored) anchored);
  carriesCode = sort lessThan (map (c: c.subject) (filter (c: onto.isSubclass c.cls "ComputerProgram") contents));
  violations = concatMap problems (anchors ++ contents) ++ parentProblems ++ missing ++ oneSided ++ duality;
}
