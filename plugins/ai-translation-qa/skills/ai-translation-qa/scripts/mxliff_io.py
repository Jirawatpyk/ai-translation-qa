#!/usr/bin/env python3
"""mxliff_io.py — extract/apply for Phrase (Memsource) MXLIFF bilingual files.

The Phrase/ATMS counterpart of sdlxliff_io.py. Same two subcommands, same edit
format, same refusal contract — so a caller can switch CAT formats without
changing its own code.

  extract  IN.mxliff [-o segments.json]
      Emit a JSON array, one object per trans-unit, in file order:
        {"id": 1,                       # sequential, 1-based == Phrase's
                                        #   segment number in the editor
                                        #   (an int here; apply matches str(id))
         "tu": "<trans-unit id>",       # opaque task-id:index string,
                                        #   e.g. "aB3xK9mQvRtY7wZp2LhN4:0"
         "source": "...", "target": "...",
         "origin": "mt|tm|null",        # m:trans-origin
         "score": 1.0, "gross_score": 1.0,
         "confirmed": false, "locked": false,
         "tm_class": "reuse|fuzzy|new",
         "source_tokens": [], "target_tokens": [],   # inline-tag tokens found
         "mt_suggestion": "...",        # alt-trans origin="machine-trans"
         "tm_suggestion": "...",        # alt-trans origin="memsource-tm"
         "tm_quality": 0.99,
         "key": "KEY-001…"}             # x-key context of the enclosing
                                        #   group, when present
      With -o, a summary JSON is printed to stdout: {segments, confirmed,
      human_pass, by_tm_class, tagged_segments, output}. human_pass is the
      confirmed>0 heuristic — "no segment confirmed over an mt/tm origin means
      no human has been through the file"; a file that arrives fully confirmed
      still tells you nothing about review depth.
      Inline elements (bpt/ept/ph/it/x/g) are rendered as {g5}…{/g5}, {x7},
      {ph3} tokens so qa_checks.py / tag_integrity.py can diff them. Phrase's
      OWN textual tag notation ({1> … <1}) is ordinary character data and comes
      through untouched — that is the notation tag_integrity.py checks.

  apply    IN.mxliff EDITS.json -o OUT.mxliff [--set-confirmed]
      EDITS.json, using extract's sequential ids, in any of:
        {"<id>": "new target", ...}
        {"<id>": {"target": "new target", "old": "what extract saw"}, ...}
        [{"id": ..., "target": "...", "old": "..."}, ...]
      "old" is OPTIONAL but strongly recommended as a DRIFT GUARD (apply
      re-reads the file, so an edit list written against a stale extract would
      otherwise land on whatever the segment holds now).
      Rules enforced:
        * refuses to write over IN — compared by real path
        * refuses locked segments
        * TAGGED segments (inline XML elements — bpt/ept/ph/it/x/g, which
          extract renders as {g5}…{/g5} / {x7} tokens) are rewritten when the
          edit carries exactly the SOURCE's token multiset with {gN} pairs
          properly nested: the target's elements are rebuilt by cloning the
          source's (same ids, same attributes, same native tag code) around
          the new text. Any other tagged edit is refused as a soft skip — a
          token set that differs from the source's, a token the source lacks,
          bad nesting, or a target holding structure beyond inline tags. The
          source is the authority, not the current target. NOTE: Phrase's own
          textual notation ({1> … <1}) is plain character data, not an
          element — apply writes it as text, exactly as it arrived.
        * a plain-text edit on a target that currently carries inline
          elements is refused (it would drop the tags); a plain-text edit on
          a tag-free target whose SOURCE carries elements is applied with a
          warning (Phrase QA will flag the missing tags)
        * leaves m:confirmed alone unless --set-confirmed is passed, which
          sets m:confirmed="1" on applied segments only. Default is OFF: a
          delivered MXLIFF that arrives pre-confirmed skips the linguist's
          review step in Phrase, and that has to be an explicit choice.
        * never touches <alt-trans> — the MT/TM suggestions are evidence
      Prints a JSON report to stdout:
        {applied, applied_ids, applied_tagged_ids, skipped, hard_skips,
         warnings, confirmed_set, output}
        (confirmed_set echoes whether --set-confirmed was active)
      Exit code 0 when hard_skips is 0 (soft skips are the documented
      contract), 2 otherwise.

Traps this script exists to absorb — do not regress on these:
  * **<target> is not unique.** Each trans-unit has its own <target>, and so
    does every <alt-trans> child (machine-trans, memsource-tm, …) — a modest
    file routinely holds several times more <target> elements than segments.
    Anything that iterates or regexes on "target" rewrites the MT/TM
    suggestions — silently, because the file stays well-formed and Phrase
    still imports it.
  * **No BOM, and the declaration uses single quotes** (<?xml version='1.0'
    encoding='UTF-8'?>) — the opposite of SDLXLIFF on both counts. Do not add
    a BOM "for consistency".
  * **m:confirmed answers "who wrote this draft".** All segments at
    m:confirmed="0" with m:trans-origin="mt"/"tm" means the file is raw
    pre-translation that no human has been through — read the flag instead of
    asking. m:score/m:gross-score give the TM class for free.
  * Empty <target/> is normal (unstarted segments, and every alt-trans slot
    that has no candidate). Do not treat it as a parse failure.
  * trans-unit count == segment count here (unlike SDLXLIFF, where one
    trans-unit can hold many <mrk mtype="seg">). It still says nothing about
    whether every SOURCE row reached the file — diff against the source export
    when one exists.
"""
import argparse, copy, io, json, os, re, sys
from collections import Counter
from lxml import etree

X = '{urn:oasis:names:tc:xliff:document:1.2}'
M = '{http://www.memsource.com/mxlf/2.0}'
PLACEHOLDER_TAGS = {'bpt', 'ept', 'ph', 'it', 'x', 'g'}
# Tokens _render emits, and the ONLY things apply turns back into elements.
# Grammar: {g5}…{/g5} is a pair (wraps content); {x7} {ph3} {bpt1} {ept1} {it2}
# are standalone. A token that names no source element cannot round-trip and
# is refused (see _rebuild_tagged). Same grammar as sdlxliff_io.py.
TOKEN_LIKE = re.compile(r'\{(/?)(%s)(\d*)\}' % '|'.join(sorted(PLACEHOLDER_TAGS)))
# Control characters XML 1.0 cannot store at all (tab/LF/CR are fine).
_XML_BAD = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def die(msg):
    sys.exit('mxliff_io: ' + msg)


def _render(el, tokens):
    """Flatten an element to text, replacing inline tags with {tok} tokens.

    Returns the text; appends every emitted token to `tokens` so the caller can
    tell a plain-text segment from a tagged one without re-walking.
    """
    parts = []

    def walk(node):
        for child in node:
            # Comments and processing instructions have a callable .tag, not a
            # name — QName() raises on them. They carry no visible text of their
            # own, but the text AFTER them is their .tail and must survive.
            if not isinstance(child.tag, str):
                if child.tail:
                    parts.append(child.tail)
                continue
            tag = etree.QName(child).localname
            cid = child.get('id') or child.get('rid') or ''
            if tag == 'g':
                # <g> WRAPS translatable content: emit the open token, then the
                # element's own .text, then recurse. Forgetting child.text here
                # silently swallows the whole wrapped string and the segment
                # reads as "{g1}{/g1}" — after ANY change to this walker,
                # re-test with a <g>-wrapped segment; a tag-free file passes
                # every byte-identical check while this bug eats content.
                tok_o, tok_c = '{g%s}' % cid, '{/g%s}' % cid
                tokens.extend([tok_o, tok_c])
                parts.append(tok_o)
                if child.text:
                    parts.append(child.text)
                walk(child)
                parts.append(tok_c)
            elif tag in PLACEHOLDER_TAGS:
                # bpt/ept/ph/it/x are standalone: their .text is the native tag
                # code (e.g. "<b>"), not content, so it is deliberately dropped.
                tok = '{%s%s}' % (tag, cid)
                tokens.append(tok)
                parts.append(tok)
            else:
                if child.text:
                    parts.append(child.text)
                walk(child)
            if child.tail:
                parts.append(child.tail)

    if el is None:
        return ''
    if el.text:
        parts.append(el.text)
    walk(el)
    return ''.join(parts)


def _inline_index(el, index=None):
    """token -> the SOURCE element it stands for ('{g5}' -> <g id="5">,
    '{x7}' -> <x id="7"/>). Walks exactly the structure _render tokenises, so
    the two never disagree about what a token means. Repeated ids map to the
    first occurrence. (Same contract as sdlxliff_io.py.)"""
    if index is None:
        index = {}
    if el is None:
        return index
    for child in el:
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child).localname
        cid = child.get('id') or child.get('rid') or ''
        if tag == 'g':
            index.setdefault('{g%s}' % cid, child)
            _inline_index(child, index)
        elif tag in PLACEHOLDER_TAGS:
            index.setdefault('{%s%s}' % (tag, cid), child)
        else:
            _inline_index(child, index)
    return index


def token_strings(text):
    """Every inline token in `text`, in order, as the literal strings _render
    emits ('{g5}', '{/g5}', '{x7}')."""
    return [m.group(0) for m in TOKEN_LIKE.finditer(text)]


def _rebuild_tagged(tgt, new_text, index, literal=frozenset()):
    """Rewrite a <target> from token-bearing text. Returns None on success,
    else a reason string (nothing is mutated on failure). Contract: every token
    names a source element, {gN} pairs nest properly, and the target holds
    nothing but inline tag elements, comments/PIs and text — any other child
    (a <mrk>, say) is structure this function cannot reproduce, so it refuses.
    (Same algorithm as sdlxliff_io.py, minus Studio's location bookmarks.)"""
    # `literal`: token-looking strings that are PLAIN TEXT in the source (a UI
    # placeholder like "{x}" with no <x/> element behind it) — written as text.
    stack, bpt_open = [], set()
    for m in TOKEN_LIKE.finditer(new_text):
        tok = m.group(0)
        if tok in literal:
            continue
        closing, name, num = m.group(1), m.group(2), m.group(3)
        if closing:
            if name != 'g':
                return 'token %s: only {gN} tokens have a closing form' % tok
            if not stack or stack[-1] != '{g%s}' % num:
                return 'token %s closes a pair that is not open (bad nesting)' % tok
            stack.pop()
            continue
        if tok not in index:
            return 'token %s names no inline element in the source' % tok
        if name == 'g':
            stack.append(tok)
        elif name == 'bpt':
            bpt_open.add(num)
        elif name == 'ept' and num not in bpt_open and ('{bpt%s}' % num) in index:
            # a paired-placeholder end before its start (when the source holds
            # both halves — a pair split across segments has only the end here):
            # the file would still parse and round-trip, and the span would be
            # broken in the tool
            return 'token %s precedes its {bpt%s} — paired placeholders must keep their order' % (tok, num)
    if stack:
        return 'unclosed pair(s) %s' % stack
    for child in tgt.iter():           # ALL depths: a <mrk> nested inside a <g>
        if child is tgt or not isinstance(child.tag, str):
            continue                   # would otherwise be flattened silently
        if etree.QName(child).localname not in PLACEHOLDER_TAGS:
            return ('target holds inline structure beyond tags (<%s>) that cannot '
                    'be rebuilt safely' % etree.QName(child).localname)
    keep = [c for c in tgt if not isinstance(c.tag, str)]  # comments / PIs
    for c in list(tgt):
        tgt.remove(c)
    tgt.text = None
    for c in keep:
        c.tail = None
        tgt.append(c)

    def put_text(container, text):
        if not text:
            return
        if len(container):
            last = container[-1]
            last.tail = (last.tail or '') + text
        else:
            container.text = (container.text or '') + text

    stack, pos = [tgt], 0
    for m in TOKEN_LIKE.finditer(new_text):
        if m.group(0) in literal:
            continue                   # plain text, consumed with the next slice
        put_text(stack[-1], new_text[pos:m.start()])
        pos = m.end()
        closing, name = m.group(1), m.group(2)
        tok = m.group(0)
        if closing:
            stack.pop()
            continue
        src_el = index[tok]
        if name == 'g':
            stack.append(etree.SubElement(stack[-1], src_el.tag, dict(src_el.attrib)))
        else:
            new_el = copy.deepcopy(src_el)
            new_el.tail = None
            stack[-1].append(new_el)
    put_text(stack[-1], new_text[pos:])
    return None


def _direct_target(tu):
    """The trans-unit's OWN <target>, never an <alt-trans> one.

    tu.find('{ns}target') already restricts to direct children — the explicit
    helper exists so nobody 'simplifies' this to tu.iter(), which would pick up
    every alt-trans target in the unit.
    """
    return tu.find(X + 'target')


def _fl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tm_class(origin, score):
    if origin != 'tm' or score is None:
        return 'new'
    if score >= 0.995:
        return 'reuse'
    return 'fuzzy' if score >= 0.5 else 'new'


def _iter_units(tree):
    """THE one definition of segment numbering (sequential, 1-based, document
    order). extract, apply, and the round-trip check must all iterate through
    here — a drifted copy of this loop would silently misnumber edits."""
    for i, tu in enumerate(tree.getroot().iter(X + 'trans-unit'), start=1):
        yield i, tu


def _parse(path):
    try:
        return etree.parse(path)
    except OSError as e:
        die('cannot read %s: %s' % (path, e.strerror or e))
    except etree.XMLSyntaxError as e:
        die('%s is not well-formed XML: %s' % (path, e))


def _alt(tu, origin):
    for a in tu.findall(X + 'alt-trans'):
        if a.get('origin') == origin:
            t = a.find(X + 'target')
            return (_render(t, []) if t is not None else ''), _fl(a.get('match-quality'))
    return None, None


def cmd_extract(args):
    tree = _parse(args.infile)
    out = []
    for i, tu in _iter_units(tree):
        src_tokens, tgt_tokens = [], []
        source = _render(tu.find(X + 'source'), src_tokens)
        target = _render(_direct_target(tu), tgt_tokens)
        score = _fl(tu.get(M + 'score'))
        origin = tu.get(M + 'trans-origin')
        mt, _ = _alt(tu, 'machine-trans')
        tm, tmq = _alt(tu, 'memsource-tm')
        key = None
        grp = tu.getparent()
        # Only read context from an actual enclosing <group>: a trans-unit that
        # sits directly under <body> has <body> as its parent, and a naive
        # .find('.//context') there walks the WHOLE file and attributes the
        # first x-key in the document to every ungrouped segment. Select by
        # context-type too — a group may list x-notes/x-uri before x-key.
        if (grp is not None and isinstance(grp.tag, str)
                and etree.QName(grp).localname == 'group'):
            for ctx in grp.findall('.//' + X + 'context'):
                if ctx.get('context-type') == 'x-key':
                    key = (ctx.text or '').strip() or None
                    break
        out.append({
            'id': i,
            'tu': tu.get('id'),
            'source': source,
            'target': target,
            'origin': origin,
            'score': score,
            'gross_score': _fl(tu.get(M + 'gross-score')),
            'confirmed': tu.get(M + 'confirmed') == '1',
            'locked': tu.get(M + 'locked') == 'true',
            'tm_class': _tm_class(origin, score),
            'source_tokens': src_tokens,
            'target_tokens': tgt_tokens,
            'mt_suggestion': mt,
            'tm_suggestion': tm,
            'tm_quality': tmq,
            'key': key,
        })
    blob = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(blob)
        n_conf = sum(1 for s in out if s['confirmed'])
        print(json.dumps({
            'segments': len(out),
            'confirmed': n_conf,
            'human_pass': n_conf > 0,   # 0 confirmed == raw pre-translation
            'by_tm_class': {c: sum(1 for s in out if s['tm_class'] == c)
                            for c in ('reuse', 'fuzzy', 'new')},
            'tagged_segments': sum(1 for s in out if s['source_tokens'] or s['target_tokens']),
            'output': args.output}, ensure_ascii=False, indent=1))
    else:
        print(blob)


def _parse_edits(path):
    """-> {id: (new_target, old_or_None)}. Accepts the flat dict, the dict of
    {target, old} objects, and the list form."""
    def one(v, where):
        if isinstance(v, dict):
            if 'target' not in v:
                die('edit for %s has no "target"' % where)
            t, old = v['target'], v.get('old')
        else:
            t, old = v, None
        # Validate BEFORE any tree mutation: a null target would crash midway
        # through apply, and an XML-incompatible control character would crash
        # tree.write after edits were already applied in memory.
        if not isinstance(t, str):
            die('edit for %s: "target" must be a string, found %s'
                % (where, type(t).__name__))
        bad = _XML_BAD.search(t)
        if bad:
            die('edit for %s: target contains control character U+%04X, which '
                'cannot be stored in XML' % (where, ord(bad.group(0))))
        if old is not None and not isinstance(old, str):
            die('edit for %s: "old" must be a string when present' % where)
        return t, old

    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except OSError as e:
        die('cannot read %s: %s' % (path, e.strerror or e))
    except json.JSONDecodeError as e:
        die('%s is not valid JSON: %s (line %d, column %d)'
            % (path, e.msg, e.lineno, e.colno))
    edits = {}
    if isinstance(raw, list):
        for i, e in enumerate(raw):
            if not isinstance(e, dict) or 'id' not in e:
                die('%s: edit #%d needs an "id"' % (path, i))
            edits[str(e['id'])] = one(e, 'id %s' % e['id'])
    elif isinstance(raw, dict):
        for k, v in raw.items():
            edits[str(k)] = one(v, 'id %s' % k)
    else:
        die('%s must hold a JSON object or array of edits, found a %s at the '
            'top level' % (path, type(raw).__name__))
    return edits


def cmd_apply(args):
    # Real paths: a symlink or a differently spelled path to the input is still
    # the input, and clobbering it destroys the only copy of the source state.
    if os.path.realpath(args.output) == os.path.realpath(args.infile):
        die('refusing to overwrite the input file — choose a different -o')
    try:
        raw = open(args.infile, 'rb').read()
    except OSError as e:
        die('cannot read %s: %s' % (args.infile, e.strerror or e))
    had_bom = raw.startswith(b'\xef\xbb\xbf')     # MXLIFF normally has none
    tree = _parse(args.infile)
    edits = _parse_edits(args.edits)

    applied, applied_tagged, skipped, warnings = [], [], [], []

    def skip(sid, reason, hard=True):
        skipped.append({'id': sid, 'reason': reason, 'hard': hard})

    seen = set()
    for i, tu in _iter_units(tree):
        sid = str(i)
        if sid not in edits:
            continue
        seen.add(sid)
        new, old = edits[sid]
        if tu.get(M + 'locked') == 'true':
            skip(sid, 'segment is locked')
            continue
        tgt = _direct_target(tu)
        if tgt is None:
            skip(sid, 'trans-unit has no <target> element')
            continue
        tokens = []
        live = _render(tgt, tokens)
        if old is not None and old != live:
            skip(sid, 'live target does not match provided old')
            continue
        src_tokens = []
        src_text = _render(tu.find(X + 'source'), src_tokens)
        # Token-looking strings that are plain text in the source ("{x}" as a
        # UI placeholder, no element behind it) stay plain text in the edit.
        # Both an element and literal text in one segment is ambiguous — refuse.
        literal = Counter(token_strings(src_text)) - Counter(src_tokens)
        if literal and set(literal) & set(src_tokens):
            skip(sid, 'source carries %s both as inline element(s) and as literal '
                      'text — an edit cannot say which is which; edit in the CAT '
                      'tool' % sorted(literal), hard=False)
            continue
        literal = frozenset(literal)
        new_tokens = [t for t in token_strings(new) if t not in literal]
        has_elements = any(isinstance(c.tag, str) for c in tgt)
        if new_tokens:
            # Tagged edit: the SOURCE tag set is the contract (multiset; nesting
            # is validated by the rebuild).
            if sorted(new_tokens) != sorted(src_tokens):
                skip(sid, 'edit tokens %s differ from the source tag set %s — a '
                          'target may only carry exactly the source\'s inline '
                          'tags; anything else needs the CAT tool'
                          % (new_tokens, src_tokens), hard=False)
                continue
            err = _rebuild_tagged(tgt, new, _inline_index(tu.find(X + 'source')), literal)
            if err:
                skip(sid, 'tagged edit refused: %s — edit in the CAT tool' % err,
                     hard=False)
                continue
            applied.append(sid)
            applied_tagged.append(sid)
            if args.set_confirmed:
                tu.set(M + 'confirmed', '1')
            continue
        if tokens or has_elements:
            skip(sid, 'edit carries no inline tokens but the live target holds %s '
                      '— applying it would silently drop the tags; put the tokens '
                      'back into the edit' % (tokens or 'inline elements'),
                 hard=False)
            continue
        if len(tgt):
            # children remain but none are elements: comments / processing
            # instructions. Rewriting .text would drop or orphan them — refuse
            # with an accurate reason rather than the misleading one above.
            skip(sid, 'target contains an XML comment or processing '
                      'instruction; rewriting would drop it — edit in the '
                      'CAT tool', hard=False)
            continue
        tgt.text = new
        applied.append(sid)
        if args.set_confirmed:
            tu.set(M + 'confirmed', '1')
        if src_tokens:
            warnings.append({'id': sid, 'warning':
                             'source carries inline elements %s but the new target '
                             'has none — Phrase QA will flag missing tags; confirm '
                             'this is intended' % src_tokens})

    unknown = sorted(set(edits) - seen, key=lambda x: int(x) if x.isdigit() else 0)
    for u in unknown:
        skip(u, 'id not found in file')

    buf = io.BytesIO()
    tree.write(buf, encoding='UTF-8', xml_declaration=True)
    data = buf.getvalue()
    # Reuse the INPUT's XML declaration verbatim (quote style, any standalone
    # attribute): lxml re-serializes the declaration in its own style, and
    # string-replacing one assumed style for another is dead code the moment
    # the lxml build or the input differs. Splicing needs no assumption about
    # either side.
    src_head = raw[3:] if had_bom else raw
    m_in = re.match(rb'<\?xml[^>]*\?>', src_head)
    if m_in and data.startswith(b'<?xml'):
        data = m_in.group(0) + data[data.index(b'?>') + 2:]
    if had_bom and not data.startswith(b'\xef\xbb\xbf'):
        data = b'\xef\xbb\xbf' + data
    with open(args.output, 'wb') as f:
        f.write(data)

    # round-trip sanity check: re-parse and confirm every APPLIED target reads
    # back exactly as written. Scope honesty: unapplied targets and alt-trans
    # elements are NOT re-compared here — their preservation is the job of the
    # tree-based editing above (only seg-target text nodes are ever touched),
    # not of this check.
    check = _parse(args.output)
    drift = []
    for i, tu in _iter_units(check):
        sid = str(i)
        if sid in applied:
            got = _render(_direct_target(tu), [])
            if got != edits[sid][0]:
                drift.append(sid)
    if drift:
        die('round-trip check failed for id(s) %s — output not trustworthy'
            % ', '.join(drift))

    hard = sum(1 for k in skipped if k['hard'])
    print(json.dumps({'applied': len(applied), 'applied_ids': applied,
                      'applied_tagged_ids': applied_tagged,
                      'skipped': skipped, 'hard_skips': hard,
                      'warnings': warnings,
                      'confirmed_set': bool(args.set_confirmed),
                      'output': args.output}, ensure_ascii=False, indent=1))
    if hard:
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('extract', help='MXLIFF -> bilingual JSON')
    e.add_argument('infile')
    e.add_argument('-o', '--output')
    e.set_defaults(func=cmd_extract)
    a = sub.add_parser('apply', help='write edited targets into a copy')
    a.add_argument('infile')
    a.add_argument('edits', help='JSON: {"id": "new target", ...} or [{id, target}]')
    a.add_argument('-o', '--output', required=True)
    a.add_argument('--set-confirmed', action='store_true',
                   help='also set m:confirmed="1" on applied segments '
                        '(off by default — see the module docstring)')
    a.set_defaults(func=cmd_apply)
    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
