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
  <a href="https://github.com/Akegarasu/blive-queue/releases">Download</a>
  ·
  <a href="https://github.com/Akegarasu/blive-queue/blob/main/README.md">Documents</a>
  ·
  <a href="https://github.com/Akegarasu/lora-scripts/blob/main/README-zh.md">中文README</a>
</p>

LoRA-scripts (a.k.a SD-Trainer)

LoRA & Dreambooth training GUI & scripts preset & one key training environment for [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts.git)

## ✨NEW: Train GUI

![image](https://github.com/Akegarasu/lora-scripts/assets/36563862/0a2edcb8-023a-4fe6-8c92-2bad9ccab64c)

Follow the installation guide below to install the GUI, then run `run_gui.ps1`(windows) or `run_gui.sh`(linux) to start the GUI.

## Usage

### Clone repo with submodules

```sh
git clone --recurse-submodules https://github.com/Akegarasu/lora-scripts
```

### Required Dependencies

Python 3.10.8 and Git

### Windows

#### Installation

Run `install.ps1` will automaticilly create a venv for you and install necessary deps.

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

Run `tensorboard.ps1` will start TensorBoard at http://localhost:6006/

![](./assets/tensorboard-example.png)
