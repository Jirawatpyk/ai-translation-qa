#!/usr/bin/env python3
"""Deterministic integrity checks for CAT-tool inline tags — the checks
qa_checks.py cannot do, because these are HALF-tokens with content between
them. qa_checks.py masks and count-compares them; this script checks STRUCTURE
and PLACEMENT. Two notations are recognised, auto-detected per segment (both
may occur in one file):

  * Memsource/Phrase textual notation: `{1>` opens, `<1}` closes.
  * The token notation sdlxliff_io.py / mxliff_io.py emit on extract:
    `{g5}` opens, `{/g5}` closes; `{x7}` `{ph3}` `{bpt1}` `{ept1}` `{it2}` are
    standalone (they take part in the set check and the placement checks;
    they are NOT order-checked, because a translation legitimately moves a
    standalone placeholder with the word it belongs to — except that an
    `{eptN}` placed before its `{bptN}` is reported as a reversed pair, Major).
  So a Trados SDLXLIFF job gets the same placement checks as a Phrase one —
  run this script on every CAT bilingual, whichever tool produced it.

  1. tag set equality      — same tags, same counts, source vs target (Critical)
  2. nesting order          — {1>{2>..<2}<1} must not become {2>{1>..<1}<2} (Major;
                              Critical if the target tags are not well-formed AND
                              the source's are — a tag pair that spans segments
                              leaves an unpaired half in BOTH source and target,
                              which is faithful, not a target defect)
  3. word-boundary placement — a tag must never land INSIDE a word:
       a1. grapheme-cluster split (no dependency, script-general, ZERO false
           positives): tag before a combining mark, before a Thai/Lao SARA AM
           sign (U+0E33/U+0EB3 — category Lo, but never stands alone), after a
           Thai/Lao leading vowel, or after a Khmer COENG — always a rendering
           break.
       a2. Thai word boundary, TOKENIZER-GATED (needs pythainlp): flags only
           when the tag offset is not a token boundary. Bare adjacency is never
           a signal — it yields Critical false positives on correct files in
           no-space scripts; do not use it.
       b. Thai lexical-unit split, TOKENIZER-GATED (needs pythainlp): a token
          spans the junction, so the two sides are one unit — "ความร่วม <3} มือ"
          → ความร่วมมือ. Always MAJOR: the tokenizer cannot tell a broken word
          from a legitimate compound boundary (ทรัพย์สิน|ทางปัญญา), so
          arbitration re-grades to Critical once a linguist confirms.
       c. Latin join: "Blon <2} de" where "Blonde" exists in the source (Critical;
          suppressed when the source itself carries the same word-tag-word
          adjacency — faithful placement is not a defect)
       c2. Latin adjacency without source proof: letters directly on BOTH sides
          of a run that contains a PAIRED tag, with no space anywhere in the run
          ("Ma{g9}nual", "Cu{1>stomer") — in a space-delimited script that is a
          word split unless partial-word formatting is intended, which is rare.
          MAJOR, not Critical: no dictionary confirms the word (the source may
          be in another script entirely), so arbitration decides. Letters only
          — an apostrophe ends the run, so "l'{g1}Union" and "{g1}Company{/g1}'s"
          do not fire; runs made only of standalone tokens ({x3} as a line
          break: "Conditions{x3}générales") do not fire either. Same
          source-adjacency suppression as 3c.
  4. spaces just inside a tag boundary — `{1> Brand <1}` when the source has
     `{1>Brand<1}` (Minor; renders as stray spaces around a link/em span)

Why this exists: on raw-MT bilinguals these defects are common and completely
invisible to placeholder-count checks — the tag set can be perfectly intact while
every tag has landed in the wrong place inside the sentence.

Usage:
  python tag_integrity.py segments.json [-o findings.json]

Input:  [{"id": 1, "source": "...", "target": "..."}, ...]
Output: same findings shape as qa_checks.py.

pythainlp is OPTIONAL. Without it, BOTH tokenizer-gated checks (3a2 and 3b) are
skipped and the output notes the degradation — install it for any THAI target.
Coverage honesty: the dictionary join (3b) and the tokenizer gate (3a2) are
Thai-only; the grapheme-cluster check (3a1) needs no dependency and covers
Thai, Lao, Khmer and any script using combining marks. Lao/Khmer WORD splits (as opposed to cluster splits) are
NOT detected — no tokenizer is wired for them; route those to the human editor
pass rather than trusting a silent pass. Severities are defaults; arbitration
may re-grade.

SEVERITY POLICY: Critical is reserved for PROOF — an orthographically impossible
cluster split (3a1), or a Latin word the SOURCE itself contains (3c). Everything
resting on a tokenizer guess is Major, because newmm lexicalises compounds and
will call a legitimate boundary a split. Arbitration re-grades upward; the script
never claims certainty it does not have.

What this script canNOT judge: whether the tag wraps the RIGHT SPAN (the Thai
equivalent of exactly the words it wraps in the source — e.g. a tag swallowing
a neighbouring verb, or wrapping the whole sentence). That is a meaning-level
judgement; the editor prompt must carry it. This script only proves structure.
"""
import argparse, json, re, sys, unicodedata
from collections import Counter

# One regex, two notations. Groups: 1-2 = Phrase {n> / <n}; 3-5 = extractor
# tokens {[/]name[N]}. Keep TAGRUN's alternation identical to TAG's.
# Extractor tokens REQUIRE a digit here: "{x}" / "{g}" without one is far more
# likely a UI placeholder in the copy itself than an id-less inline element.
# ({g}/{/g} without an id is the extractor's rendering of an id-less <g>, which
# UI copy never contains, so it is accepted; "{x}" is a placeholder, not a tag.)
# An id is digits, or a Studio Perfect Match / TM tag id ("pm" + GUID) that
# sdlxliff_io could not map to a source twin — parsed as a tag so the tag-set
# check names it, instead of it passing silently as text.
_ID = r"(?:\d+|pm[0-9a-f][0-9a-f-]{7,})"
_XT = r"\{(/?)(g" + _ID + r"?|(?:x|ph|bpt|ept|it)" + _ID + r")\}"
TAG = re.compile(r"\{(\d+)>|<(\d+)\}|" + _XT)
TAGRUN = re.compile(r"(?:\s*(?:\{\d+>|<\d+\}|\{/?(?:g" + _ID + r"?|(?:x|ph|bpt|ept|it)" + _ID + r")\})\s*)+")   # run of tags + surrounding spaces
_TOKNAME = re.compile(r"bpt|ept|ph|it|g|x")
LETTERS_BEFORE = re.compile(r"[A-Za-zÀ-ÿ]+$")     # 3c2: letters only, no apostrophe
LETTERS_AFTER = re.compile(r"^[A-Za-zÀ-ÿ]+")
# Thai/Lao leading vowels — written BEFORE their consonant, so a tag between
# them and the consonant breaks the cluster.
LEADING_VOWEL = re.compile(r"[\u0E40-\u0E44\u0EC0-\u0EC4]")
THAI = re.compile(r"[\u0E00-\u0E7F]")                    # Thai only (3b dictionary join)
THAI_SEQ_BEFORE = re.compile(r"[\u0E00-\u0E7F]+$")
THAI_SEQ_AFTER = re.compile(r"^[\u0E00-\u0E7F]+")
LATIN_SEQ_BEFORE = re.compile(r"[A-Za-zÀ-ÿ']+$")
LATIN_SEQ_AFTER = re.compile(r"^[A-Za-zÀ-ÿ']+")

try:
    from pythainlp import word_tokenize as TOKENIZE
except Exception:
    TOKENIZE = None


def junction_token(left, right):
    """If a single token spans the left|right junction, the two sides are one
    word and the tag between them splits it. Returns (leftpart, rightpart, word).
    This is what makes the check sound: the tokenizer, not a dictionary guess,
    decides whether a boundary is real. Without it, any suffix+prefix pair that
    happens to form a word fires (และ|ครอบคลุม -> "ละ"+"คร" = ละคร)."""
    if TOKENIZE is None:
        return None
    joined, pos = left + right, 0
    try:
        toks = TOKENIZE(joined, engine="newmm")
    except Exception:
        return None
    for t in toks:
        if pos < len(left) < pos + len(t):
            k = len(left) - pos
            return (t[:k], t[k:], t)
        pos += len(t)
    return None


def classify(m):
    """(kind, key) for a TAG match: kind is open/close/empty; key identifies
    the pair ('3' for Phrase {3>/<3}, 'g5' for {g5}/{/g5}, 'x7' for a
    standalone token)."""
    if m.group(1):
        return ("open", m.group(1))
    if m.group(2):
        return ("close", m.group(2))
    closing, body = m.group(3), m.group(4)
    name = _TOKNAME.match(body).group(0)
    if name == "g":
        return ("close" if closing else "open", body)
    return ("empty", body)


def tags(text):
    return [classify(m) for m in TAG.finditer(text)]


def pair_literals(text):
    """{open literal: close literal} for every paired tag in `text`, so check 4
    can look for a space just inside either half whichever notation it is."""
    out = {}
    for m in TAG.finditer(text):
        kind, key = classify(m)
        if kind == "empty":
            continue
        phrase = bool(m.group(1) or m.group(2))
        op = ("{%s>" % key) if phrase else ("{%s}" % key)
        cl = ("<%s}" % key) if phrase else ("{/%s}" % key)
        out[op] = cl          # a lone close half (pair split across segments) still maps
    return out


def well_formed(seq):
    stack = []
    for kind, n in seq:
        if kind == "open":
            stack.append(n)
        elif kind == "close":
            if not stack or stack[-1] != n:
                return False
            stack.pop()
    return not stack


def check_segment(seg):
    fs = []
    sid = seg["id"]
    src = str(seg.get("source") or "")
    tgt = str(seg.get("target") or "")
    add = lambda sev, desc, fix="": fs.append(dict(
        segment_id=sid, category="Markup", severity=sev, description=desc,
        suggested_fix=fix, found_by="Script(tag_integrity)"))

    # An empty target is qa_checks' finding (Critical "Empty target segment");
    # reporting its missing tags again would charge the same defect twice.
    if not tgt.strip():
        return fs
    ts, tt = tags(src), tags(tgt)
    if not ts and not tt:
        return fs

    # 1–2: set, order, well-formedness. Order is judged on PAIRED tags only:
    # a standalone placeholder ({x1} a line break, {ph2} a variable) moves with
    # the word it belongs to, and target word order is the translator's call.
    ts_p = [t for t in ts if t[0] != "empty"]
    tt_p = [t for t in tt if t[0] != "empty"]
    if sorted(ts) != sorted(tt):
        add("Critical", f"Tag set differs from source. source={ts} target={tt}",
            "Restore the exact source tag set")
    elif ts_p != tt_p:
        add("Major", f"Tag order/nesting differs from source. source={ts_p} target={tt_p}",
            "Match the source nesting order")
    # paired placeholders ({bptN} … {eptN}) are standalone tokens, so the order
    # check above ignores them — but an end before its start is a broken span
    # in the CAT tool even though the file parses.
    for kind, key in tt:
        if kind == "empty" and key.startswith("ept"):
            n = key[3:]
            first_bpt = next((i for i, t in enumerate(tt) if t == ("empty", "bpt" + n)), None)
            first_ept = next(i for i, t in enumerate(tt) if t == ("empty", key))
            if first_bpt is not None and first_ept < first_bpt:
                add("Major", f"Paired placeholder reversed: {{ept{n}}} precedes {{bpt{n}}}",
                    "Put {bpt%s} before {ept%s}" % (n, n))
    # Only a target that breaks pairing the SOURCE kept is a defect. CAT files
    # routinely split a tag pair across segments, leaving an unpaired half on
    # both sides; flagging that is a Critical false positive on a correct file.
    if tt and not well_formed(tt) and well_formed(ts):
        add("Critical", f"Target tags are not well-formed (bad nesting): {tt}",
            "Re-pair the tags")

    # ---- 3: cluster / word-boundary placement -------------------------------
    # One plain-text coordinate system for all three checks, so the same physical
    # split cannot be reported three times (evidence order: 3a1 > 3b > 3a2).
    def plain_off(raw_idx):
        consumed = 0
        for mm in TAG.finditer(tgt):
            if mm.end() <= raw_idx:
                consumed += mm.end() - mm.start()
            else:
                break
        return raw_idx - consumed
    reported = set()

    # 3a-1: grapheme-cluster split — a tag between a base character and a mark
    # that cannot stand alone. Zero false positives by construction: this is a
    # rendering break, not a guess about where words end. CRITICAL = proof.
    for m in TAG.finditer(tgt):
        b, a = tgt[:m.start()], tgt[m.end():]
        if not b:
            continue                      # tag at string start splits nothing
        why = None
        if a and unicodedata.category(a[0]) in ("Mn", "Mc"):
            why = (f"the character after it ({a[0]!r}) is a combining mark that must "
                   "stay attached to the base character before the tag")
        elif a and a[0] in "ำຳ":
            # Thai/Lao SARA AM: Unicode category Lo (not Mn/Mc), but it never
            # stands alone — it binds to the preceding consonant, so a tag
            # between them is a guaranteed rendering break.
            why = (f"the character after it ({a[0]!r}) is a SARA AM sign that must "
                   "stay attached to the consonant before the tag")
        elif LEADING_VOWEL.match(b[-1]):
            why = (f"the character before it ({b[-1]!r}) is a leading vowel that must "
                   "stay attached to the consonant after the tag")
        elif b[-1] == "\u17d2":          # Khmer COENG binds to the next consonant
            why = ("it follows a Khmer COENG, which must stay attached to the "
                   "consonant after it")
        if why:
            reported.add(plain_off(m.start()))
            add("Critical",
                f"Tag {m.group(0)!r} splits a grapheme cluster "
                f"(…{b[-6:]}|{a[:6]}…) — {why}",
                "Move the tag outside the cluster")

    # 3b/3c: a tag run (with or without spaces around it) that lands inside one
    # word. TOKENIZER-GATED: the two sides are only "one word" if a token spans
    # the junction. Bare adjacency proves nothing — Thai/Lao/Khmer do not space
    # between words, so script characters on both sides of a tag are NORMAL.
    src_vocab = set(re.findall(r"[A-Za-zÀ-ÿ']{2,}", src))
    src_adjacent = set()                  # Latin adjacencies the SOURCE itself has
    for sm in TAGRUN.finditer(src):
        sb = LATIN_SEQ_BEFORE.search(src[:sm.start()])
        sa = LATIN_SEQ_AFTER.search(src[sm.end():])
        if sb and sa:
            src_adjacent.add((sb.group(0), sa.group(0)))
    seen = set()
    for m in TAGRUN.finditer(tgt):
        before, after = tgt[:m.start()], tgt[m.end():]
        run = m.group(0).strip()
        first_tag = TAG.search(m.group(0))
        off = plain_off(m.start() + (first_tag.start() if first_tag else 0))
        if TOKENIZE is not None and off not in reported:
            b, a = THAI_SEQ_BEFORE.search(before), THAI_SEQ_AFTER.search(after)
            if b and a:
                hit = junction_token(b.group(0), a.group(0))
                if hit and hit[2] not in seen:
                    seen.add(hit[2]); reported.add(off)
                    # MAJOR, never Critical: a token spanning the junction proves
                    # the two sides form one lexical unit, but NOT whether that
                    # unit is a broken word (ความร่วม|มือ) or a legitimate compound
                    # boundary (ทรัพย์สิน|ทางปัญญา). Only a linguist can tell those
                    # apart — arbitration re-grades to Critical when it is a real
                    # broken word, which for a heading usually it is.
                    add("Major",
                        f"Tag run {run!r} sits inside the Thai lexical unit "
                        f"“{hit[2]}” (splits it into “{hit[0]}” + “{hit[1]}”). "
                        "Decide which it is: a BROKEN WORD (re-grade Critical — it "
                        "renders as two fragments) or a compound boundary the tag "
                        "may legitimately fall on.",
                        f"If broken, rejoin as “{hit[2]}” and move the tag to a word boundary")
        b, a = LATIN_SEQ_BEFORE.search(before), LATIN_SEQ_AFTER.search(after)
        if b and a:
            bg, ag = b.group(0), a.group(0)
            j = bg + ag
            if (j in src_vocab and j not in seen and len(bg) >= 2 and len(ag) >= 2
                    and (bg, ag) not in src_adjacent):
                seen.add(j); reported.add(off)
                add("Critical",
                    f"Latin word split by tag run {run!r}: “{bg}” + “{ag}” = “{j}”",
                    f"Rejoin as “{j}”; move the tag outside the word")
            elif (j not in seen and not re.search(r"\s", m.group(0))
                    and any(k != "empty" for k, _ in tags(m.group(0)))
                    and (bg, ag) not in src_adjacent
                    and LETTERS_BEFORE.search(before) and LETTERS_AFTER.search(after)
                    and len(LETTERS_BEFORE.search(before).group(0)) >= 2
                    and len(LETTERS_AFTER.search(after).group(0)) >= 2):
                # 3c2: no source word proves the join, but letters hug the tag
                # on both sides with no space in the run. In a space-delimited
                # script that is a split unless partial-word formatting was
                # intended — MAJOR, arbitration decides (the source may be in
                # another script, so the dictionary test cannot apply).
                seen.add(j); reported.add(off)
                add("Major",
                    f"Tag run {run!r} sits between two Latin letter sequences with no "
                    f"space: “{bg}” + “{ag}” — a word split unless partial-word "
                    "formatting is intended (rare). Confirm against the layout.",
                    f"If it is one word, rejoin as “{j}” and move the tag to the word boundary")

    # 3a-2: tokenizer boundary disagreement only — the tag offset is not a token
    # boundary, but no dictionary word confirms a split. That is a tokenizer
    # GUESS (newmm lexicalises compounds like ทรัพย์สินทางปัญญา as one token), so
    # it is MAJOR, never Critical. Critical is reserved for proof.
    if TOKENIZE is not None and THAI.search(tgt):
        plain, offsets, i = [], [], 0
        for m in TAG.finditer(tgt):
            plain.append(tgt[i:m.start()])
            offsets.append((sum(len(p) for p in plain), m.group(0)))
            i = m.end()
        plain.append(tgt[i:])
        text = "".join(plain)
        try:
            toks = TOKENIZE(text, engine="newmm")
        except Exception:
            toks = None
        if toks:
            bounds, pos = {0}, 0
            for t in toks:
                pos += len(t)
                bounds.add(pos)
            for off, tag in offsets:
                if (0 < off < len(text) and off not in bounds and off not in reported
                        and THAI.match(text[off - 1]) and THAI.match(text[off])):
                    reported.add(off)
                    add("Major",
                        f"Tag {tag!r} may sit inside a Thai word "
                        f"(…{text[max(0,off-8):off]}|{text[off:off+8]}…) — the tag "
                        "offset is not a token boundary. Tokenizer evidence only; "
                        "verify against the source before acting.",
                        "Move the tag to a word boundary if it really is mid-word")

    # 4: space inserted just inside a tag boundary, absent from source
    for op, cl in pair_literals(tgt).items():
        if re.search(re.escape(op) + r"\s", tgt) and not re.search(re.escape(op) + r"\s", src):
            add("Minor", f"Space inserted right after opening tag {op} — renders as a "
                         "stray space at the start of the tagged span",
                "Write the space outside the tag")
        if re.search(r"\s" + re.escape(cl), tgt) and not re.search(r"\s" + re.escape(cl), src):
            add("Minor", f"Space inserted right before closing tag {cl} — renders as a "
                         "stray space at the end of the tagged span",
                "Write the space outside the tag")
    return fs


def die(msg):
    """One-line diagnostic, no traceback — the caller is usually a pipeline."""
    sys.exit(f"tag_integrity: {msg}")


def load_segments(path):
    """Read and validate the segment file. Every failure mode names itself."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        die(f"cannot read {path}: {e.strerror or e}")
    except UnicodeDecodeError:
        die(f"{path} is not valid UTF-8")
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})")
    if not isinstance(data, list):
        die(f"{path} must hold a JSON array of segments, found a "
            f"{type(data).__name__} at the top level")
    for i, seg in enumerate(data):
        if not isinstance(seg, dict):
            die(f"{path}: segment #{i} is a {type(seg).__name__}, expected an object "
                'like {"id": ..., "source": ..., "target": ...}')
        if "id" not in seg:
            die(f'{path}: segment #{i} has no "id" field')
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    segs = load_segments(a.segments)
    findings = []
    for seg in segs:
        findings += check_segment(seg)
    sev = Counter(f["severity"] for f in findings)
    out = {"findings": findings,
           "stats": {"segments": len(segs), "findings": len(findings),
                     "by_severity": dict(sev),
                     "thai_tokenizer": "available (tokenizer-gated word checks: Thai only; "
                         "grapheme-cluster check: all scripts, no dependency)" if TOKENIZE else
                         "UNAVAILABLE — pythainlp not installed; BOTH tokenizer-gated "
                         "Thai word checks (3a2 boundary disagreement AND 3b lexical-unit "
                         "join) were SKIPPED. pip install pythainlp"}}
    if TOKENIZE is None:
        print("WARNING: pythainlp not installed — Thai word checks 3a2 and 3b skipped "
              "(grapheme-cluster check 3a1 still ran)",
              file=sys.stderr)
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.output:
        open(a.output, "w", encoding="utf-8").write(text)
        print(f"{len(findings)} findings → {a.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
