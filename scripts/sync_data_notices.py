"""Synchronize the code-owned offline notice module; --check never writes."""

import argparse
from pathlib import Path

from sugarglider.offline_regions.source_notices import render_browser_registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = (
        Path(__file__).resolve().parents[1]
        / "src/sugarglider/web/static/data_notice_registry.js"
    )
    expected = render_browser_registry()
    if args.check:
        if path.read_text(encoding="utf-8") != expected:
            raise SystemExit("Offline data notice registry is not synchronized")
    else:
        path.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
