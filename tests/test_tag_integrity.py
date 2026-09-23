#!/usr/bin/env python3
"""Synthetic TP/FP tests for tag_integrity.py v1.10.0 (extractor-token notation
+ 3c2 Latin adjacency). Run: python3 test_tag_integrity.py <scripts-dir>"""
import json, os, subprocess, sys, tempfile

SCRIPTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'ai-translation-qa', 'skills', 'ai-translation-qa', 'scripts')
fails = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  <- ' + str(detail)))
    if not cond:
        fails.append(name)


def run(segs):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 's.json')
    json.dump(segs, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'tag_integrity.py'), p],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('tag_integrity crashed: ' + r.stderr)
    return json.loads(r.stdout)['findings']


def sev(fs, sid):
    return sorted(f['severity'] for f in fs if f['segment_id'] == sid)


segs = [
    # ---- extractor-token notation, TP side
    {'id': 1, 'source': '{g9}Technical{/g9} Site Manager', 'target': 'Te{g9}chnical{/g9} Site Manager'},        # 3c Critical: Technical in source
    {'id': 2, 'source': 'ผู้จัดการฝ่ายเทคนิค {g9}คู่มือ{/g9}', 'target': 'Te{g9}chnical{/g9} Site Manager'},  # 3c2 Major: th source, no vocab proof
    {'id': 3, 'source': '{g9}Bold{/g9} {g5}text{/g5}', 'target': '{g9}ตัวหนา {g5}ข้อความ{/g9}{/g5}'},              # nesting: Major order + Critical not well-formed
    {'id': 4, 'source': '{g9}Bold{/g9} text', 'target': 'ตัวหนา text'},                                              # tag set differs: Critical
    {'id': 5, 'source': 'Page {x7} of', 'target': 'หน้า ของ'},                                                       # standalone token missing: Critical
    {'id': 6, 'source': '{g5}Brand{/g5}', 'target': '{g5} แบรนด์{/g5}'},                                              # check 4 Minor: space inside open
    {'id': 7, 'source': 'ก{g5}ำ{/g5}หนด', 'target': 'ก{g5}ำ{/g5}หนด'},                                                 # 3a1 SARA AM Critical (target) — source has it too but 3a1 is a rendering break regardless
    # ---- extractor-token notation, FP side (must be clean)
    {'id': 11, 'source': '{g9}Technical{/g9} Site Manager', 'target': '{g9}เทคนิค{/g9} ผู้จัดการไซต์'},              # faithful Thai
    {'id': 12, 'source': 'Page {x7} of the manual', 'target': 'หน้า {x7} ของคู่มือ'},                                  # standalone preserved
    {'id': 13, 'source': 'Ca{g9}rbon{/g9}', 'target': 'Ca{g9}rbon{/g9}'},                                             # source has same adjacency -> suppressed
    {'id': 14, 'source': '{bpt1}Save{ept1} now', 'target': '{bpt1}บันทึก{ept1} ตอนนี้'},                                # bpt/ept standalone pair
    {'id': 15, 'source': '{g9}Bold{/g9} {g5}nested{/g5}', 'target': '{g9}ตัวหนา{/g9} {g5}ซ้อน{/g5}'},
    {'id': 16, 'source': 'ภาษาไทย {g9}ครับ{/g9}', 'target': 'ภาษาไทย {g9}ครับ{/g9}'},                                   # Thai adjacency: never a finding
    # ---- Phrase notation regression (v1.9.0 behaviour must hold)
    {'id': 21, 'source': '{1>Blonde<1} hair', 'target': 'Blon {1>de<1} ผม'},                                          # 3c Critical
    {'id': 22, 'source': '{1>Brand<1}', 'target': '{1>Brand <1}'},                                                     # check 4 Minor (close side)
    {'id': 23, 'source': '{1>Bold<1} {2>x<2}', 'target': '{2>ตัวหนา<2} {1>x<1}'},                                      # Major order
    {'id': 24, 'source': 'text <3}', 'target': 'ข้อความ <3}'},                                                         # split pair both sides: clean
    {'id': 25, 'source': '{1>Pet Care<1} cats', 'target': '{1>Pet Care<1} แมว'},                                     # clean
    {'id': 26, 'source': 'The {1>Data<1} Manager', 'target': 'Le {1>Da<1}ta Manager'},                                # "Data" is in the source vocabulary -> 3c Critical, not 3c2
    # ---- review round: FP guards for 3c2 / order / literal placeholders
    {'id': 41, 'source': "the {g1}European Union{/g1}", 'target': "l'{g1}Union européenne{/g1}"},          # elision: clean
    {'id': 42, 'source': "{g1}Company{/g1} policy", 'target': "{g1}Company{/g1}'s policy"},                 # possessive: clean
    {'id': 43, 'source': 'Terms{x3}general', 'target': 'Conditions{x3}générales'},                          # standalone-only run: clean
    {'id': 44, 'source': '{x1} items in {x2}', 'target': 'Dans {x2} il y a {x1} articles'},                 # standalone reorder: clean
    {'id': 45, 'source': 'Use {x} as value', 'target': 'ใช้ {x} เป็นค่า'},                                     # UI placeholder, no digit: not a tag
    {'id': 46, 'source': '{g1}Bold{/g1} {x1} then {g2}more{/g2}', 'target': '{g2}mehr{/g2} {x1} dann {g1}fett{/g1}'},  # paired reorder still Major
    {'id': 47, 'source': 'a{bpt1}b{ept1}c', 'target': 'a{ept1}b{bpt1}c'},                                   # reversed pair: Major (N3)
    {'id': 48, 'source': 'Cli{g}quez{/g}', 'target': 'Cli{g}quez{/g}'},                                       # id-less g read; source adjacency -> clean (N4)
    {'id': 49, 'source': '{g}Click{/g} here', 'target': 'Cli{g}quez{/g} ici'},                                # id-less g, 3c2 Major
    # ---- mixed notations in one segment
    {'id': 31, 'source': '{g2}Click {1>Save<1}{/g2}', 'target': '{g2}คลิก {1>บันทึก<1}{/g2}'},                          # clean
]
segs += [
    {'id': 51, 'source': '{g5}Bold{/g5} text', 'target': ''},                                       # empty target: qa_checks' finding, not ours (v1.10.4)
    {'id': 52, 'source': '{g5}Bold{/g5} text', 'target': '{gpm7d570a0a-da72}Fett{/gpm7d570a0a-da72} Text'},  # unmapped Studio pm id: parsed as a tag -> Critical names it
    {'id': 53, 'source': 'Go to {goal1} now', 'target': 'Gehe zu {goal1} jetzt'},                  # UI placeholder that merely starts with g: not a tag
]
fs = run(segs)
by = {}
for f in fs:
    by.setdefault(f['segment_id'], []).append(f)

check('1: 3c Critical Latin split proven by source', sev(fs, 1) == ['Critical'], by.get(1))
check('2: 3c2 Major Latin adjacency without source proof', sev(fs, 2) == ['Major'] and 'no space' in by[2][0]['description'], by.get(2))
check('3: nesting Major + not-well-formed Critical', sev(fs, 3) == ['Critical', 'Major'], by.get(3))
check('4: missing g pair Critical', sev(fs, 4) == ['Critical'] and 'Tag set differs' in by[4][0]['description'], by.get(4))
check('5: missing standalone {x7} Critical', sev(fs, 5) == ['Critical'], by.get(5))
check('6: space inside {g5} Minor', sev(fs, 6) == ['Minor'] and '{g5}' in by[6][0]['description'], by.get(6))
check('7: SARA AM split Critical', 'Critical' in sev(fs, 7), by.get(7))
for i in (11, 12, 13, 14, 15, 16, 24, 25, 31):
    check('%d: clean (FP guard)' % i, i not in by, by.get(i))
for i in (41, 42, 43, 44, 45):
    check('%d: clean (review-round FP guard)' % i, i not in by, by.get(i))
check('46: paired reorder still Major', sev(fs, 46) == ['Major'], by.get(46))
check('47: reversed bpt/ept Major (N3)', sev(fs, 47) == ['Major'] and 'reversed' in by[47][0]['description'], by.get(47))
check('48: id-less g faithful -> clean (N4)', 48 not in by, by.get(48))
check('49: id-less g split -> Major (N4)', sev(fs, 49) == ['Major'], by.get(49))
check('21: Phrase 3c Critical', sev(fs, 21) == ['Critical'], by.get(21))
check('22: Phrase space before close Minor', sev(fs, 22) == ['Minor'] and '<1}' in by[22][0]['description'], by.get(22))
check('23: Phrase order Major', sev(fs, 23) == ['Major'], by.get(23))
check('26: Da|ta with Data in source -> Critical (3c wins over 3c2)', sev(fs, 26) == ['Critical'], by.get(26))

check('51: empty target -> no tag finding (qa_checks owns it)', 51 not in by, by.get(51))
check('52: unmapped pm id parsed as tag -> Critical', sev(fs, 52) == ['Critical'] and 'gpm7d570a0a' in by[52][0]['description'], by.get(52))
check('53: {goal1} is not a tag', 53 not in by, by.get(53))

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
