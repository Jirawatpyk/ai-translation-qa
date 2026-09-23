#!/usr/bin/env python3
"""v1.10.0: identical-to-source suppression when nothing translatable remains."""
import json, os, subprocess, sys, tempfile
SCRIPTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'ai-translation-qa', 'skills', 'ai-translation-qa', 'scripts')
segs = [
    {'id': 1, 'source': 'Lactobacillus acidophilus DSM 10663 NCIMB 10415', 'target': 'Lactobacillus acidophilus DSM 10663 NCIMB 10415'},  # composite DNT -> clean
    {'id': 2, 'source': '{g5}{x7}{/g5}', 'target': '{g5}{x7}{/g5}'},                     # tag-only field -> clean
    {'id': 3, 'source': 'Page {x7} of 12', 'target': 'Page {x7} of 12'},                 # untranslated -> Major
    {'id': 4, 'source': 'Acme Pet', 'target': 'Acme Pet'},                     # whole-segment DNT -> clean
    {'id': 5, 'source': 'Lactobacillus acidophilus in cats', 'target': 'Lactobacillus acidophilus in cats'},  # residue -> Major
    {'id': 6, 'source': 'https://example.com/x', 'target': 'https://example.com/x'},     # URL only -> clean
    {'id': 7, 'source': 'ADD TO CART', 'target': 'ADD TO CART'},                          # all-caps untranslated -> Major (review #4)
    {'id': 8, 'source': 'Logging in', 'target': 'Logging in'},                            # DNT "Log"/"in" match whole words only: "Logging" stays translatable (review #5)
    {'id': 9, 'source': 'SKU-8842 / DSM10663', 'target': 'SKU-8842 / DSM10663'},          # real codes -> clean
    {'id': 10, 'source': 'STEP 1', 'target': 'STEP 1'},                                    # heading, untranslated -> Major (N2)
    {'id': 11, 'source': 'TABLE 2', 'target': 'TABLE 2'},                                  # heading, untranslated -> Major (N2)
]
d = tempfile.mkdtemp(); p = os.path.join(d, 's.json'); json.dump(segs, open(p, 'w'), ensure_ascii=False)
open(os.path.join(d, 'dnt.txt'), 'w').write('Lactobacillus acidophilus\nAcme Pet\nLog\nin\n')
r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'qa_checks.py'), p, '--dnt', os.path.join(d, 'dnt.txt')], capture_output=True, text=True)
hits = sorted(f['segment_id'] for f in json.loads(r.stdout)['findings'] if 'identical to source' in f['description'])
ok = hits == [3, 5, 7, 8, 10, 11]
print(('PASS' if ok else 'FAIL') + ' identical-to-source fires only on 3,5,7,8,10,11 — got %s' % hits)
sys.exit(0 if ok else 1)
