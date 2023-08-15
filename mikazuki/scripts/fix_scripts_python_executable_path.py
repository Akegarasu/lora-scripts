import os
import sys
import re
from pathlib import Path

py_path = sys.executable
scripts_path = Path(sys.executable).parent

if scripts_path.name != "Scripts":
    print("Seems your env not venv, do you want to continue? [y/n]")
    sure = input()
    if sure != "y":
        sys.exit(1)

scripts_list = os.listdir(scripts_path)

for script in scripts_list:
    if not script.endswith(".exe") or script in ["python.exe", "pythonw.exe"]:
        continue

    with open(os.path.join(scripts_path, script), "rb+") as f:
        s = f.read()
        spl = re.split(b'(#!.*python\.exe)', s)
        if len(spl) == 3:
            spl[1] = bytes(b"#!"+sys.executable.encode())
        f.seek(0)
        f.write(b''.join(spl))
        print(f"fixed {script}")