LoRA Scripts - Windows NVIDIA portable

Extract the entire archive to a writable directory, then double-click
run_gui.bat. The GUI opens at http://127.0.0.1:28000 by default.

This package includes Python, the CUDA 12.8 PyTorch runtime, training
dependencies, the ONNX GPU tagger runtime, and the built web frontend.
You do not need to install Python, Node.js, Git, or the CUDA Toolkit.
An NVIDIA GPU and a driver compatible with CUDA 12.8 are required.

Place your training models in models and your datasets in train. Training
outputs are written to output. Model weights are not included; caption
models and Hugging Face models are downloaded when you select them.

Keep all files and subdirectories together when moving this installation.
Do not copy a separate venv or Python installation into this directory.
Use python\python.exe -m pip when managing this package's dependencies.

You can pass GUI options from a terminal, for example:
    run_gui.bat --port 28001

The installed Python packages are recorded in installed-packages.txt.
See README.md, README-zh.md, and docs for application documentation.
