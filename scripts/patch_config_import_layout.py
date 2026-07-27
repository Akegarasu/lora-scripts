"""Compatibility entry point for the former dist patch command.

Layout changes now belong in frontend/src/layout/layout.js. This command remains so
existing release automation builds the asset instead of mutating a minified bundle.
"""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_layout import build_layout
from bump_spa_asset_cache_key import bump_dist_cache_keys


def main() -> None:
    bumped = bump_dist_cache_keys()
    print(f"bumped SPA cache key in {bumped} dist file(s)")
    build_layout()


if __name__ == "__main__":
    main()
