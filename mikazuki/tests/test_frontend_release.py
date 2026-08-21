import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mikazuki.frontend_release import (
    ArtifactLocation,
    FrontendDownloadError,
    FrontendReleaseError,
    FrontendReleaseConfigError,
    GithubReleaseProvider,
    JihulabGenericProvider,
    StaticFrontendProvider,
    ensure_frontend_release,
    load_download_config,
    load_frontend_build_info,
    load_release_info,
    providers_for_config,
    release_version_payload,
)
from mikazuki.scripts.package_frontend_release import package_frontend


class _FixedProvider:
    name = "test"

    def __init__(self, archive: Path, checksum: Path) -> None:
        self.archive = archive
        self.checksum = checksum

    def locate(self, _release):
        return ArtifactLocation(
            source=self.name,
            archive_url=self.archive.as_uri(),
            checksum_url=self.checksum.as_uri(),
        )


class FrontendReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        (self.root / "frontend").mkdir()
        (self.root / "frontend" / "package.json").write_text(
            json.dumps({"version": "2.1.0"}), encoding="utf-8"
        )
        self.write_version()

    def write_version(
        self,
        *,
        version: str = "2.1.0",
        channel: str = "stable",
        auto_download: bool = True,
    ) -> None:
        payload = {
            "schemaVersion": 1,
            "version": version,
            "channel": channel,
            "tag": f"v{version}",
            "frontend": {
                "version": version,
                "asset": "frontend-dist.zip",
                "checksumAsset": "frontend-dist.zip.sha256",
                "autoDownload": auto_download,
            },
        }
        (self.root / "version.json").write_text(json.dumps(payload), encoding="utf-8")

    def write_dist(self, version: str, *, marker: str = "current") -> Path:
        dist = self.root / "frontend" / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text(marker, encoding="utf-8")
        (dist / "build-info.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "appVersion": version,
                    "frontendVersion": version,
                    "commit": f"commit-{version}",
                    "builtAt": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        return dist

    def make_artifact(
        self,
        *,
        version: str = "2.1.0",
        entries: dict[str, str] | None = None,
        valid_checksum: bool = True,
    ) -> tuple[Path, Path]:
        artifact_dir = self.root / "artifacts"
        artifact_dir.mkdir(exist_ok=True)
        archive = artifact_dir / "frontend-dist.zip"
        default_entries = {
            "index.html": "new frontend",
            "assets/app.js": "console.log('ok')",
            "build-info.json": json.dumps(
                {
                    "schemaVersion": 1,
                    "appVersion": version,
                    "frontendVersion": version,
                    "commit": "release-commit",
                    "builtAt": "2026-01-02T00:00:00Z",
                }
            ),
        }
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, content in (entries or default_entries).items():
                bundle.writestr(name, content)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if not valid_checksum:
            digest = "0" * 64
        checksum = artifact_dir / "frontend-dist.zip.sha256"
        checksum.write_text(f"{digest}  frontend-dist.zip\n", encoding="utf-8")
        return archive, checksum

    def test_loads_complete_release_and_installed_version_information(self) -> None:
        self.write_dist("2.1.0")

        release = load_release_info(self.root / "version.json")
        build = load_frontend_build_info(self.root / "frontend" / "dist")
        payload = release_version_payload(self.root)

        self.assertEqual(release.version, "2.1.0")
        self.assertEqual(release.frontend.version, "2.1.0")
        self.assertEqual(build.frontend_version, "2.1.0")
        self.assertEqual(payload["frontend"]["installedVersion"], "2.1.0")
        self.assertEqual(payload["frontend"]["buildCommit"], "commit-2.1.0")

    def test_rejects_unsafe_release_metadata(self) -> None:
        payload = json.loads((self.root / "version.json").read_text(encoding="utf-8"))
        payload["frontend"]["asset"] = "../frontend.zip"
        (self.root / "version.json").write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(FrontendReleaseConfigError):
            load_release_info(self.root / "version.json")

    def test_provider_urls_pin_the_required_frontend_version(self) -> None:
        release = load_release_info(self.root / "version.json")

        github = GithubReleaseProvider("Akegarasu/lora-scripts").locate(release)
        jihulab = JihulabGenericProvider(
            "Akegarasu/lora-scripts", "lora-scripts-frontend"
        ).locate(release)
        static = StaticFrontendProvider("https://downloads.example.com/frontend").locate(release)

        self.assertEqual(
            github.archive_url,
            "https://github.com/Akegarasu/lora-scripts/releases/download/v2.1.0/frontend-dist.zip",
        )
        self.assertEqual(
            jihulab.archive_url,
            "https://jihulab.com/api/v4/projects/Akegarasu%2Flora-scripts/packages/generic/"
            "lora-scripts-frontend/2.1.0/frontend-dist.zip",
        )
        self.assertEqual(
            static.archive_url,
            "https://downloads.example.com/frontend/2.1.0/frontend-dist.zip",
        )

    def test_download_config_precedence_and_cn_alias(self) -> None:
        config_dir = self.root / "config"
        config_dir.mkdir()
        (config_dir / "frontend-download.json").write_text(
            json.dumps(
                {
                    "source": "static",
                    "staticBaseUrl": "https://file.example.com/frontend",
                    "autoOrder": ["cn", "github"],
                }
            ),
            encoding="utf-8",
        )

        config = load_download_config(
            self.root,
            source="cn",
            environ={"MIKAZUKI_FRONTEND_JIHULAB_PROJECT": "12345"},
        )

        self.assertEqual(config.source, "jihulab")
        self.assertEqual(config.jihulab_project, "12345")
        self.assertEqual(config.static_base_url, "https://file.example.com/frontend")
        self.assertEqual(config.auto_order, ("jihulab", "github"))
        self.assertEqual(providers_for_config(config)[0].name, "jihulab")

    def test_static_source_requires_a_base_url(self) -> None:
        config = load_download_config(self.root, source="static", environ={})

        with self.assertRaises(FrontendReleaseConfigError):
            providers_for_config(config)

    def test_matching_frontend_does_not_download(self) -> None:
        self.write_dist("2.1.0")

        result = ensure_frontend_release(self.root)

        self.assertEqual(result.status, "current")

    def test_downloads_verifies_and_atomically_replaces_frontend(self) -> None:
        self.write_dist("2.0.0", marker="old frontend")
        archive, checksum = self.make_artifact()

        result = ensure_frontend_release(
            self.root,
            providers=[_FixedProvider(archive, checksum)],
        )

        self.assertEqual(result.status, "installed")
        self.assertEqual(result.source, "test")
        dist = self.root / "frontend" / "dist"
        self.assertEqual((dist / "index.html").read_text(encoding="utf-8"), "new frontend")
        self.assertTrue((dist / "assets" / "app.js").is_file())
        self.assertEqual(load_frontend_build_info(dist).frontend_version, "2.1.0")
        self.assertEqual(load_frontend_build_info(dist).source, "test")
        self.assertEqual(release_version_payload(self.root)["frontend"]["source"], "test")
        self.assertFalse(any((self.root / "frontend").glob(".dist-backup-*")))

    def test_auto_source_falls_back_to_the_next_provider(self) -> None:
        self.write_dist("2.0.0", marker="old frontend")
        bad_archive, bad_checksum = self.make_artifact(valid_checksum=False)
        good_dir = self.root / "good-artifacts"
        good_dir.mkdir()
        good_archive = good_dir / "frontend-dist.zip"
        good_checksum = good_dir / "frontend-dist.zip.sha256"
        good_archive.write_bytes(bad_archive.read_bytes())
        digest = hashlib.sha256(good_archive.read_bytes()).hexdigest()
        good_checksum.write_text(f"{digest}  frontend-dist.zip\n", encoding="utf-8")

        first = _FixedProvider(bad_archive, bad_checksum)
        first.name = "first"
        second = _FixedProvider(good_archive, good_checksum)
        second.name = "second"
        result = ensure_frontend_release(self.root, providers=[first, second])

        self.assertEqual(result.source, "second")
        self.assertEqual(
            (self.root / "frontend" / "dist" / "index.html").read_text(encoding="utf-8"),
            "new frontend",
        )

    def test_checksum_failure_preserves_previous_frontend(self) -> None:
        dist = self.write_dist("2.0.0", marker="old frontend")
        archive, checksum = self.make_artifact(valid_checksum=False)

        with self.assertRaises(FrontendDownloadError):
            ensure_frontend_release(
                self.root,
                providers=[_FixedProvider(archive, checksum)],
            )

        self.assertEqual((dist / "index.html").read_text(encoding="utf-8"), "old frontend")
        self.assertEqual(load_frontend_build_info(dist).frontend_version, "2.0.0")

    def test_unsafe_zip_path_is_rejected_without_touching_previous_frontend(self) -> None:
        dist = self.write_dist("2.0.0", marker="old frontend")
        entries = {
            "index.html": "new frontend",
            "../escaped.txt": "unsafe",
            "build-info.json": json.dumps(
                {
                    "schemaVersion": 1,
                    "appVersion": "2.1.0",
                    "frontendVersion": "2.1.0",
                }
            ),
        }
        archive, checksum = self.make_artifact(entries=entries)

        with self.assertRaises(FrontendDownloadError) as raised:
            ensure_frontend_release(
                self.root,
                providers=[_FixedProvider(archive, checksum)],
            )

        self.assertIn("不安全路径", str(raised.exception))
        self.assertFalse((self.root / "frontend" / "escaped.txt").exists())
        self.assertEqual((dist / "index.html").read_text(encoding="utf-8"), "old frontend")

    def test_development_channel_can_skip_download(self) -> None:
        self.write_version(version="2.2.0-dev", channel="development", auto_download=False)

        result = ensure_frontend_release(self.root)

        self.assertEqual(result.status, "missing")

    def test_packages_built_frontend_with_checksum(self) -> None:
        self.write_dist("2.1.0")
        output = self.root / "release"

        archive, checksum = package_frontend(
            self.root,
            output,
            expected_tag="v2.1.0",
        )

        self.assertTrue(archive.is_file())
        self.assertTrue(checksum.is_file())
        expected = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertTrue(checksum.read_text(encoding="utf-8").startswith(expected))
        with zipfile.ZipFile(archive) as bundle:
            self.assertIn("index.html", bundle.namelist())
            self.assertIn("build-info.json", bundle.namelist())

    def test_stable_package_requires_auto_download(self) -> None:
        self.write_version(auto_download=False)
        self.write_dist("2.1.0")

        with self.assertRaises(FrontendReleaseError):
            package_frontend(self.root, self.root / "release", expected_tag="v2.1.0")


if __name__ == "__main__":
    unittest.main()
