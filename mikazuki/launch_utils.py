import locale
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from typing import List
from pathlib import Path
from typing import Optional

import pkg_resources

from mikazuki.log import log

python_bin = sys.executable


def base_dir_path():
    return Path(__file__).parents[1].absolute()


def find_windows_git():
    possible_paths = ["git\\bin\\git.exe", "git\\cmd\\git.exe", "Git\\mingw64\\libexec\\git-core\\git.exe"]
    for path in possible_paths:
        if os.path.exists(path):
            return path


def prepare_submodules():
    frontend_path = base_dir_path() / "frontend" / "dist"
    tag_editor_path = base_dir_path() / "mikazuki" / "dataset-tag-editor" / "scripts"

    if not os.path.exists(frontend_path) or not os.path.exists(tag_editor_path):
        log.info("submodule not found, try clone...")
        log.info("checking git installation...")
        if not shutil.which("git"):
            if sys.platform == "win32":
                git_path = find_windows_git()

                if git_path is not None:
                    log.info(f"Git not found, but found git in {git_path}, add it to PATH")
                    os.environ["PATH"] += os.pathsep + os.path.dirname(git_path)
                    return
            else:
                log.error("git not found, please install git first")
                sys.exit(1)
        subprocess.run(["git", "submodule", "init"])
        subprocess.run(["git", "submodule", "update"])


def check_dirs(dirs: List):
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)


def run(command,
        desc: Optional[str] = None,
        errdesc: Optional[str] = None,
        custom_env: Optional[list] = None,
        live: Optional[bool] = True,
        shell: Optional[bool] = None):

    if shell is None:
        shell = False if sys.platform == "win32" else True

    if desc is not None:
        print(desc)

    if live:
        result = subprocess.run(command, shell=shell, env=os.environ if custom_env is None else custom_env)
        if result.returncode != 0:
            raise RuntimeError(f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}""")

        return ""

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            shell=shell, env=os.environ if custom_env is None else custom_env)

    if result.returncode != 0:
        message = f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}
stdout: {result.stdout.decode(encoding="utf8", errors="ignore") if len(result.stdout) > 0 else '<empty>'}
stderr: {result.stderr.decode(encoding="utf8", errors="ignore") if len(result.stderr) > 0 else '<empty>'}
"""
        raise RuntimeError(message)

    return result.stdout.decode(encoding="utf8", errors="ignore")


def is_installed(package, friendly: str = None):
    #
    # This function was adapted from code written by vladimandic: https://github.com/vladmandic/automatic/commits/master
    #

    # Remove brackets and their contents from the line using regular expressions
    # e.g., diffusers[torch]==0.10.2 becomes diffusers==0.10.2
    package = re.sub(r'\[.*?\]', '', package)

    try:
        if friendly:
            pkgs = friendly.split()
        else:
            pkgs = [
                p
                for p in package.split()
                if not p.startswith('-') and not p.startswith('=')
            ]
            pkgs = [
                p.split('/')[-1] for p in pkgs
            ]   # get only package name if installing from URL

        for pkg in pkgs:
            if '>=' in pkg:
                pkg_name, pkg_version = [x.strip() for x in pkg.split('>=')]
            elif '==' in pkg:
                pkg_name, pkg_version = [x.strip() for x in pkg.split('==')]
            else:
                pkg_name, pkg_version = pkg.strip(), None

            spec = pkg_resources.working_set.by_key.get(pkg_name, None)
            if spec is None:
                spec = pkg_resources.working_set.by_key.get(pkg_name.lower(), None)
            if spec is None:
                spec = pkg_resources.working_set.by_key.get(pkg_name.replace('_', '-'), None)

            if spec is not None:
                version = pkg_resources.get_distribution(pkg_name).version
                # log.debug(f'Package version found: {pkg_name} {version}')

                if pkg_version is not None:
                    if '>=' in pkg:
                        ok = version >= pkg_version
                    else:
                        ok = version == pkg_version

                    if not ok:
                        log.info(f'Package wrong version: {pkg_name} {version} required {pkg_version}')
                        return False
            else:
                log.warning(f'Package version not found: {pkg_name}')
                return False

        return True
    except ModuleNotFoundError:
        log.warning(f'Package not installed: {pkgs}')
        return False


def validate_requirements(requirements_file: str):
    with open(requirements_file, 'r', encoding='utf8') as f:
        lines = [
            line.strip()
            for line in f.readlines()
            if line.strip() != ''
            and not line.startswith("#")
            and not (line.startswith("-") and not line.startswith("--index-url "))
            and line is not None
            and "# skip_verify" not in line
        ]

        index_url = ""
        for line in lines:
            if line.startswith("--index-url "):
                index_url = line.replace("--index-url ", "")
                continue

            if not is_installed(line):
                if index_url != "":
                    run_pip(f"install {line} --index-url {index_url}", line, live=True)
                else:
                    run_pip(f"install {line}", line, live=True)


def setup_windows_bitsandbytes():
    if sys.platform != "win32":
        return

    bnb_windows_index = os.environ.get("BNB_WINDOWS_INDEX", "https://jihulab.com/api/v4/projects/140618/packages/pypi/simple")
    bnb_package = "bitsandbytes==0.41.1"
    bnb_path = os.path.join(sysconfig.get_paths()["purelib"], "bitsandbytes")

    installed_bnb = is_installed(bnb_package)
    bnb_cuda_setup = len([f for f in os.listdir(bnb_path) if re.findall(r"libbitsandbytes_cuda.+?\.dll", f)]) != 0

    if not installed_bnb or not bnb_cuda_setup:
        log.error("detected wrong install of bitsandbytes, reinstall it")
        run_pip(f"uninstall bitsandbytes -y", "bitsandbytes", live=True)
        run_pip(f"install {bnb_package} --index-url {bnb_windows_index}", bnb_package, live=True)


def run_pip(command, desc=None, live=False):
    return run(f'"{python_bin}" -m pip {command}', desc=f"Installing {desc}", errdesc=f"Couldn't install {desc}", live=live)


def check_run(file: str) -> bool:
    result = subprocess.run([python_bin, file], capture_output=True, shell=False)
    log.info(result.stdout.decode("utf-8").strip())
    return result.returncode == 0


def prepare_environment():
    if sys.platform == "win32":
        # disable triton on windows
        os.environ["XFORMERS_FORCE_DISABLE_TRITON"] = "1"

    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    os.environ["BITSANDBYTES_NOWELCOME"] = "1"
    os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    if locale.getdefaultlocale()[0] == "zh_CN":
        log.info("detected locale zh_CN, use pip mirrors")
        os.environ.setdefault("PIP_FIND_LINKS", "https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html")
        os.environ.setdefault("PIP_INDEX_URL", "https://mirror.baidu.com/pypi/simple")

    if not os.environ.get("PATH"):
        os.environ["PATH"] = os.path.dirname(sys.executable)

    prepare_submodules()

    check_dirs(["config/autosave", "logs"])

    # if not check_run("mikazuki/scripts/torch_check.py"):
    #     sys.exit(1)

    requirements_file = "requirements_win.txt" if sys.platform == "win32" else "requirements.txt"
    validate_requirements(requirements_file)
    setup_windows_bitsandbytes()
