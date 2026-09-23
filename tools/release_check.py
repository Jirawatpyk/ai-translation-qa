#!/usr/bin/env python3
"""Pre-release gate for the ai-translation-qa plugin. Run from the repo root:

    python3 tools/release_check.py

Fails (exit 1) on anything that must not ship:
  * version mismatch between plugin.json and the marketplace entry, or no
    CHANGELOG entry for that version — users only receive an update when the
    version changes, so a forgotten bump means nobody gets the release
  * SKILL.md frontmatter missing `name`/`description`, or a description over
    the 1024-character limit (the upload validator rejects it)
  * __pycache__ / *.pyc, or any client-data file type, inside the plugin
  * any term from .trace-denylist found anywhere in the repo (client names, vendor
    names, job numbers — the list itself is gitignored so it never goes public)
  * a failing synthetic test in tests/
"""
import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "ai-translation-qa"
SKILL = PLUGIN / "skills" / "ai-translation-qa"
DATA_EXT = {".jsonl", ".tmx", ".sdlxliff", ".mxliff", ".mqxliff", ".xlf", ".xliff",
            ".docx", ".xlsx", ".pptx", ".pdf", ".csv"}
problems = []


def fail(msg):
    problems.append(msg)
    print("FAIL  " + msg)


def ok(msg):
    print("ok    " + msg)


# 1. versions
market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
entry = next((p for p in market["plugins"] if p["name"] == plugin["name"]), None)
if entry is None:
    fail("marketplace.json has no entry named %r" % plugin["name"])
elif entry.get("version") != plugin.get("version"):
    fail("version mismatch: plugin.json %s vs marketplace.json %s"
         % (plugin.get("version"), entry.get("version")))
else:
    ok("version %s in both manifests" % plugin["version"])
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
if not re.search(r"^## \[?%s\]?" % re.escape(plugin.get("version", "?")), changelog, re.M):
    fail("CHANGELOG.md has no '## %s' entry" % plugin.get("version"))
else:
    ok("CHANGELOG entry present")

# 2. SKILL.md frontmatter
text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
m = re.match(r"---\n(.*?)\n---\n", text, re.S)
if not m:
    fail("SKILL.md has no YAML frontmatter")
else:
    fm = m.group(1)
    if not re.search(r"^name:\s*\S", fm, re.M):
        fail("SKILL.md frontmatter has no name")
    dm = re.search(r"^description:\s*>?\s*\n?(.*)", fm, re.M | re.S)
    desc = " ".join(l.strip() for l in (dm.group(1) if dm else "").splitlines() if l.strip())
    if not desc:
        fail("SKILL.md frontmatter has no description")
    elif len(desc) > 1024:
        fail("description is %d characters (limit 1024)" % len(desc))
    else:
        ok("description %d/1024 characters" % len(desc))

# 3. junk and client-data files inside the shipped plugin
bad = [p for p in PLUGIN.rglob("*")
       if p.name == "__pycache__" or p.suffix in {".pyc"} | DATA_EXT]
if bad:
    for p in bad:
        fail("must not ship: %s" % p.relative_to(ROOT))
else:
    ok("no __pycache__ or client-data files in the plugin")

# 4. trace denylist
deny = ROOT / ".trace-denylist"
if not deny.exists():
    print("WARN  .trace-denylist not found — client/vendor-name grep skipped "
          "(create it locally, one term per line; it is gitignored)")
else:
    terms = [t.strip() for t in deny.read_text(encoding="utf-8").splitlines()
             if t.strip() and not t.startswith("#")]
    def pattern(t):
        # whole-word on the left always; on the right only when the term ends in a
        # letter — a name like "Lock" must not hit "deadlock", but a job-number
        # prefix like "JOB-12" must still hit "JOB-12345"
        right = r"(?![A-Za-z])" if t[-1:].isalpha() else ""
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + right, re.I)
    pats = [(t, pattern(t)) for t in terms]
    hits = []
    # the whole repo is public, not just the shipped plugin: README, CHANGELOG,
    # tests and fixtures are scanned too
    for p in ROOT.rglob("*"):
        if (p.is_file() and ".git" not in p.parts and p.name != ".trace-denylist"
                and p.suffix in {".md", ".py", ".json", ".sdlxliff", ".txt"}):
            body = p.read_text(encoding="utf-8", errors="replace")
            hits += ["%s: %s" % (p.relative_to(ROOT), t) for t, rx in pats if rx.search(body)]
    for h in hits:
        fail("job trace — " + h)
    if not hits:
        ok("no denylisted term in the repo (%d terms checked)" % len(terms))

# 5. synthetic tests
for t in sorted((ROOT / "tests").glob("test_*.py")):
    r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True)
    if r.returncode:
        fail("%s failed:\n%s" % (t.name, (r.stdout + r.stderr)[-1500:]))
    else:
        n = sum(1 for line in r.stdout.splitlines() if line.startswith("PASS"))
        ok("%s (%d checks)" % (t.name, n))

print("\n%s" % ("RELEASE BLOCKED — %d problem(s)" % len(problems) if problems else "ready to release"))
sys.exit(1 if problems else 0)
