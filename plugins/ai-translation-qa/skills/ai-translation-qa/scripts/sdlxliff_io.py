#!/usr/bin/env python3
"""sdlxliff_io.py — extract/apply for SDL Trados Studio SDLXLIFF files.

Two subcommands:

  extract  IN.sdlxliff [-o segments.json]
      Emit a JSON array of segments:
        {"id": "12",                 # sequential, 1-based, stable per file
         "tu": "<trans-unit id>",    # trans-unit GUID
         "mid": "12",               # mrk mid inside the trans-unit
         "source": "...", "target": "...",
         "conf": "Translated", "origin": "tm",
         "origin_system": "<TM or MT provider name, when Studio recorded one>",
         "prev_origin": [{"origin": "mt", "origin_system": "...", "percent": ...}],
         "percent": "85", "locked": false,
         "tm_class": "reuse|fuzzy|new"}
      origin="interactive" means a linguist EDITED the segment, not that they
      typed it from scratch: Studio pushes the earlier state into prev_origin, so
      interactive over a prev_origin of mt is post-edited MT. Read the chain
      before calling a segment human work (Mode D).
      Inline non-seg elements (g/x/bpt/ept/ph/it) are rendered as placeholder
      tokens {g5}...{/g5}, {x7}, {ph3} so qa_checks.py can diff them. Empty
      x-sdl-location bookmark mrks are invisible in extracted text (they carry
      no content) but are preserved on apply.

  apply    IN.sdlxliff EDITS.json -o OUT.sdlxliff
      EDITS.json, using extract's sequential ids, in any of:
        {"<id>": "new target", ...}
        {"<id>": {"target": "new target", "old": "what extract saw"}, ...}
        [{"id": "...", "target": "...", "old": "..."}, ...]
      "old" is OPTIONAL but strongly recommended as a DRIFT GUARD: apply
      re-reads the file, so an edit list written against a stale extract would
      otherwise land on whatever the segment holds now. When "old" is present
      the live rendered target must equal it, or the edit is skipped.
      Rules enforced:
        * refuses to write over IN — compared by real path, so a symlink or a
          differently spelled path to the same file is caught too
        * TAGGED segments are rewritten when the edit carries the SOURCE's
          inline tokens — same multiset as the source, {gN}…{/gN} pairs
          properly nested. The target's inline elements are then rebuilt by
          cloning the source's <g>/<x>/<ph>/… elements (same ids, same
          attributes) around the new text, which is exactly what Studio does
          when a linguist inserts source tags. Any other tagged edit is
          refused: a token set that differs from the source's, a token the
          source doesn't have, broken nesting, or a target holding structure
          beyond inline tags and bookmarks (a comment mrk, say) — those still
          need the CAT tool. The source is the authority, NOT the current
          target: a draft that lost its tags or carries a linguist's extra
          QuickInsert formatting is repaired to the source tag set.
        * a plain-text edit on a segment whose target currently carries tokens
          is refused (it would silently drop the tags); a plain-text edit on a
          tag-free target whose SOURCE carries tokens is applied with a warning
          (Studio QA will flag the missing tags — decide, don't stumble)
        * refuses locked segments
        * preserves UTF-8 BOM, sdl:seg-defs, x-sdl-location bookmarks (on a
          tagged rebuild they are kept but moved to the start of the segment —
          reported as a warning), and — when the input has one — its XML
          declaration verbatim (a declaration-less input gains lxml's default
          declaration)
        * round-trip check: the output is re-parsed and every applied segment
          must render back exactly as the edit — a mismatch aborts
      Prints a JSON report to stdout:
        {applied, applied_ids, applied_tagged_ids, skipped, hard_skips,
         warnings, output}
      Every skip carries "hard": refusing a tagged edit that doesn't meet the
      contract is documented behaviour, not a failure, so it is soft. Exit code
      is 0 when hard_skips is 0 (even with soft skips) and 2 otherwise — a
      caller must be able to tell "by-design refusal" from "your edit did not
      land".

Traps this script exists to absorb — do not regress on these:
  * Segment text lives in <seg-source>/<target> under <mrk mtype="seg">, NOT in
    <source>. One trans-unit may hold many seg mrks.
  * A target mrk may contain empty <mrk mtype="x-sdl-location"/> bookmarks; the
    visible text can sit in mrk.text OR in a bookmark's .tail. Naive
    mrk.text = new silently drops or duplicates text.
  * The file begins with a UTF-8 BOM; Studio expects it back.
  * Trans-unit count != segment count; numeric-only source cells may be absent
    from the file entirely (raise those from a source diff, not from here).
"""
import argparse, copy, json, os, re, sys, io
from collections import Counter
from lxml import etree

X = '{urn:oasis:names:tc:xliff:document:1.2}'
SDL = '{http://sdl.com/FileTypes/SdlXliff/1.0}'
PLACEHOLDER_TAGS = {'bpt', 'ept', 'ph', 'it', 'x', 'g'}
# Tokens _render emits, and the ONLY things apply turns back into elements.
# Grammar: {g5}…{/g5} is a pair (wraps content); {x7} {ph3} {bpt1} {ept1} {it2}
# are standalone. Text that looks like a token but matches no source element
# cannot round-trip and is refused (see _rebuild_tagged).
TOKEN_LIKE = re.compile(r'\{(/?)(%s)(\d*)\}' % '|'.join(sorted(PLACEHOLDER_TAGS)))
# Control characters XML 1.0 cannot store at all (tab/LF/CR are fine).
_XML_BAD = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def die(msg):
    sys.exit('sdlxliff_io: ' + msg)


def _parse(path):
    try:
        return etree.parse(path)
    except OSError as e:
        die('cannot read %s: %s' % (path, e.strerror or e))
    except etree.XMLSyntaxError as e:
        die('%s is not well-formed XML: %s' % (path, e))


def _render(el, tokens):
    """Flatten an element to text, replacing inline tags with {tok} tokens."""
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
            if tag == 'mrk' and child.get('mtype') == 'x-sdl-location':
                pass  # invisible bookmark
            elif tag == 'mrk':
                if child.text:
                    parts.append(child.text)
                walk(child)
            elif tag == 'g':
                # `or ''` — an id-less <g> must not become the literal token
                # "{gNone}" (a Python artifact TOKEN_LIKE cannot even match)
                gid = child.get('id') or ''
                tok_o, tok_c = '{g%s}' % gid, '{/g%s}' % gid
                tokens.extend([tok_o, tok_c])
                parts.append(tok_o)
                if child.text:
                    parts.append(child.text)
                walk(child)
                parts.append(tok_c)
            elif tag in PLACEHOLDER_TAGS:
                tok = '{%s%s}' % (tag, child.get('id') or '')
                tokens.append(tok)
                parts.append(tok)
            else:
                if child.text:
                    parts.append(child.text)
                walk(child)
            if child.tail:
                parts.append(child.tail)

    if el.text:
        parts.append(el.text)
    walk(el)
    return ''.join(parts)


def _is_bookmark(el):
    return (isinstance(el.tag, str) and etree.QName(el).localname == 'mrk'
            and el.get('mtype') == 'x-sdl-location' and len(el) == 0)


def _inline_index(el, index=None):
    """token -> the SOURCE element it stands for, e.g. '{g5}' -> <g id="5">,
    '{x7}' -> <x id="7"/>. Walks exactly the structure _render tokenises, so
    the two never disagree about what a token means. Repeated ids map to the
    first occurrence — same id, same tag-def, same element."""
    if index is None:
        index = {}
    for child in el:
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child).localname
        if tag == 'mrk':
            _inline_index(child, index)
        elif tag == 'g':
            gid = child.get('id') or ''
            index.setdefault('{g%s}' % gid, child)
            _inline_index(child, index)
        elif tag in PLACEHOLDER_TAGS:
            index.setdefault('{%s%s}' % (tag, child.get('id') or ''), child)
        else:
            _inline_index(child, index)
    return index


def token_strings(text):
    """Every inline token in `text`, in order, as the literal strings _render
    emits ('{g5}', '{/g5}', '{x7}')."""
    return [m.group(0) for m in TOKEN_LIKE.finditer(text)]


def _rebuild_tagged(tmrk, new_text, index, literal=frozenset()):
    """Rewrite a target seg-mrk from token-bearing text. Returns None on
    success, else a reason string (nothing is mutated on failure).

    Contract: every token must name a source element (`index`), {gN} pairs must
    nest properly, and the target may hold nothing but inline tags, bookmarks,
    comments/PIs and text — a comment mrk or other wrapper is structure this
    function cannot reproduce, so it refuses. Bookmarks survive but move to the
    front of the segment (their position inside the old text is meaningless
    once the text is replaced); the caller reports that as a warning.
    """
    # 1. validate the token stream before touching anything
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
    # 2. validate the target's current structure
    bookmarks = []
    for child in tmrk.iter():          # ALL depths: a comment mrk nested inside
        if child is tmrk or not isinstance(child.tag, str):
            continue                   # a <g> would otherwise be flattened silently
        if _is_bookmark(child):
            if child.getparent() is tmrk:
                bookmarks.append(child)
            else:
                return 'a bookmark sits inside an inline tag; cannot rebuild safely'
        elif etree.QName(child).localname not in PLACEHOLDER_TAGS:
            return ('target holds inline structure beyond tags and bookmarks '
                    '(<%s mtype=%r>) that cannot be rebuilt safely'
                    % (etree.QName(child).localname, child.get('mtype')))
    # 3. rebuild
    keep = [c for c in tmrk if not isinstance(c.tag, str)]  # comments / PIs
    for c in list(tmrk):
        tmrk.remove(c)
    tmrk.text = None
    for c in bookmarks + keep:
        c.text = None if _is_bookmark(c) else c.text
        c.tail = None
        tmrk.append(c)

    def put_text(container, text):
        if not text:
            return
        if len(container):
            last = container[-1]
            last.tail = (last.tail or '') + text
        else:
            container.text = (container.text or '') + text

    stack = [tmrk]
    pos = 0
    for m in TOKEN_LIKE.finditer(new_text):
        if m.group(0) in literal:
            continue                   # plain text, consumed with the next slice
        put_text(stack[-1], new_text[pos:m.start()])
        pos = m.end()
        closing, name, num = m.group(1), m.group(2), m.group(3)
        tok = m.group(0)
        if closing:
            stack.pop()
            continue
        src_el = index[tok]
        if name == 'g':
            new_el = etree.SubElement(stack[-1], src_el.tag, dict(src_el.attrib))
            stack.append(new_el)
        else:
            new_el = copy.deepcopy(src_el)
            new_el.tail = None
            stack[-1].append(new_el)
    put_text(stack[-1], new_text[pos:])
    return None


def _tm_class(origin, percent):
    if origin == 'auto-propagated' or (percent and percent.isdigit() and int(percent) >= 100):
        return 'reuse'
    if percent:
        return 'fuzzy'
    return 'new'


def _iter_segments(tree):
    """Yield dicts per segment, in document order."""
    n = 0
    for tu in tree.iter(X + 'trans-unit'):
        ss = tu.find(X + 'seg-source')
        tg = tu.find(X + 'target')
        defs = {}
        sd = tu.find(SDL + 'seg-defs')
        if sd is not None:
            for s in sd.findall(SDL + 'seg'):
                defs[s.get('id')] = s
        if ss is None:
            continue  # unsegmented/structure-only unit
        tmrks = {}
        if tg is not None:
            for m in tg.iter(X + 'mrk'):
                if m.get('mtype') == 'seg':
                    tmrks[m.get('mid')] = m
        for m in ss.iter(X + 'mrk'):
            if m.get('mtype') != 'seg':
                continue
            n += 1
            mid = m.get('mid')
            stoks, ttoks = [], []
            d = defs.get(mid)
            conf = d.get('conf') if d is not None else None
            origin = d.get('origin') if d is not None else None
            origin_system = d.get('origin-system') if d is not None else None
            pct = d.get('percent') if d is not None else None
            locked = (d.get('locked') == 'true') if d is not None else False
            # Studio keeps the segment's history as nested <sdl:prev-origin>
            # elements: origin="interactive" over prev-origin origin="mt" is
            # post-edited MT, not hand translation. Outermost first.
            prev = []
            if d is not None:
                for po in d.iter(SDL + 'prev-origin'):
                    prev.append({'origin': po.get('origin'),
                                 'origin_system': po.get('origin-system'),
                                 'percent': po.get('percent')})
            tmrk = tmrks.get(mid)
            yield {
                'id': str(n), 'tu': tu.get('id'), 'mid': mid,
                'source': _render(m, stoks),
                'target': _render(tmrk, ttoks) if tmrk is not None else '',
                'source_tokens': stoks, 'target_tokens': ttoks,
                'conf': conf, 'origin': origin, 'origin_system': origin_system,
                'prev_origin': prev, 'percent': pct,
                'locked': locked,
                'tm_class': _tm_class(origin, pct),
                '_tmrk': tmrk, '_smrk': m,
            }


def cmd_extract(args):
    tree = _parse(args.infile)
    out = []
    for s in _iter_segments(tree):
        s.pop('_tmrk'); s.pop('_smrk')
        out.append(s)
    data = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(data)
        print(json.dumps({'segments': len(out), 'written': args.output}))
    else:
        print(data)


def _set_plain_text(tmrk, old_text, new_text):
    """Replace the visible text of a target seg-mrk that has NO placeholder
    tokens, handling x-sdl-location bookmarks. Returns True on success."""
    holders = []  # (kind, node) where text lives
    if tmrk.text:
        holders.append(('text', tmrk))
    for child in tmrk:
        if not isinstance(child.tag, str):
            # comment / PI: contributes no text, but its .tail is a text holder
            # exactly like a bookmark's
            if child.tail:
                holders.append(('tail', child))
            continue
        tag = etree.QName(child).localname
        if not (tag == 'mrk' and child.get('mtype') == 'x-sdl-location' and len(child) == 0):
            return False  # real inline structure — caller must refuse
        if child.text:
            holders.append(('text', child))
        if child.tail:
            holders.append(('tail', child))
    current = ''.join((n.text if k == 'text' else n.tail) or '' for k, n in holders)
    if current != old_text:
        return False
    if len(holders) == 1:
        k, node = holders[0]
        if k == 'text':
            node.text = new_text
        else:
            node.tail = new_text
        return True
    if not holders:
        if old_text == '':
            tmrk.text = new_text
            return True
        return False
    # multiple holders: put everything in the first, blank the rest
    k, node = holders[0]
    if k == 'text':
        node.text = new_text
    else:
        node.tail = new_text
    for k, node in holders[1:]:
        if k == 'text':
            node.text = ''
        else:
            node.tail = ''
    return True


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
        die('%s must hold a JSON object or array of edits, '
            'found a %s at the top level' % (path, type(raw).__name__))
    return edits


def cmd_apply(args):
    # Real paths: a symlink or a differently spelled path to the input is still
    # the input, and clobbering it destroys the only copy of the source state.
    if os.path.realpath(args.output) == os.path.realpath(args.infile):
        sys.exit('refusing to overwrite the input file — choose a different -o')
    try:
        raw = open(args.infile, 'rb').read()
    except OSError as e:
        die('cannot read %s: %s' % (args.infile, e.strerror or e))
    had_bom = raw.startswith(b'\xef\xbb\xbf')
    tree = _parse(args.infile)

    edits = _parse_edits(args.edits)

    applied, applied_tagged, skipped, warnings = [], [], [], []

    def skip(sid, reason, hard=True):
        skipped.append({'id': sid, 'reason': reason, 'hard': hard})

    seen = set()
    for s in _iter_segments(tree):
        sid = s['id']
        if sid not in edits:
            continue
        seen.add(sid)
        new, old = edits[sid]
        if s['locked']:
            skip(sid, 'segment is locked')
            continue
        if s['_tmrk'] is None:
            skip(sid, 'no target mrk for this segment')
            continue
        if old is not None and old != s['target']:
            skip(sid, 'live target does not match provided old')
            continue
        # Token-looking strings that are plain text in the source ("{x}" as a
        # UI placeholder, no element behind it) stay plain text in the edit.
        # If the same string is BOTH an element and literal text in one
        # segment, the edit is ambiguous — refuse rather than guess.
        literal = Counter(token_strings(s['source'])) - Counter(s['source_tokens'])
        if literal and set(literal) & set(s['source_tokens']):
            skip(sid, 'source carries %s both as inline element(s) and as literal '
                      'text — an edit cannot say which is which; edit in the CAT '
                      'tool' % sorted(literal), hard=False)
            continue
        literal = frozenset(literal)
        new_tokens = [t for t in token_strings(new) if t not in literal]
        if new_tokens:
            # Tagged edit: the SOURCE tag set is the contract. Compare as
            # multisets — order is the edit's business, nesting is validated
            # by the rebuild.
            if sorted(new_tokens) != sorted(s['source_tokens']):
                skip(sid, 'edit tokens %s differ from the source tag set %s — '
                          'a target may only carry exactly the source\'s inline '
                          'tags; anything else needs the CAT tool'
                          % (new_tokens, s['source_tokens']), hard=False)
                continue
            had_bookmarks = any(_is_bookmark(c) for c in s['_tmrk'])
            err = _rebuild_tagged(s['_tmrk'], new, _inline_index(s['_smrk']), literal)
            if err:
                skip(sid, 'tagged edit refused: %s — edit in the CAT tool' % err,
                     hard=False)
                continue
            applied.append(sid)
            applied_tagged.append(sid)
            if had_bookmarks:
                warnings.append({'id': sid, 'warning':
                                 'x-sdl-location bookmark(s) kept but moved to the '
                                 'start of the segment during the tagged rebuild'})
            continue
        if s['target_tokens']:
            skip(sid, 'edit carries no inline tokens but the live target holds %s '
                      '— applying it would silently drop the tags; put the tokens '
                      'back into the edit' % s['target_tokens'], hard=False)
            continue
        if _set_plain_text(s['_tmrk'], s['target'], new):
            applied.append(sid)
            if s['source_tokens']:
                warnings.append({'id': sid, 'warning':
                                 'source carries inline tags %s but the new target '
                                 'has none — Studio QA will flag missing tags; '
                                 'confirm this is intended' % s['source_tokens']})
        else:
            skip(sid, 'unexpected inline structure in the target segment — it is '
                      'not plain text plus x-sdl-location bookmarks, so it cannot '
                      'be rewritten safely')
    unknown = sorted(set(edits) - seen, key=lambda x: int(x) if x.isdigit() else 0)
    for u in unknown:
        skip(u, 'id not found in file')

    buf = io.BytesIO()
    tree.write(buf, encoding='utf-8', xml_declaration=True)
    data = buf.getvalue()
    # Reuse the INPUT's XML declaration verbatim (quote style, any standalone
    # attribute): lxml re-serializes the declaration in its own style, and
    # string-replacing one assumed style for another is dead code the moment
    # the lxml build or the input differs. Splicing needs no assumption about
    # either side. (Same policy as the sibling MXLIFF script.)
    src_head = raw[3:] if had_bom else raw
    m_in = re.match(rb'<\?xml[^>]*\?>', src_head)
    if m_in and data.startswith(b'<?xml'):
        data = m_in.group(0) + data[data.index(b'?>') + 2:]
    if had_bom and not data.startswith(b'\xef\xbb\xbf'):
        data = b'\xef\xbb\xbf' + data
    with open(args.output, 'wb') as f:
        f.write(data)
    # round-trip check: re-parse and confirm every APPLIED segment renders back
    # exactly as the edit — for a tagged rebuild this is the proof that the
    # cloned elements tokenise to the same string that went in. Scope honesty:
    # unapplied segments are not re-compared; their preservation is the job of
    # the tree-based editing above (only seg-target mrks are ever touched).
    check = _parse(args.output)
    drift = []
    want = set(applied)
    for s in _iter_segments(check):
        if s['id'] in want and s['target'] != edits[s['id']][0]:
            drift.append(s['id'])
    if drift:
        die('round-trip check failed for id(s) %s — output not trustworthy'
            % ', '.join(drift))
    hard = sum(1 for k in skipped if k['hard'])
    print(json.dumps({'applied': len(applied), 'applied_ids': applied,
                      'applied_tagged_ids': applied_tagged,
                      'skipped': skipped, 'hard_skips': hard,
                      'warnings': warnings, 'output': args.output},
                     ensure_ascii=False, indent=1))
    if hard:
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('extract', help='SDLXLIFF -> bilingual JSON')
    e.add_argument('infile')
    e.add_argument('-o', '--output')
    e.set_defaults(func=cmd_extract)
    a = sub.add_parser('apply', help='write edited targets into a copy')
    a.add_argument('infile')
    a.add_argument('edits', help='JSON: {"id": "new target", ...} or [{id, target}]')
    a.add_argument('-o', '--output', required=True)
    a.set_defaults(func=cmd_apply)
    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
