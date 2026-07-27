"""Build the vendored-compatible layout asset from its maintainable source."""
from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src" / "layout" / "layout.js"
OUTPUT = ROOT / "frontend" / "dist" / "assets" / "layout.96d49288.js"


def build_layout() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    if "./app.547295de.js" not in source:
        raise SystemExit("layout source no longer imports the compatible app runtime")
    if "export{" not in source and "export {" not in source:
        raise SystemExit("layout source no longer exports its Vue components")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, OUTPUT)
    try:
        output_label = OUTPUT.relative_to(ROOT)
    except ValueError:
        output_label = OUTPUT
    print(f"built {output_label} from {SOURCE.relative_to(ROOT)}")


if __name__ == "__main__":
    build_layout()
