"""Check the staged Windows bundle without a GPU or model downloads."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, build_opener


class ScriptSources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source)


def runtime_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSAFEPATH"):
        env.pop(key, None)
    env.update(
        PYTHONHOME=str(root / "python"),
        HF_HOME=str(root / "huggingface"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        XFORMERS_FORCE_DISABLE_TRITON="1",
        BITSANDBYTES_NOWELCOME="1",
    )
    env["PATH"] = os.pathsep.join(
        [str(root / "python"), str(root / "python" / "Scripts"), env.get("PATH", "")]
    )
    return env


def check_entrypoints(root: Path, python: Path, env: dict[str, str]) -> None:
    commands = [
        ["scripts/dev/train_network.py", "--help"],
        ["-m", "accelerate.commands.launch", "--help"],
        ["-m", "mikazuki.captioning.worker", "--help"],
    ]
    for arguments in commands:
        print(f"Checking {' '.join(arguments)}", flush=True)
        try:
            result = subprocess.run(
                [str(python), "-s", *arguments],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            raise RuntimeError(f"{' '.join(arguments)} timed out:\n{output}") from error
        if result.returncode:
            raise RuntimeError(f"{' '.join(arguments)} failed:\n{result.stdout}")
        if "usage:" not in result.stdout.lower():
            raise RuntimeError(f"{' '.join(arguments)} did not display CLI help:\n{result.stdout}")

    # Exercise an optimizer step: imports alone can miss embedded-stdlib or
    # torch._dynamo failures that first occur when actual training begins.
    print("Checking a CPU forward/backward/AdamW step", flush=True)
    subprocess.run(
        [str(python), "-s", "-c",
         "import torch; torch.set_num_threads(1); torch.manual_seed(0); "
         "model = torch.nn.Linear(4, 2); optimizer = torch.optim.AdamW(model.parameters(), lr=0.1); "
         "before = model.weight.detach().clone(); optimizer.zero_grad(); "
         "loss = model(torch.ones(2, 4)).square().mean(); "
         "assert torch.isfinite(loss).item(); loss.backward(); optimizer.step(); "
         "assert not torch.equal(before, model.weight.detach()); print('CPU optimizer step passed')"],
        cwd=root,
        env=env,
        check=True,
        timeout=180,
    )


def check_gui(root: Path, python: Path, env: dict[str, str], release: dict) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}/"
    # Run the real launcher, suppressing only its automatic desktop browser window.
    launcher = (
        "import runpy, sys, webbrowser; "
        "webbrowser.open = lambda *args, **kwargs: False; "
        "sys.argv = ['gui.py', *sys.argv[1:]]; "
        "runpy.run_path('gui.py', run_name='__main__')"
    )
    command = [
        str(python), "-s", "-c", launcher,
        "--host", "127.0.0.1", "--port", str(port),
        "--skip-prepare-environment", "--skip-frontend-download",
    ]
    opener = build_opener(ProxyHandler({}))
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 90
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"GUI exited with code {process.returncode}")
                try:
                    with opener.open(urljoin(base_url, "api/v2/health"), timeout=2) as response:
                        health = json.load(response)
                    break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("GUI health check did not become ready within 90 seconds")
                    time.sleep(0.5)

            if health.get("status") != "ok" or health.get("version") != release["version"]:
                raise RuntimeError(f"Unexpected health response: {health}")
            frontend = health.get("frontend", {})
            expected_version = release["frontend"]["version"]
            if any(frontend.get(key) != expected_version for key in ("requiredVersion", "installedVersion")):
                raise RuntimeError(f"Frontend version mismatch: {frontend}")

            with opener.open(base_url, timeout=10) as response:
                html = response.read()
            if html != (root / "frontend" / "dist" / "index.html").read_bytes():
                raise RuntimeError("GUI did not serve the packaged frontend index.html")
            scripts = ScriptSources()
            scripts.feed(html.decode("utf-8"))
            if not scripts.sources:
                raise RuntimeError("Built frontend has no JavaScript entrypoint")
            asset_url = urljoin(base_url, scripts.sources[0])
            if urlparse(asset_url).netloc != urlparse(base_url).netloc:
                raise RuntimeError("Frontend entrypoint is not bundled locally")
            with opener.open(asset_url, timeout=10) as response:
                if "javascript" not in response.headers.get("Content-Type", "") or not response.read():
                    raise RuntimeError("GUI did not serve the bundled JavaScript asset")
            print("GUI health, frontend version, index and JavaScript asset checks passed.", flush=True)
        except Exception:
            log.seek(0)
            print(log.read().decode("utf-8", errors="replace"), flush=True)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


@contextmanager
def clean_runtime_outputs(root: Path):
    """Remove only files/directories created by this smoke run in data folders."""
    def snapshot() -> set[Path]:
        paths: set[Path] = set()
        for name in ("config", "logs", "huggingface", "models", "train", "output", "temp"):
            directory = root / name
            if directory.exists():
                paths.add(directory)
                paths.update(directory.rglob("*"))
        return paths

    before = snapshot()
    try:
        yield
    finally:
        for path in sorted(snapshot() - before, key=lambda item: len(item.parts), reverse=True):
            if not path.resolve().is_relative_to(root):
                raise RuntimeError(f"Smoke output escaped the staged bundle: {path}")
            if path.is_file() or path.is_symlink():
                path.unlink()
            else:
                path.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Staged lora-scripts_windows_portable directory")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    python = root / "python" / "python.exe"
    if not python.is_file():
        raise RuntimeError(f"Bundled Python is missing: {python}")
    release = json.loads((root / "version.json").read_text(encoding="utf-8"))
    build = json.loads((root / "frontend" / "dist" / "build-info.json").read_text(encoding="utf-8"))
    if build.get("appVersion") != release["version"] or build.get("frontendVersion") != release["frontend"]["version"]:
        raise RuntimeError("Packaged frontend build metadata does not match version.json")
    env = runtime_environment(root)
    with clean_runtime_outputs(root):
        check_entrypoints(root, python, env)
        check_gui(root, python, env, release)
    print("Windows portable smoke checks passed.", flush=True)


if __name__ == "__main__":
    main()
