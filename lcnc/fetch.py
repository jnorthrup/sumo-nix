"""Takes TrikeShed's LCNC vocabulary from a running daemon into lcnc/vocabulary.kif.
   python3 lcnc/fetch.py [http://127.0.0.1:8888] [path/to/TrikeShed]
The daemon's /api/lcnc/facts is its whole shared KIF bank; only the vocabulary relations are kept, at the arity
LcncFacts tells them: what each node type is called, which ports it has, what kind of value each port carries,
whether running it has an effect, and the kinds themselves.  Rows are sorted so a re-fetch diffs by meaning."""
import os, re, subprocess, sys, urllib.request
here = os.path.dirname(os.path.abspath(__file__))
base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8888'
repo = sys.argv[2] if len(sys.argv) > 2 else None
KEEP = {'nodeType': 2, 'label': 3, 'input': 3, 'output': 3, 'inKind': 4, 'outKind': 4,
        'effect': 2, 'source': 2, 'sink': 2, 'kind': 2, 'introduces': 3, 'shape': 3}
TOKEN = re.compile(r'[()]|"(?:[^"\\]|\\.)*"|[^ \t\r\n()";]+')
text = urllib.request.urlopen(base + '/api/lcnc/facts', timeout=120).read().decode('utf-8')
rows = set()
for line in text.splitlines():
    if not line.startswith('('):
        continue
    t = TOKEN.findall(line)
    if len(t) < 3 or t[0] != '(' or t[-1] != ')' or '(' in t[1:-1] or ')' in t[1:-1]:
        continue
    atoms = t[1:-1]
    if KEEP.get(atoms[0]) == len(atoms):
        rows.add('(' + ' '.join(atoms) + ')')
rev = subprocess.run(['git', '-C', repo, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip() if repo else 'unknown'
dirty = repo and subprocess.run(['git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True).stdout.strip()
order = list(KEEP)
with open(os.path.join(here, 'vocabulary.kif'), 'w') as out:
    out.write(f';; TrikeShed LCNC vocabulary, from {base}/api/lcnc/facts at TrikeShed {rev}{" with local edits" if dirty else ""}.\n')
    out.write(';; Relations as LcncFacts tells them; written by lcnc/fetch.py, not by hand.\n')
    for r in sorted(rows, key=lambda r: (order.index(r[1:].split(' ', 1)[0]), r)):
        out.write(r + '\n')
counts = {}
for r in rows:
    k = r[1:].split(' ', 1)[0]; counts[k] = counts.get(k, 0) + 1
print(len(rows), 'rows', {k: counts.get(k, 0) for k in order})
