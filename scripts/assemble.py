"""Отдельный скрипт сборки: python scripts/assemble.py sheet.json out.mp4"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.assembler.assemble import assemble_from_sheet  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: python scripts/assemble.py <sheet.json> <out.mp4>")
        sys.exit(2)
    sheet = Path(sys.argv[1])
    out = Path(sys.argv[2])
    work = out.parent / "_work"
    assemble_from_sheet(sheet, work, out)
    print(out)


if __name__ == "__main__":
    main()
