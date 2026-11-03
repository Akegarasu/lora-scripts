from __future__ import annotations

import argparse
import hashlib
import os
import sys
import zipfile
from pathlib import Path

from mikazuki.frontend_release import (
    FrontendReleaseError,
    load_frontend_build_info,
    load_release_info,
    project_root,
)


def package_frontend(
    root: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    release = load_release_info(root / "version.json")

    dist = root / "frontend" / "dist"
    build = load_frontend_build_info(dist)
    if not (dist / "index.html").is_file() or build is None:
        raise FrontendReleaseError("frontend/dist 未完成构建或缺少 build-info.json")
    if build.app_version != release.version or build.frontend_version != release.frontend.version:
        raise FrontendReleaseError("frontend/dist 的构建版本与 version.json 不一致，请重新构建")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / release.frontend.asset
    temporary = output_dir / f".{release.frontend.asset}.tmp"
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as bundle:
            for path in sorted(dist.rglob("*")):
                if path.is_symlink():
                    raise FrontendReleaseError(f"前端构建目录不允许符号链接：{path}")
                if path.is_file():
                    bundle.write(path, path.relative_to(dist).as_posix())
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)

    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_path = output_dir / release.frontend.checksum_asset
    checksum_path.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    return archive, checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 Mikazuki 前端 Release 制品")
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--output", type=Path, default=Path("release"))
    args = parser.parse_args()
    try:
        archive, checksum = package_frontend(
            args.root.resolve(),
            args.output.resolve(),
        )
    except FrontendReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
