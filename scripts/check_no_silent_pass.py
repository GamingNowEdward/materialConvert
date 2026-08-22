"""Guard against silent logging regressions in core/ and ui/.

Usage:
    python scripts/check_no_silent_pass.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BARE_EXCEPT = re.compile(r"except\s+Exception\s*:\s*$")
_PASS = re.compile(r"^\s*pass\s*$")
_PRINT = re.compile(r"(?<![.\w])\bprint\s*\(")
_MAYA_WARNING = re.compile(r"\bcmds\.warning\s*\(")


def check_python_file(path):
    problems = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines):
        if _PRINT.search(line):
            problems.append(f"{idx + 1}: print call: {line.strip()}")
        if _MAYA_WARNING.search(line):
            problems.append(f"{idx + 1}: direct cmds.warning call: {line.strip()}")
        if _BARE_EXCEPT.search(line.strip()):
            problems.append(f"{idx + 1}: bare except Exception without as exc: {line.strip()}")
        if _PASS.match(line):
            previous = lines[idx - 1].strip() if idx > 0 else ""
            if previous.startswith("except") or previous.startswith("except Exception"):
                problems.append(f"{idx + 1}: silent pass after except")
    return problems


def main():
    failed = False
    for base in ("core", "ui"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for problem in check_python_file(path):
                failed = True
                print(f"{path.relative_to(ROOT)}:{problem}")
    if failed:
        sys.exit(1)
    print("No silent pass / print / cmds.warning markers found.")


if __name__ == "__main__":
    main()
