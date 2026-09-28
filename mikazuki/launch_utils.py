import os
import platform
import shlex
import subprocess
import sys
import socket
import sysconfig
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

from packaging.requirements import Requirement
from packaging.version import Version

from mikazuki.log import log

python_bin = sys.executable


def base_dir_path():
    return Path(__file__).parents[1].absolute()


def run(command,
        desc: Optional[str] = None,
        errdesc: Optional[str] = None,
        custom_env: Optional[dict[str, str]] = None,
        live: Optional[bool] = True,
        shell: Optional[bool] = None):

    if shell is None:
        shell = sys.platform != "win32"

    if desc is not None:
        print(desc)

    result = subprocess.run(
        command,
        capture_output=not live,
        shell=shell,
        env=os.environ if custom_env is None else custom_env,
    )

    if result.returncode != 0:
        message = f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}
"""
        if not live:
            message += (
                f"stdout: {result.stdout.decode('utf8', errors='ignore') or '<empty>'}\n"
                f"stderr: {result.stderr.decode('utf8', errors='ignore') or '<empty>'}\n"
            )
        raise RuntimeError(message)

    return "" if live else result.stdout.decode(encoding="utf8", errors="ignore")


def is_installed(package: str) -> bool:
    requirement = Requirement(package)
    if requirement.marker is not None and not requirement.marker.evaluate():
        return True
    try:
        installed = version(requirement.name)
    except PackageNotFoundError:
        log.warning(f'Package not installed: {requirement.name}')
        return False
    if not requirement.specifier.contains(installed, prereleases=True):
        log.info(f'Package wrong version: {requirement.name} {installed} required {requirement.specifier}')
        return False
    return True


def validate_requirements(requirements_file: str):
    with open(requirements_file, 'r', encoding='utf8') as f:
        index_url = ""
        for raw_line in f:
            if "# skip_verify" in raw_line:
                continue
            line = raw_line.split(" #", 1)[0].strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("--index-url "):
                index_url = line.removeprefix("--index-url ").strip()
                continue
            if line.startswith("-"):
                continue

            if not is_installed(line):
                command = ["install", line]
                if index_url:
                    command.extend(["--index-url", index_url])
                run_pip(command, line, live=True)


def setup_windows_bitsandbytes():
    if sys.platform != "win32":
        return

    bnb_package = "bitsandbytes==0.46.0"
    bnb_path = Path(sysconfig.get_paths()["purelib"]) / "bitsandbytes"

    installed_bnb = is_installed("bitsandbytes")  # don't check version here
    bnb_cuda_setup = any(bnb_path.glob("libbitsandbytes_cuda*.dll"))

    if not installed_bnb or not bnb_cuda_setup:
        log.error("detected wrong install of bitsandbytes, reinstall it")
        run_pip("uninstall bitsandbytes -y", "bitsandbytes", live=True)
        run_pip(f"install {bnb_package}", bnb_package, live=True)


def setup_onnxruntime(
        onnx_version: Optional[str] = None,
        index_url: Optional[str] = None
):
    if sys.platform == "linux":
        libc_ver = platform.libc_ver()
        if libc_ver[0] == "glibc" and Version(libc_ver[1]) <= Version("2.27"):
            onnx_version = "1.16.3"

    onnx_version = os.environ.get("ONNXRUNTIME_VERSION", onnx_version)

    if onnx_version and not is_installed(f"onnxruntime-gpu=={onnx_version}"):
        log.info("uninstalling wrong onnxruntime version")
        run_pip("uninstall onnxruntime -y", "onnxruntime", live=True)
        run_pip("uninstall onnxruntime-gpu -y", "onnxruntime", live=True)

    if not is_installed("onnxruntime-gpu"):
        log.info("installing onnxruntime")
        pip_install("onnxruntime", onnx_version, index_url=index_url, live=True)
        pip_install("onnxruntime-gpu", onnx_version, index_url=index_url, live=True)


def run_pip(command, desc=None, live=False):
    arguments = shlex.split(command) if isinstance(command, str) else command
    return run(
        [python_bin, "-m", "pip", *arguments],
        desc=f"Installing {desc}",
        errdesc=f"Couldn't install {desc}",
        live=live,
        shell=False,
    )


def pip_install(package: str, version: Optional[str] = None, index_url: Optional[str] = None, live: bool = True):
    """
    Install a package using pip.
    :param package: The name of the package to install.
    :param version: The version of the package to install (optional).
    :param index_url: The index URL to use for installing the package (optional).
    """
    if version:
        package = f"{package}=={version}"

    command = ["install", package]

    if index_url:
        command.extend(["-i", index_url])

    run_pip(command, desc=f"Installing {package}", live=live)


def network_gfw_test(timeout=3):
    try:
        import requests
        # requests will auto detect system proxies
        response = requests.get("https://www.google.com", timeout=timeout)
        if response.status_code == 200:
            log.info("Network test passed")
            return True
        else:
            log.error(f"Network test failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        log.error(f"Network test failed: {e}")
        return False


def prepare_environment(
        disable_auto_mirror: bool = True,
        prepare_onnxruntime: bool = True,
):
    if sys.platform == "win32":
        # disable triton on windows
        os.environ["XFORMERS_FORCE_DISABLE_TRITON"] = "1"

    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    os.environ["BITSANDBYTES_NOWELCOME"] = "1"
    os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    if not disable_auto_mirror and not network_gfw_test():
        log.info("use pip & huggingface mirrors")
        os.environ.setdefault("PIP_FIND_LINKS", "https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html")
        os.environ.setdefault("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    if not os.environ.get("PATH"):
        os.environ["PATH"] = os.path.dirname(sys.executable)

    Path("logs").mkdir(exist_ok=True)

    validate_requirements("requirements.txt")
    setup_windows_bitsandbytes()

    if prepare_onnxruntime:
        setup_onnxruntime()


def check_port_available(port: int) -> bool:
    try:
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def find_available_port(port_start: int, port_end: int) -> Optional[int]:
    for port in range(port_start, port_end):
        if check_port_available(port):
            return port

    log.error(f"error finding available ports in range: {port_start} -> {port_end}")
    return None
