#!/usr/bin/env python3
"""Deterministic technical QA checks for bilingual segment files.

Usage:
  python qa_checks.py segments.json [--dnt dnt.txt] [--glossary glossary.json] [-o findings.json]

Input segments.json: [{"id": 1, "source": "...", "target": "..."}, ...]
Optional glossary.json: [{"source": "invoice", "target": "ใบแจ้งหนี้"}, ...]
Optional dnt.txt: one do-not-translate term per line.

Output: {"findings": [{"segment_id", "category", "severity", "description",
                       "suggested_fix", "found_by": "Script(qa_checks)"}], "stats": {...}}

Severities emitted here are DEFAULTS — every finding still goes through
orchestrator arbitration (e.g. a "number mismatch" may be a legitimate
Buddhist Era year conversion; a glossary miss on a mandated term should be
re-graded up to Major per the severity table).

Checks, per segment (the list SKILL.md Phase 4 points at):
  * empty target (Critical) · target identical to source (Major — suppressed
    when nothing translatable remains after removing tags, DNT terms, codes
    and URLs: a Latin scientific name with catalogue numbers, a tag-only field)
  * placeholders & inline tags, both directions (Critical missing / Major added)
  * URLs and emails, both directions (Major)
  * HTML entities not carried over (Minor)
  * number values, digit-script- and separator-canonicalized, incl.
    space/NBSP thousands grouping (Major missing / Minor added)
  * whitespace: leading/trailing, double space, line-break count (Minor)
  * typographic punctuation the target drops — curly quotes flattened to
    straight, ellipsis — substitute-set-gated per locale (Minor; see
    punct_losses — dashes deliberately NOT checked, rationale there)
  * space injected next to a +/−/± sign the source writes tight (Minor;
    signs only — see spacing_slips for why %, ‰, ° are excluded)
  * length-ratio outliers (Minor)
  * do-not-translate violations, matched-span-verified (Major)
  * glossary adherence, expected-target check (Minor, re-grade at arbitration)
  * identical source with different targets across segments (Major,
    whole-file check — inconsistent terminology on repeated strings)
"""
import argparse, json, re, sys, unicodedata
from collections import Counter

FOUND_BY = "Script(qa_checks)"

# Ordered: extracted with masking so {{var}} is never re-matched as {var},
# and numbers inside placeholders/URLs are not double-counted.
# CAT half-tokens ({n> / <n}, Memsource/Phrase bilinguals) MUST come first:
# they are half-tokens, so the {var} pattern sees `{1>Brand<1}` as ONE token when
# the tag hugs the text but NOT when a space sits inside (`{1>Brand <1}`) — a
# guaranteed false "tag added/missing" pair — and their digits would otherwise
# be counted as content numbers. Set/order/word-boundary checks for these tags
# live in tag_integrity.py; here they are only masked and count-compared.
PLACEHOLDER_PATTERNS = [
    r"\{\d+>|<\d+\}",               # Memsource inline tag halves {1> … <1}
    r"\{\{[^{}]+\}\}",              # {{var}}
    r"%\([\w]+\)[sdif]",            # %(name)s
    r"%\d*\$?[sdif](?![A-Za-z])",   # %s, %1$s — not 50%iger / %20file
    r"\{[^{}\s]+\}",                # {var}, {0}
    r"</?[a-zA-Z][^>]*>",           # HTML/inline tags
    r"\\[nrt]",                     # literal escapes
]
# Real entities only (not "R&D;"); missing entity is Minor (decoding to plain
# text, e.g. &amp; -> และ, is usually legitimate).
ENTITY_RE = re.compile(r"&(?:amp|lt|gt|nbsp|quot|apos|copy|reg|trade|hellip|mdash|ndash|#\d+|#x[0-9a-fA-F]+);")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# \d covers every Unicode decimal digit (Thai ๐-๙, Arabic-Indic ٠-٩, Khmer ០-៩,
# Devanagari, Myanmar, Persian, …). canon_num MUST canonicalize the same set, so
# it goes through unicodedata.digit per character rather than a fixed table —
# a hardcoded table silently turns every unlisted script into a false mismatch.
NUM_RE = re.compile(r"\d[\d,.:]*\d|\d")
# Space-grouped thousands (French/Russian/Nordic "1 000 000", incl. NBSP and
# narrow NBSP) — NUM_RE would split these into separate tokens, yielding a
# false "missing" AND a false "invented" on a correct target. Shape-gated:
# only a leading group of 1-3 digits followed by groups of exactly 3 merges,
# so adjacent independent numbers ("2026 300 people") are left alone.
_GROUPED_NUM = re.compile(r"(?<!\d)\d{1,3}(?:[   ]\d{3})+(?!\d)")
_GROUP_SEP = re.compile(r"[   ]")

def ungroup_spaces(text):
    """Collapse space-style thousands separators inside a grouped number."""
    return _GROUPED_NUM.sub(lambda m: _GROUP_SEP.sub("", m.group(0)), text)
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_./]*$")   # SKU-8842-XL etc.
CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")
# A "." or "," followed by 1-2 digits at the very end of a token reads as a
# decimal mark in every locale that uses either; longer tails are thousands
# groups. ":" is never a separator here — it keeps 10:30 distinct from 1030.
DECIMAL_TAIL_RE = re.compile(r"[.,](\d{1,2})$")

def strip_trailing_punct(tok):
    return tok.rstrip(".,;:!?)»”’")

def clean_tok(tok):
    """Drop mask bytes so an already-masked span inside a token can never reach
    a finding description."""
    return tok.replace("\x00", "")

def canon_digits(tok):
    """Map every Unicode decimal digit to its ASCII value, leave anything else."""
    out = []
    for ch in tok:
        try:
            out.append(str(unicodedata.digit(ch)))
        except (TypeError, ValueError):
            out.append(ch)
    return "".join(out)

def canon_num(tok):
    """Canonical numeric value: unify digit scripts, normalize the decimal mark,
    drop thousands separators. Deliberately conservative — "1.5" must NOT
    collapse to "15" and "10:30" must NOT collapse to "1030", or real omissions
    go unreported."""
    t = canon_digits(tok)
    frac = ""
    m = DECIMAL_TAIL_RE.search(t)
    if m:
        frac, t = "." + m.group(1), t[:m.start()]
    return t.replace(",", "").replace(".", "") + frac

def extract_masked(text):
    """Extract placeholder tokens in priority order, masking each match so
    later patterns and the number check never see it. Returns (Counter, masked)."""
    found, masked = Counter(), text
    for p in PLACEHOLDER_PATTERNS:
        def repl(m):
            found[clean_tok(m.group(0))] += 1
            return "\x00" * len(m.group(0))
        masked = re.sub(p, repl, masked)
    return found, masked

def mask_pattern(rex, text, clean=lambda t: t):
    found, out = Counter(), text
    def repl(m):
        tok = clean(clean_tok(m.group(0)))
        found[tok] += 1
        return "\x00" * len(m.group(0))
    out = rex.sub(repl, out)
    return found, out

def has_letters(s):
    return any(unicodedata.category(c).startswith("L") for c in s)

def translatable_residue(text, dnt):
    """What is left of `text` once inline tags/placeholders, every DNT term,
    code-like tokens and URLs/emails are removed. An identical target is only
    suspicious when this residue still has letters: a segment that is nothing
    but a Latin scientific name plus catalogue numbers, or a tag-only field
    ({g5}{x7}{/g5}), is EXPECTED to come back unchanged — flagging it is a known
    false-positive class, and the raw-text test ("{g5}" contains a letter) fell
    straight into it."""
    _, out = extract_masked(text)
    out = URL_RE.sub(" ", out)
    out = EMAIL_RE.sub(" ", out)
    for term in sorted(dnt, key=len, reverse=True):
        if term:
            # whole-term match only: a DNT entry "Log" must not eat the "Log"
            # of an untranslated "Logging"
            out = re.sub(ascii_boundary(term), " ", out)
    # A code is a token that carries a digit or a code separator (SKU-8842,
    # v2.1, DSM10663), or a short all-caps prefix glued to a LONG number by a
    # space (a catalogue accession "DSM 10663"). A bare all-caps WORD is not a
    # code, and neither is a heading like "STEP 1" or "TABLE 2": "ADD TO CART"
    # left untranslated must still be flagged, and so must those.
    out = re.sub(r"(?<![A-Za-z0-9])[A-Z]{2,5}\s+\d{3,}(?![A-Za-z0-9])", " ", out)
    out = " ".join(tok for tok in out.split()
                   if not (CODE_RE.match(tok) and re.search(r"[0-9\-_./]", tok)))
    return out

def ascii_boundary(term):
    """Word-boundary regex safe next to Thai/CJK text (ASCII boundary only)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)

# --- typographic punctuation -------------------------------------------------
# A source glyph is only reported when the target carries NOTHING from its
# substitute set. The sets exist because the "loss" is often a correct locale
# swap: “ ” -> 「 」 in Japanese, “ ” -> « » in French. Without them this
# check is a false-positive generator on every non-Latin target — the same
# untested-language-assumption bug class as bare adjacency and non-Arabic
# digits. Straight quotes are deliberately IN the quote set for the "any quote
# at all" test, and handled separately by the flattening rule below, which is
# the defect that actually recurs.
#
# DASHES ARE DELIBERATELY NOT CHECKED — do not add them back. Whether an
# em/en dash may survive into the target is a per-locale STYLE-GUIDE POLICY,
# not a mechanical property: client guides routinely mandate REPLACING an
# em dash with target-language punctuation or a conjunction (so "source has
# it, target doesn't" is the CORRECT outcome there), while other locales keep
# it. A script that cannot read the target locale's guide fires wrongly in
# one direction or the other — in a replacement-mandating locale, every
# "loss" it flags is the correct outcome, so it yields false positives on
# correct files and blesses the actual defect. Dash handling belongs to the
# Phase 3 editor, who holds the style guide (SKILL.md Phase 3 scope B names
# it). Same principle as SIGNS ONLY below (spacing_slips excluding %/‰/°).
_QUOTES_CURLY = "“”‘’«»„‚‹›"
_QUOTES_CJK = "「」『』"
_QUOTES_STRAIGHT = "\"'"
_QUOTE_ANY = _QUOTES_CURLY + _QUOTES_CJK + _QUOTES_STRAIGHT

# glyph -> (label, substitute STRINGS that count as "still represented").
# Substring test, not char test: "．．" (doubled fullwidth stop) counts, a lone
# "．" does not — a single fullwidth full stop anywhere in a CJK target is
# ordinary sentence punctuation, not an ellipsis. "⋯" (U+22EF) covers the
# doubled "⋯⋯" form standard in Traditional Chinese.
PUNCT_CLASSES = [
    ("…", "ellipsis", ("…", "⋯", "．．")),
]

# U+2019 between letters is an APOSTROPHE (don’t, l’heure, James’s), not a
# quotation mark — testing it as a quote fires on every English contraction
# translated into a quote-less script. Strip only the intra-word case; a
# trailing possessive apostrophe (James’) is left in and may still read as a
# closing quote — conservative, but the intra-word form is the common one.
_INTRAWORD_APOS = re.compile(r"(?<=\w)\u2019(?=\w)")

def punct_losses(src, tgt):
    """Yield (span, message) for typographic punctuation the target drops.

    Presence-based, not count-based: one surviving glyph from the substitute
    set satisfies the class, so "two ellipses in, one out" is not reported.
    That miss is accepted — counting would false-positive on legitimate
    merges of truncation cues. Callers
    should pass MASKED text (placeholders/URLs blanked) so a glyph inside a
    URL or placeholder neither fires nor satisfies the check.
    """
    src = _INTRAWORD_APOS.sub('', src)
    out = []
    for glyph, label, subs in PUNCT_CLASSES:
        if glyph in src and not any(s in tgt for s in subs):
            # "..." spelled out is a legitimate ellipsis rendering
            if glyph == "…" and "..." in tgt:
                continue
            out.append((glyph, f"Source {label} {glyph!r} has no counterpart in the "
                               "target — verify the truncation/continuation cue was "
                               "not silently dropped."))
    if any(c in src for c in _QUOTES_CURLY):
        if not any(c in tgt for c in _QUOTE_ANY):
            out.append(("“”", "Source uses typographic quotation marks; the "
                                        "target has no quotation marks at all."))
        elif (not any(c in tgt for c in _QUOTES_CURLY + _QUOTES_CJK)
              and any(c in tgt for c in _QUOTES_STRAIGHT)):
            out.append(("“”", "Typographic quotation marks flattened to straight "
                                        "quotes in the target. Locale-appropriate pairs "
                                        "(「」, « », „ “) are fine; "
                                        "\" is usually not."))
    return out

# A sign the source writes tight against its digit, spaced in the target
# ("UTC+04:00" -> "UTC+ 04:00"). Deliberately narrow: the sign must appear in
# the source, the source must NOT already space it, and the target must.
#
# SIGNS ONLY - %, per-mille and degree are deliberately excluded. French,
# Russian and Swedish typography put a space before %, and "20 °C" is the
# SI-recommended form, so flagging those would fire on correct targets in
# several locales - the same untested-language-assumption trap as bare
# adjacency and non-Arabic digits. No locale writes "+ 04:00", which is why
# the sign case is safe to check without knowing the target language.
# (?<!\d) on the tight form: "3-5" is a RANGE, not a signed number — without
# the lookbehind a range in the source opens the gate and a spaced range in
# the target ("3 - 5", legitimate typography) fires. The loose form gets a
# rstrip-based guard instead, because "digit, spaces, hyphen" needs a
# variable-length look-back a regex lookbehind cannot express.
_SIGN_TIGHT = re.compile(r"(?<!\d)[+\-−±]\d")
_SIGN_LOOSE = re.compile(r"[+\-−±][   ]+\d")

def spacing_slips(src, tgt):
    if not _SIGN_TIGHT.search(src) or _SIGN_LOOSE.search(src):
        return []
    out = set()
    for m in _SIGN_LOOSE.finditer(tgt):
        pre = tgt[:m.start()].rstrip("   ")
        if pre and pre[-1].isdigit():
            continue  # digit … sign … digit with spacing = a spaced range
        out.add(m.group(0))
    return sorted(out)

def check_segment(seg, dnt, glossary):
    fs = []
    sid = seg["id"]
    src = str(seg.get("source") or "")
    tgt = str(seg.get("target") or "")
    add = lambda cat, sev, desc, fix="": fs.append(dict(
        segment_id=sid, category=cat, severity=sev, description=clean_tok(desc),
        suggested_fix=clean_tok(fix), found_by=FOUND_BY))

    if not src.strip():
        return fs                      # blank/spacer segment — nothing to check
    if not tgt.strip():
        add("Accuracy", "Critical", "Empty target segment", "Translate the segment")
        return fs

    identical = src.strip() == tgt.strip()
    if (identical and len(src.strip()) > 3
            and src.strip() not in dnt and not CODE_RE.match(src.strip())
            and has_letters(translatable_residue(src, dnt))):
        add("Accuracy", "Major", "Target identical to source (possibly untranslated)")

    # placeholders / tags (masked extraction)
    ps, src_m = extract_masked(src)
    pt, tgt_m = extract_masked(tgt)
    for tok, n in (ps - pt).items():
        add("Markup", "Critical", f"Placeholder/tag missing in target: {tok!r} (×{n})",
            "Restore the exact token")
    for tok, n in (pt - ps).items():
        add("Markup", "Major", f"Placeholder/tag added in target: {tok!r} (×{n})",
            "Remove or match source")

    # URLs / emails FIRST — a query string legitimately contains entities
    # (?a=1&amp;b=2). Masking entities before URLs shreds the URL, so the two
    # sides no longer compare equal and the mask bytes leak into the message.
    # Strip sentence-final punctuation; check BOTH directions.
    for rex, label in ((URL_RE, "URL"), (EMAIL_RE, "email")):
        s_set, src_m = mask_pattern(rex, src_m, strip_trailing_punct)
        t_set, tgt_m = mask_pattern(rex, tgt_m, strip_trailing_punct)
        for tok in (s_set - t_set):
            add("Markup", "Major", f"{label} missing or altered in target: {tok}")
        for tok in (t_set - s_set):
            add("Markup", "Major", f"{label} added in target (not in source): {tok}",
                "Remove unless intentionally localized")

    # HTML entities — Minor: decoding to plain text is often legitimate.
    # Entities inside a URL were consumed above and are not re-reported here.
    es, src_m = mask_pattern(ENTITY_RE, src_m)
    et, tgt_m = mask_pattern(ENTITY_RE, tgt_m)
    for tok in (es - et):
        add("Markup", "Minor", f"HTML entity {tok!r} not carried over — verify it was "
            "correctly decoded (e.g. &amp; → and/และ) rather than lost")

    # numbers — canonical compare (Thai/Arabic-Indic digits, separators unified,
    # space/NBSP thousands grouping collapsed on BOTH sides first)
    s_nums = Counter(canon_num(t) for t in NUM_RE.findall(ungroup_spaces(src_m)))
    t_nums = Counter(canon_num(t) for t in NUM_RE.findall(ungroup_spaces(tgt_m)))
    missing, added = s_nums - t_nums, t_nums - s_nums
    if missing:
        add("Locale", "Major",
            f"Number values in source not found in target: {sorted(missing)} "
            "(digit script/separators already normalized; verify — may be a "
            "legitimate conversion, e.g. Buddhist Era year)")
    if added and not identical:
        add("Accuracy", "Minor",
            f"Number values in target with no source counterpart: {sorted(added)} "
            "— verify not invented")

    # whitespace / structure
    if tgt != tgt.strip():
        add("Linguistic", "Minor", "Leading/trailing whitespace in target", tgt.strip())
    if "  " in tgt and "  " not in src:
        add("Linguistic", "Minor", "Double space in target (not present in source)")
    if src.count("\n") != tgt.count("\n"):
        add("Design", "Minor",
            f"Line-break count differs (source {src.count(chr(10))}, target {tgt.count(chr(10))}) "
            "— verify intentional")

    # typographic punctuation the source carries and the target drops.
    # Masked strings on purpose: a quote or ellipsis living inside a URL or
    # placeholder must neither fire the check nor satisfy it for a loss in
    # running text.
    for span, msg in punct_losses(src_m, tgt_m):
        add("Locale", "Minor", msg, span)

    # a space injected next to a +/-/± sign the source writes tight
    # ("UTC+04:00" -> "UTC+ 04:00", "-5°" -> "- 5°"). Signs only — the
    # rationale for excluding %, per-mille and degree is above spacing_slips.
    # The number check cannot see this: the value is intact, only the
    # spacing moved.
    loose = spacing_slips(src_m, tgt_m)
    if loose:
        add("Locale", "Minor",
            "Space inserted next to a sign that the source writes "
            f"tight: {loose}. The number value is unchanged, so the number check "
            "cannot see this.")

    # length ratio (skip very short; relax floor for compact CJK scripts)
    if len(src) >= 15 and has_letters(src):
        ratio = len(tgt) / max(1, len(src))
        floor = 0.15 if CJK_RE.search(tgt) else 0.3
        if ratio < floor:
            add("Accuracy", "Minor", f"Target suspiciously short (ratio {ratio:.2f}) — check for omission")
        elif ratio > 3.0:
            add("Accuracy", "Minor", f"Target suspiciously long (ratio {ratio:.2f}) — check for addition")

    # Do-not-translate terms (ASCII word boundary on source side). Detection is
    # case-insensitive, so verification MUST run against the span actually
    # matched in the source, not the list spelling: a source that writes GITHUB
    # and a target that keeps GITHUB is faithful, and comparing against the
    # listed "GitHub" would call it a defect.
    for term in dnt:
        if not term:
            continue
        if term.isascii():
            spans = {m.group(0) for m in ascii_boundary(term).finditer(src)}
        else:
            spans = {term} if term in src else set()
        for span in sorted(spans):
            if span not in tgt:
                add("Terminology", "Major", f"DNT term altered or missing: {span!r}",
                    "Keep the term exactly as in source")

    # glossary (boundary-aware on both sides where terms are ASCII)
    for g in glossary:
        gs, gt_term = g.get("source", ""), g.get("target", "")
        if not gs or not gt_term:
            continue
        src_hit = (ascii_boundary(gs).search(src) if gs.isascii() else gs in src)
        tgt_hit = (ascii_boundary(gt_term).search(tgt) if gt_term.isascii()
                   else gt_term in tgt)
        if src_hit and not tgt_hit:
            add("Terminology", "Minor",
                f"Glossary term {gs!r} → expected {gt_term!r} not found in target "
                "(re-grade to Major at arbitration if the term is mandated)",
                f"Use {gt_term!r} unless context justifies otherwise")
    return fs

def die(msg):
    """One-line diagnostic, no traceback — the caller is usually a pipeline."""
    sys.exit(f"qa_checks: {msg}")

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
    ap.add_argument("--dnt")
    ap.add_argument("--glossary")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    segs = load_segments(a.segments)
    try:
        dnt = [l.strip() for l in open(a.dnt, encoding="utf-8") if l.strip()] if a.dnt else []
    except OSError as e:
        die(f"cannot read {a.dnt}: {e.strerror or e}")
    if a.glossary:
        try:
            with open(a.glossary, encoding="utf-8") as f:
                glossary = json.load(f)
        except OSError as e:
            die(f"cannot read {a.glossary}: {e.strerror or e}")
        except json.JSONDecodeError as e:
            die(f"{a.glossary} is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})")
        if not isinstance(glossary, list):
            die(f"{a.glossary} must hold a JSON array of "
                '{"source": ..., "target": ...} entries')
    else:
        glossary = []

    findings = []
    for seg in segs:
        findings += check_segment(seg, dnt, glossary)

    # cross-segment: identical source must yield identical target (repeated SEO
    # strings, duplicated CTAs). Cheap, and a human diff misses it easily.
    # Sources are coerced ONCE and reused — a numeric source cell arrives as an
    # int and .strip() on the raw value would take the whole run down.
    from collections import defaultdict
    by_src = defaultdict(list)
    for seg in segs:
        key = str(seg.get("source") or "").strip()
        if key:
            by_src[key].append(seg)
    for group in by_src.values():
        if len(group) > 1 and len({str(g.get("target") or "").strip() for g in group}) > 1:
            ids = [g["id"] for g in group]
            findings.append(dict(
                segment_id=ids[0], category="Terminology", severity="Major",
                description=f"Identical source text in segments {ids} has differing "
                            "targets — unify unless context genuinely differs",
                suggested_fix="Pick one rendering and apply it to all listed segments",
                found_by=FOUND_BY))

    sev = Counter(f["severity"] for f in findings)
    out = {"findings": findings,
           "stats": {"segments": len(segs), "findings": len(findings),
                     "by_severity": dict(sev)}}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.output:
        open(a.output, "w", encoding="utf-8").write(text)
        print(f"{len(findings)} findings → {a.output}", file=sys.stderr)
    else:
        print(text)

if __name__ == "__main__":
    main()
