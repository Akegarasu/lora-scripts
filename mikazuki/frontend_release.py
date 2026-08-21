from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Iterator, Mapping, Optional, Protocol, Sequence

from mikazuki.log import log


DEFAULT_GITHUB_REPOSITORY = "Akegarasu/lora-scripts"
DEFAULT_JIHULAB_PROJECT = "Akegarasu/lora-scripts"
DEFAULT_JIHULAB_PACKAGE = "lora-scripts-frontend"
DEFAULT_SOURCE = "github"
BUILD_INFO_FILE = "build-info.json"
DOWNLOAD_CONFIG_FILE = Path("config") / "frontend-download.json"
VERSION_TOKEN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+\-]{0,127}$")
SHA256_TOKEN = re.compile(r"^[0-9a-fA-F]{64}$")


class FrontendReleaseError(RuntimeError):
    """Raised when a matching frontend cannot be resolved or installed safely."""


class FrontendReleaseConfigError(FrontendReleaseError):
    """Raised when release metadata or download configuration is invalid."""


class FrontendDownloadError(FrontendReleaseError):
    """Raised when a frontend artifact cannot be downloaded or verified."""


class FrontendArchiveError(FrontendReleaseError):
    """Raised when a frontend archive is malformed or unsafe."""


@dataclass(frozen=True)
class FrontendSpec:
    version: str
    asset: str
    checksum_asset: str
    auto_download: bool


@dataclass(frozen=True)
class ReleaseInfo:
    schema_version: int
    version: str
    channel: str
    tag: str
    frontend: FrontendSpec


@dataclass(frozen=True)
class FrontendBuildInfo:
    schema_version: int
    app_version: str
    frontend_version: str
    commit: str = ""
    built_at: str = ""
    source: str = ""
    installed_at: str = ""


@dataclass(frozen=True)
class ArtifactLocation:
    source: str
    archive_url: str
    checksum_url: str


@dataclass(frozen=True)
class FrontendDownloadConfig:
    source: str = DEFAULT_SOURCE
    github_repository: str = DEFAULT_GITHUB_REPOSITORY
    github_base_url: str = "https://github.com"
    jihulab_project: str = DEFAULT_JIHULAB_PROJECT
    jihulab_package: str = DEFAULT_JIHULAB_PACKAGE
    jihulab_base_url: str = "https://jihulab.com"
    static_base_url: str = ""
    auto_order: tuple[str, ...] = ("github", "jihulab", "static")


@dataclass(frozen=True)
class FrontendEnsureResult:
    status: str
    required_version: str
    installed_version: str = ""
    source: str = ""


class FrontendReleaseProvider(Protocol):
    name: str

    def locate(self, release: ReleaseInfo) -> ArtifactLocation:
        ...


class GithubReleaseProvider:
    name = "github"

    def __init__(self, repository: str, *, base_url: str = "https://github.com") -> None:
        repository = repository.strip().strip("/")
        if len(repository.split("/")) != 2:
            raise FrontendReleaseConfigError("GitHub repository 必须使用 owner/repo 格式")
        self.repository = repository
        self.base_url = _http_base_url(base_url, "GitHub")

    def locate(self, release: ReleaseInfo) -> ArtifactLocation:
        repository = "/".join(urllib.parse.quote(part, safe="") for part in self.repository.split("/"))
        tag = urllib.parse.quote(release.tag, safe="")
        base = f"{self.base_url}/{repository}/releases/download/{tag}"
        return ArtifactLocation(
            source=self.name,
            archive_url=f"{base}/{urllib.parse.quote(release.frontend.asset, safe='')}",
            checksum_url=f"{base}/{urllib.parse.quote(release.frontend.checksum_asset, safe='')}",
        )


class JihulabGenericProvider:
    name = "jihulab"

    def __init__(
        self,
        project: str,
        package: str,
        *,
        base_url: str = "https://jihulab.com",
    ) -> None:
        if not project.strip():
            raise FrontendReleaseConfigError("Jihulab project 不能为空")
        if not package.strip():
            raise FrontendReleaseConfigError("Jihulab package 不能为空")
        self.project = project.strip().strip("/")
        self.package = package.strip().strip("/")
        self.base_url = _http_base_url(base_url, "Jihulab")

    def locate(self, release: ReleaseInfo) -> ArtifactLocation:
        project = urllib.parse.quote(self.project, safe="")
        package = urllib.parse.quote(self.package, safe="")
        version = urllib.parse.quote(release.frontend.version, safe="")
        base = f"{self.base_url}/api/v4/projects/{project}/packages/generic/{package}/{version}"
        return ArtifactLocation(
            source=self.name,
            archive_url=f"{base}/{urllib.parse.quote(release.frontend.asset, safe='')}",
            checksum_url=f"{base}/{urllib.parse.quote(release.frontend.checksum_asset, safe='')}",
        )


class StaticFrontendProvider:
    name = "static"

    def __init__(self, base_url: str) -> None:
        self.base_url = _http_base_url(base_url, "静态下载源")

    def locate(self, release: ReleaseInfo) -> ArtifactLocation:
        version = urllib.parse.quote(release.frontend.version, safe="")
        base = f"{self.base_url}/{version}"
        return ArtifactLocation(
            source=self.name,
            archive_url=f"{base}/{urllib.parse.quote(release.frontend.asset, safe='')}",
            checksum_url=f"{base}/{urllib.parse.quote(release.frontend.checksum_asset, safe='')}",
        )


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_release_info(path: Optional[Path] = None) -> ReleaseInfo:
    metadata_path = Path(path) if path is not None else project_root() / "version.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FrontendReleaseConfigError(f"无法读取版本信息 {metadata_path}: {error}") from error
    if not isinstance(payload, dict):
        raise FrontendReleaseConfigError("version.json 顶层必须是对象")

    schema_version = payload.get("schemaVersion")
    version = payload.get("version")
    channel = payload.get("channel")
    tag = payload.get("tag")
    frontend = payload.get("frontend")
    if schema_version != 1:
        raise FrontendReleaseConfigError(f"不支持的版本信息格式：{schema_version!r}")
    _validate_token(version, "应用版本")
    _validate_token(tag, "Git tag")
    if channel not in {"development", "prerelease", "stable"}:
        raise FrontendReleaseConfigError("channel 必须是 development、prerelease 或 stable")
    if not isinstance(frontend, dict):
        raise FrontendReleaseConfigError("frontend 版本信息缺失")

    frontend_version = frontend.get("version")
    asset = frontend.get("asset")
    checksum_asset = frontend.get("checksumAsset")
    auto_download = frontend.get("autoDownload")
    _validate_token(frontend_version, "前端版本")
    _validate_asset_name(asset, "前端压缩包")
    _validate_asset_name(checksum_asset, "前端校验文件")
    if not isinstance(auto_download, bool):
        raise FrontendReleaseConfigError("frontend.autoDownload 必须是布尔值")

    return ReleaseInfo(
        schema_version=schema_version,
        version=version,
        channel=channel,
        tag=tag,
        frontend=FrontendSpec(
            version=frontend_version,
            asset=asset,
            checksum_asset=checksum_asset,
            auto_download=auto_download,
        ),
    )


def load_frontend_build_info(frontend_dir: Path) -> Optional[FrontendBuildInfo]:
    path = Path(frontend_dir) / BUILD_INFO_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        schema_version = int(payload.get("schemaVersion"))
    except (TypeError, ValueError):
        return None
    app_version = payload.get("appVersion")
    frontend_version = payload.get("frontendVersion")
    if schema_version != 1 or not isinstance(app_version, str) or not isinstance(frontend_version, str):
        return None
    return FrontendBuildInfo(
        schema_version=schema_version,
        app_version=app_version,
        frontend_version=frontend_version,
        commit=str(payload.get("commit") or ""),
        built_at=str(payload.get("builtAt") or ""),
        source=str(payload.get("source") or ""),
        installed_at=str(payload.get("installedAt") or ""),
    )


def release_version_payload(root: Optional[Path] = None) -> dict[str, object]:
    base = Path(root) if root is not None else project_root()
    release = load_release_info(base / "version.json")
    installed = load_frontend_build_info(base / "frontend" / "dist")
    return {
        "version": release.version,
        "channel": release.channel,
        "tag": release.tag,
        "frontend": {
            "requiredVersion": release.frontend.version,
            "installedVersion": installed.frontend_version if installed else None,
            "buildCommit": installed.commit if installed else None,
            "builtAt": installed.built_at if installed else None,
            "source": (installed.source if installed else None) or None,
        },
    }


def load_download_config(
    root: Optional[Path] = None,
    *,
    source: Optional[str] = None,
    static_base_url: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> FrontendDownloadConfig:
    base = Path(root) if root is not None else project_root()
    environment = os.environ if environ is None else environ
    file_payload: dict[str, object] = {}
    config_path = base / DOWNLOAD_CONFIG_FILE
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FrontendReleaseConfigError(f"无法读取下载源配置 {config_path}: {error}") from error
        if not isinstance(loaded, dict):
            raise FrontendReleaseConfigError("frontend-download.json 顶层必须是对象")
        file_payload = loaded

    def setting(file_key: str, env_key: str, default: str) -> str:
        value = environment.get(env_key)
        if value is not None:
            return value.strip()
        from_file = file_payload.get(file_key)
        return str(from_file).strip() if from_file is not None else default

    order_value = environment.get("MIKAZUKI_FRONTEND_AUTO_ORDER")
    if order_value is not None:
        order = tuple(item.strip() for item in order_value.split(",") if item.strip())
    else:
        from_file = file_payload.get("autoOrder")
        if from_file is None:
            order = ("github", "jihulab", "static")
        elif isinstance(from_file, list) and all(isinstance(item, str) for item in from_file):
            order = tuple(item.strip() for item in from_file if item.strip())
        else:
            raise FrontendReleaseConfigError("autoOrder 必须是下载源名称数组")

    selected_source = source or setting("source", "MIKAZUKI_FRONTEND_SOURCE", DEFAULT_SOURCE)
    selected_static_url = static_base_url or setting(
        "staticBaseUrl", "MIKAZUKI_FRONTEND_STATIC_BASE_URL", ""
    )
    selected_source = selected_source.strip().lower()
    if selected_source == "cn":
        selected_source = "jihulab"
    valid_sources = {"github", "jihulab", "static", "auto", "off"}
    if selected_source not in valid_sources:
        raise FrontendReleaseConfigError(
            f"未知前端下载源 {selected_source!r}，可选值：{', '.join(sorted(valid_sources))}"
        )
    normalized_order = tuple("jihulab" if item.lower() == "cn" else item.lower() for item in order)
    if any(item not in {"github", "jihulab", "static"} for item in normalized_order):
        raise FrontendReleaseConfigError("autoOrder 只能包含 github、jihulab、static")

    return FrontendDownloadConfig(
        source=selected_source,
        github_repository=setting(
            "githubRepository", "MIKAZUKI_FRONTEND_GITHUB_REPOSITORY", DEFAULT_GITHUB_REPOSITORY
        ),
        github_base_url=setting(
            "githubBaseUrl", "MIKAZUKI_FRONTEND_GITHUB_BASE_URL", "https://github.com"
        ),
        jihulab_project=setting(
            "jihulabProject", "MIKAZUKI_FRONTEND_JIHULAB_PROJECT", DEFAULT_JIHULAB_PROJECT
        ),
        jihulab_package=setting(
            "jihulabPackage", "MIKAZUKI_FRONTEND_JIHULAB_PACKAGE", DEFAULT_JIHULAB_PACKAGE
        ),
        jihulab_base_url=setting(
            "jihulabBaseUrl", "MIKAZUKI_FRONTEND_JIHULAB_BASE_URL", "https://jihulab.com"
        ),
        static_base_url=selected_static_url,
        auto_order=normalized_order,
    )


def providers_for_config(config: FrontendDownloadConfig) -> list[FrontendReleaseProvider]:
    names: Sequence[str] = config.auto_order if config.source == "auto" else (config.source,)
    providers: list[FrontendReleaseProvider] = []
    for name in names:
        if name == "github":
            providers.append(
                GithubReleaseProvider(config.github_repository, base_url=config.github_base_url)
            )
        elif name == "jihulab":
            providers.append(
                JihulabGenericProvider(
                    config.jihulab_project,
                    config.jihulab_package,
                    base_url=config.jihulab_base_url,
                )
            )
        elif name == "static":
            if config.static_base_url:
                providers.append(StaticFrontendProvider(config.static_base_url))
            elif config.source == "static":
                raise FrontendReleaseConfigError(
                    "使用 static 下载源时必须设置 MIKAZUKI_FRONTEND_STATIC_BASE_URL、配置文件或启动参数"
                )
    if not providers and config.source != "off":
        raise FrontendReleaseConfigError("没有可用的前端下载源")
    return providers


def ensure_frontend_release(
    root: Optional[Path] = None,
    *,
    source: Optional[str] = None,
    static_base_url: Optional[str] = None,
    skip_download: bool = False,
    force: bool = False,
    environ: Optional[Mapping[str, str]] = None,
    providers: Optional[Sequence[FrontendReleaseProvider]] = None,
    downloader: Optional[Callable[[str, Path, float], str]] = None,
    timeout: float = 30.0,
) -> FrontendEnsureResult:
    base = Path(root) if root is not None else project_root()
    release = load_release_info(base / "version.json")
    frontend_dir = base / "frontend" / "dist"
    installed = load_frontend_build_info(frontend_dir)
    installed_version = installed.frontend_version if installed else ""
    has_index = (frontend_dir / "index.html").is_file()

    if not force and has_index and _build_matches_release(installed, release):
        return FrontendEnsureResult(
            "current", release.frontend.version, installed_version, installed.source
        )

    if skip_download or (not release.frontend.auto_download and not force):
        if has_index:
            log.warning(
                "frontend/dist 与要求版本不一致（当前 %s，需要 %s），已跳过自动下载",
                installed_version or "未知",
                release.frontend.version,
            )
            return FrontendEnsureResult("skipped", release.frontend.version, installed_version)
        log.warning("frontend/dist 不存在；当前版本配置已禁用前端自动下载")
        return FrontendEnsureResult("missing", release.frontend.version, installed_version)

    config = load_download_config(
        base,
        source=source,
        static_base_url=static_base_url,
        environ=environ,
    )
    if config.source == "off":
        if has_index:
            log.warning(
                "frontend/dist 与要求版本不一致（当前 %s，需要 %s），下载源已关闭",
                installed_version or "未知",
                release.frontend.version,
            )
            return FrontendEnsureResult("skipped", release.frontend.version, installed_version)
        log.warning("frontend/dist 不存在；前端下载源已关闭")
        return FrontendEnsureResult("missing", release.frontend.version, installed_version)

    selected_providers = list(providers) if providers is not None else providers_for_config(config)
    if not selected_providers:
        raise FrontendReleaseConfigError("没有可用的前端下载源")
    download = downloader or _download_file

    frontend_parent = frontend_dir.parent
    frontend_parent.mkdir(parents=True, exist_ok=True)
    lock_path = frontend_parent / ".frontend-update.lock"
    with _update_lock(lock_path):
        installed = load_frontend_build_info(frontend_dir)
        if (
            not force
            and (frontend_dir / "index.html").is_file()
            and _build_matches_release(installed, release)
        ):
            return FrontendEnsureResult(
                "current",
                release.frontend.version,
                installed.frontend_version,
                installed.source,
            )

        failures: list[str] = []
        for provider in selected_providers:
            try:
                artifact = provider.locate(release)
                log.info(
                    "正在从 %s 下载前端 %s",
                    artifact.source,
                    release.frontend.version,
                )
                _download_and_install(
                    artifact,
                    release,
                    frontend_dir,
                    download=download,
                    timeout=timeout,
                )
                return FrontendEnsureResult(
                    "installed",
                    release.frontend.version,
                    release.frontend.version,
                    artifact.source,
                )
            except FrontendReleaseError as error:
                failures.append(f"{provider.name}: {error}")
                log.warning("前端下载源 %s 失败：%s", provider.name, error)

    details = "; ".join(failures) or "未知错误"
    raise FrontendDownloadError(
        f"无法安装前端 {release.frontend.version}。{details}。"
        "可切换 --frontend-source，或使用 --skip-frontend-download 后手动构建。"
    )


def _download_and_install(
    artifact: ArtifactLocation,
    release: ReleaseInfo,
    frontend_dir: Path,
    *,
    download: Callable[[str, Path, float], str],
    timeout: float,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".frontend-update-", dir=str(frontend_dir.parent)) as temp:
        temp_root = Path(temp)
        checksum_path = temp_root / release.frontend.checksum_asset
        archive_path = temp_root / release.frontend.asset
        download(artifact.checksum_url, checksum_path, timeout)
        expected_sha256 = _parse_sha256_file(checksum_path)
        actual_sha256 = download(artifact.archive_url, archive_path, timeout)
        if actual_sha256.lower() != expected_sha256:
            raise FrontendDownloadError(
                f"前端压缩包 SHA-256 不匹配：期望 {expected_sha256}，实际 {actual_sha256}"
            )

        extract_root = temp_root / "extracted"
        extract_root.mkdir()
        payload = _safe_extract_zip(archive_path, extract_root)
        build_info = load_frontend_build_info(payload)
        if not (payload / "index.html").is_file():
            raise FrontendArchiveError("前端压缩包缺少 index.html")
        if build_info is None:
            raise FrontendArchiveError(f"前端压缩包缺少有效的 {BUILD_INFO_FILE}")
        if build_info.frontend_version != release.frontend.version:
            raise FrontendArchiveError(
                f"前端压缩包版本为 {build_info.frontend_version}，需要 {release.frontend.version}"
            )
        if build_info.app_version != release.version:
            raise FrontendArchiveError(
                f"前端压缩包应用版本为 {build_info.app_version}，需要 {release.version}"
            )
        _record_installed_source(payload, artifact.source)
        _atomic_replace_directory(payload, frontend_dir)


def _download_file(url: str, destination: Path, timeout: float) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[BaseException] = None
    retry_statuses = {429, 500, 502, 503, 504}
    for attempt in range(3):
        digest = hashlib.sha256()
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": "lora-scripts-frontend-updater/1",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with destination.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
            return digest.hexdigest()
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in retry_statuses or attempt == 2:
                break
            delay = _retry_delay(error.headers.get("Retry-After"), attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt == 2:
                break
            delay = 0.5 * (2 ** attempt)
        if destination.exists():
            destination.unlink()
        time.sleep(delay)
    if destination.exists():
        destination.unlink()
    raise FrontendDownloadError(f"下载失败 {url}: {last_error}") from last_error


def _safe_extract_zip(archive: Path, destination: Path) -> Path:
    try:
        bundle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise FrontendArchiveError(f"无法打开前端压缩包：{error}") from error

    with bundle:
        entries = bundle.infolist()
        root = destination.resolve()
        for item in entries:
            normalized = item.filename.replace("\\", "/")
            relative = PurePosixPath(normalized)
            if (
                not normalized
                or relative.is_absolute()
                or PureWindowsPath(normalized).drive
                or not relative.parts
                or ".." in relative.parts
            ):
                raise FrontendArchiveError(f"前端压缩包包含不安全路径：{item.filename}")
            target = destination.joinpath(*relative.parts)
            resolved = target.resolve()
            if not _is_within(resolved, root):
                raise FrontendArchiveError(f"前端压缩包路径越界：{item.filename}")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    if (destination / "index.html").is_file():
        return destination
    dist = destination / "dist"
    if (dist / "index.html").is_file():
        return dist
    roots = [item for item in destination.iterdir() if item.is_dir()]
    if len(roots) == 1 and (roots[0] / "index.html").is_file():
        return roots[0]
    raise FrontendArchiveError("前端压缩包中找不到唯一的 dist 内容目录")


def _atomic_replace_directory(source: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}-backup-{uuid.uuid4().hex}"
    had_destination = destination.exists()
    try:
        if had_destination:
            os.replace(destination, backup)
        os.replace(source, destination)
    except OSError as error:
        if had_destination and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise FrontendArchiveError(f"无法替换 frontend/dist：{error}") from error
    if backup.exists():
        try:
            _remove_path(backup)
        except OSError as error:
            log.warning("无法清理旧前端备份 %s：%s", backup, error)


@contextmanager
def _update_lock(path: Path) -> Iterator[None]:
    descriptor: Optional[int] = None
    try:
        try:
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            try:
                stale = time.time() - path.stat().st_mtime > 600
            except OSError:
                stale = False
            if not stale:
                raise FrontendDownloadError("另一个进程正在更新前端，请稍后重试") from error
            path.unlink(missing_ok=True)
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
            path.unlink(missing_ok=True)


def _parse_sha256_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise FrontendDownloadError(f"无法读取 SHA-256 文件：{error}") from error
    token = text.removeprefix("sha256:").split()[0] if text else ""
    if not SHA256_TOKEN.fullmatch(token):
        raise FrontendDownloadError("SHA-256 文件格式无效")
    return token.lower()


def _build_matches_release(
    build: Optional[FrontendBuildInfo], release: ReleaseInfo
) -> bool:
    return bool(
        build is not None
        and build.app_version == release.version
        and build.frontend_version == release.frontend.version
    )


def _record_installed_source(frontend_dir: Path, source: str) -> None:
    path = frontend_dir / BUILD_INFO_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("build-info.json 顶层不是对象")
        payload["source"] = source
        payload["installedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise FrontendArchiveError(f"无法记录前端安装来源：{error}") from error


def _validate_token(value: object, label: str) -> None:
    if not isinstance(value, str) or not VERSION_TOKEN.fullmatch(value):
        raise FrontendReleaseConfigError(f"{label}格式无效：{value!r}")


def _validate_asset_name(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise FrontendReleaseConfigError(f"{label}文件名无效：{value!r}")


def _http_base_url(value: str, label: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FrontendReleaseConfigError(f"{label}地址必须是 http(s) URL")
    return normalized


def _retry_delay(header: Optional[str], attempt: int) -> float:
    if header:
        try:
            return min(10.0, max(0.0, float(header)))
        except ValueError:
            pass
    return 0.5 * (2 ** attempt)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
