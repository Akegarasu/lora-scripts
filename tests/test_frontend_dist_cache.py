"""Vue 3 production build and cache contracts."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestVueFrontendDist(unittest.TestCase):
    def test_dist_is_a_vite_application(self):
        html = (ROOT / "frontend/dist/index.html").read_text(encoding="utf-8")
        self.assertIn('<div id="app"></div>', html)
        self.assertRegex(html, r'/assets/index-[A-Za-z0-9_-]+\.js')
        self.assertRegex(html, r'/assets/index-[A-Za-z0-9_-]+\.css')
        self.assertNotIn("app.547295de.js", html)

    def test_referenced_assets_exist(self):
        html = (ROOT / "frontend/dist/index.html").read_text(encoding="utf-8")
        references = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        self.assertTrue(references)
        for reference in references:
            self.assertTrue((ROOT / "frontend/dist" / reference.lstrip("/")).is_file(), reference)

    def test_server_recognizes_vite_hashes_as_immutable(self):
        source = (ROOT / "mikazuki/app/application.py").read_text(encoding="utf-8")
        self.assertIn("[A-Za-z0-9_-]{8}", source)
        self.assertIn("public, max-age=31536000, immutable", source)


if __name__ == "__main__":
    unittest.main()
