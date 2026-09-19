#!/usr/bin/env python3
"""Validate every mermaid diagram in markdown files, or .mmd files, with mermaid-cli.

    check_mermaid.py [PATH ...]    # files or directories; default: .

Each ```mermaid (or ~~~mermaid) fence is rendered with `mmdc`, the reference
mermaid.js parser. Failures print as `file:line: error` and the exit status is
1. A fence preceded by the line `<!-- mermaid: expected to fail -->` must
FAIL to render (a deliberate broken sample); if it renders, that is reported.

mmdc drives a headless browser through puppeteer. If puppeteer's own
chrome-headless-shell is not installed, the script points it at a system
Chromium/Chrome (CHROME env var, else the first found on PATH).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_FAILURE = "<!-- mermaid: expected to fail -->"
SKIP_DIRS = {".git", "node_modules", "target", ".venv", "dist", "build"}
FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[ \t]*mermaid\b[^\n]*\n(.*?)^\1\2[ \t]*$", re.S | re.M)


def sources(paths):
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix in (".md", ".mmd") and not SKIP_DIRS & set(f.parts):
                    yield f
        elif p.exists():
            yield p


def diagrams(path):
    """(line, source, expected_failure) for each diagram in `path`."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".mmd":
        yield 1, text, False
        return
    lines = text.splitlines()
    for m in FENCE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        before = lines[line - 2].strip() if line >= 2 else ""
        yield line, m.group(3), before == EXPECTED_FAILURE


def puppeteer_config(tmp):
    chrome = os.environ.get("CHROME") or next(
        (shutil.which(c) for c in ("chromium", "chromium-browser", "google-chrome", "chrome") if shutil.which(c)),
        None,
    )
    if not chrome:
        return None
    cfg = Path(tmp) / "puppeteer.json"
    cfg.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox"]}))
    return cfg


def render(source, tmp, cfg):
    """None when mmdc renders `source`, else its error message."""
    src, out = Path(tmp) / "d.mmd", Path(tmp) / "d.svg"
    src.write_text(source, encoding="utf-8")
    cmd = ["mmdc", "-q", "-i", str(src), "-o", str(out)] + (["-p", str(cfg)] if cfg else [])
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if run.returncode == 0:
        return None
    lines = [l for l in (run.stderr + run.stdout).splitlines() if l.strip() and not l.lstrip().startswith("at ")]
    return " ".join(lines[:3]) or f"mmdc exited {run.returncode}"


def main():
    if not shutil.which("mmdc"):
        sys.exit("mmdc not found: install @mermaid-js/mermaid-cli")
    failed = checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        cfg = puppeteer_config(tmp)
        # A broken browser setup makes every diagram "fail": prove the tool first.
        if render("flowchart LR\n  a --> b\n", tmp, cfg):
            sys.exit("mmdc cannot render a trivial diagram; fix the browser setup:\n"
                     + render("flowchart LR\n  a --> b\n", tmp, cfg))
        for path in sources(sys.argv[1:] or ["."]):
            for line, source, expect_fail in diagrams(path):
                checked += 1
                error = render(source, tmp, cfg)
                if expect_fail and error is None:
                    print(f"{path}:{line}: marked '{EXPECTED_FAILURE}' but renders")
                    failed += 1
                elif error and not expect_fail:
                    print(f"{path}:{line}: {error}")
                    failed += 1
    print(f"{checked} diagram(s) checked, {failed} problem(s)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
