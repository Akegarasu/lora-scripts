LoRA Scripts - Windows NVIDIA portable

Extract the entire archive to a writable directory, then double-click
run_gui.bat. The GUI opens at http://127.0.0.1:28000 by default.

This package includes Python 3.11.9, a CUDA PyTorch runtime, training
dependencies, the matching ONNX GPU tagger runtime, and the built frontend.
You do not need to install Python, Node.js, Git, or the CUDA Toolkit.

Release variants:
  lora-scripts_windows_portable_nvidia.7z
    Default: CUDA 13.0, PyTorch 2.14.1, ONNX Runtime GPU 1.31.1.
    Requires an NVIDIA R580 or newer driver.
  lora-scripts_windows_portable_nvidia_cu128.7z
    Fallback: CUDA 12.8, PyTorch 2.11.0, ONNX Runtime GPU 1.26.0.
    Requires a driver compatible with CUDA 12.8.

Both variants require a Turing or newer NVIDIA GPU. The cu128 variant is
a CUDA/driver fallback and does not restore Pascal or Volta GPU support.
Each archive has a matching .sha256 file. Keep the variants in separate
directories; do not combine their Python runtimes or dependency files.

Place your training models in models and your datasets in train. Training
outputs are written to output. Model weights are not included; caption
models and Hugging Face models are downloaded when you select them.

Keep all files and subdirectories together when moving this installation.
Do not copy a separate venv or Python installation into this directory.
Use python\python.exe -m pip when managing this package's dependencies.

You can pass GUI options from a terminal, for example:
    run_gui.bat --port 28001

The selected CUDA profile and Python version are recorded in runtime-info.json.
The installed Python packages are recorded in installed-packages.txt.
See README.md, README-zh.md, and docs for application documentation.
