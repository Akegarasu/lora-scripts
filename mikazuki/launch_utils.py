import os
import re
import sys
import shutil
import subprocess
import pkg_resources
import locale
from typing import List
from mikazuki.utils import run_pip


def smart_pip_mirror():
    if locale.getdefaultlocale()[0] == "zh_CN":
        os.environ.setdefault("PIP_FIND_LINKS", "https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html")
        os.environ.setdefault("PIP_INDEX_URL", "https://mirror.baidu.com/pypi/simple")

def find_windows_git():
    possible_paths = ["git\\bin\\git.exe", "git\\cmd\\git.exe", "Git\\mingw64\\libexec\\git-core\\git.exe"]
    for path in possible_paths:
        if os.path.exists(path):
            return path


def prepare_frontend():
    if not os.path.exists("./frontend/dist"):
        print("Frontend not found, try clone...")
        print("Checking git installation...")
        if not shutil.which("git"):
            if sys.platform == "win32":
                git_path = find_windows_git()

                if git_path is not None:
                    print(f"Git not found, but found git in {git_path}, add it to PATH")
                    os.environ["PATH"] += os.pathsep + os.path.dirname(git_path)
                    return
            else:
                print("Git not found, please install git first")
                sys.exit(1)
        subprocess.run(["git", "submodule", "init"])
        subprocess.run(["git", "submodule", "update"])


def remove_warnings():
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    if sys.platform == "win32":
        # disable triton on windows
        os.environ["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
    os.environ["BITSANDBYTES_NOWELCOME"] = "1"
    os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"


def check_dirs(dirs: List):
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)


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
                        print(f'Package wrong version: {pkg_name} {version} required {pkg_version}')
                        return False
            else:
                print(f'Package version not found: {pkg_name}')
                return False

        return True
    except ModuleNotFoundError:
        print(f'Package not installed: {pkgs}')
        return False


def validate_requirements(requirements_file: str):
    with open(requirements_file, 'r', encoding='utf8') as f:
        lines = [
            line.strip()
            for line in f.readlines()
            if line.strip() != ''
            and not line.startswith("#")
            and not line.startswith("-")
            and line is not None
            and "# skip_verify" not in line
        ]

        for line in lines:
            if not is_installed(line):
                run_pip(f"install {line}", line, live=True)
