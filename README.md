<div align="center">

<img src="https://github.com/Akegarasu/lora-scripts/assets/36563862/3b177f4a-d92a-4da4-85c8-a0d163061a40" width="200" height="200" alt="SD-Trainer" style="border-radius: 25px">

# SD-Trainer

_✨ Enjoy Stable Diffusion Train！ ✨_

</div>

<p align="center">
  <a href="https://github.com/Akegarasu/lora-scripts" style="margin: 2px;">
    <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/Akegarasu/lora-scripts">
  </a>
  <a href="https://github.com/Akegarasu/lora-scripts" style="margin: 2px;">
    <img alt="GitHub forks" src="https://img.shields.io/github/forks/Akegarasu/lora-scripts">
  </a>
  <a href="https://raw.githubusercontent.com/Akegarasu/lora-scripts/master/LICENSE" style="margin: 2px;">
    <img src="https://img.shields.io/github/license/Akegarasu/lora-scripts" alt="license">
  </a>
  <a href="https://github.com/Akegarasu/lora-scripts/releases" style="margin: 2px;">
    <img src="https://img.shields.io/github/v/release/Akegarasu/lora-scripts?color=blueviolet&include_prereleases" alt="release">
  </a>
</p>

<p align="center">
  <a href="https://github.com/Akegarasu/lora-scripts/releases">Download</a>
  ·
  <a href="https://github.com/Akegarasu/lora-scripts/blob/main/README.md">Documents</a>
  ·
  <a href="https://github.com/Akegarasu/lora-scripts/blob/main/README-zh.md">中文README</a>
</p>

LoRA-scripts (a.k.a SD-Trainer)

LoRA & Dreambooth training GUI & scripts preset & one key training environment for [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts.git)

## ✨NEW: Train WebUI

The **REAL** Stable Diffusion Training Studio. Everything in one WebUI.

Follow the installation guide below to install the GUI, then run `run_gui.ps1`(windows) or `run_gui.sh`(linux) to start the GUI.

![image](https://github.com/Akegarasu/lora-scripts/assets/36563862/d3fcf5ad-fb8f-4e1d-81f9-c903376c19c6)

| Tensorboard | WD 1.4 Tagger | Tag Editor |
| ------------ | ------------ | ------------ |
| ![image](https://github.com/Akegarasu/lora-scripts/assets/36563862/b2ac5c36-3edf-43a6-9719-cb00b757fc76) | ![image](https://github.com/Akegarasu/lora-scripts/assets/36563862/9504fad1-7d77-46a7-a68f-91fbbdbc7407) | ![image](https://github.com/Akegarasu/lora-scripts/assets/36563862/4597917b-caa8-4e90-b950-8b01738996f2) |

### Caption & tagging workspace

Open [http://127.0.0.1:28000/caption](http://127.0.0.1:28000/caption) after starting the GUI to scan a dataset and batch-generate tags or natural-language captions. The server-side catalog currently registers 25 models: the existing WD/CL taggers, BLIP/GIT/BLIP-2 compatibility models, and six chat VLM entries. Missing dependencies and incompatible model versions are disabled before a job starts.

Caption generation processes the full scanned dataset by default, skips existing sidecars, and writes safely. Manual image selection and review-before-write are optional. The gallery combines server-side pagination with a virtual grid for datasets containing thousands of images; long-term manual tagging, search/replace, and batch revision belong to the separate Tag Editor. Writes detect external file changes, can preserve backups, and share the GPU queue with training jobs. The feature stays outside `scripts/`, so the sd-scripts submodule can continue tracking upstream. See [the frontend/backend design notes](docs/frontend-backend-refactor-design.md) for the API, model compatibility, licensing and safety boundaries.


# Usage

### Required Dependencies

Python 3.10 and Git

### Clone repo with submodules

```sh
git clone --recurse-submodules https://github.com/Akegarasu/lora-scripts
```

## ✨ SD-Trainer GUI

### Windows

#### Installation

Run `install.ps1` will automatically create a venv for you and install necessary deps. 
If you are in China mainland, please use `install-cn.ps1`

#### Train

run `run_gui.ps1`, then program will open [http://127.0.0.1:28000](http://127.0.0.1:28000) automanticlly

### Linux

#### Installation

Run `install.bash` will create a venv and install necessary deps. 

#### Train

run `bash run_gui.sh`, then program will open [http://127.0.0.1:28000](http://127.0.0.1:28000) automanticlly

## Legacy training through run script manually

### Windows

#### Installation

Run `install.ps1` will automatically create a venv for you and install necessary deps.

#### Train

Edit `train.ps1`, and run it.

### Linux

#### Installation

Run `install.bash` will create a venv and install necessary deps.

#### Train

Training script `train.sh` **will not** activate venv for you. You should activate venv first.

```sh
source venv/bin/activate
```

Edit `train.sh`, and run it.

#### TensorBoard

Training metrics are displayed directly in each job detail. The default environment uses
`tensorboardX` only to write compatible event files and does not install or start the
TensorBoard Web UI.

## Program arguments

| Parameter Name                | Type  | Default Value | Description                                      |
|-------------------------------|-------|---------------|--------------------------------------------------|
| `--host`                      | str   | "127.0.0.1"   | Hostname for the server                          |
| `--port`                      | int   | 28000         | Port to run the server                           |
| `--listen`                    | bool  | false         | Enable listening mode for the server             |
| `--skip-prepare-environment`  | bool  | false         | Skip the environment preparation step            |
| `--skip-prepare-onnxruntime`  | bool  | false         | Skip ONNX Runtime preparation                    |
| `--disable-auto-mirror`       | bool  | false         | Disable automatic package mirror selection       |
| `--dev`                       | bool  | false         | Enable development mode and auto reload          |
