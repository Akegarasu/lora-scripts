SD-Trainer

LoRA 训练脚本（又名SD-Trainer）

LoRA 与 Dreambooth 训练 GUI 和脚本预设，以及一键训练环境，适用于[kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts.git)

## ✨新功能：训练界面

![图像](https://github.com/Akegarasu/lora-scripts/assets/36563862/0a2edcb8-023a-4fe6-8c92-2bad9ccab64c)

按照下面的安装指南安装 GUI，然后运行`run_gui.ps1`（Windows）或`run_gui.sh`（Linux）来启动GUI。

## 使用方法

### 克隆带子模块的仓库

**必须** 使用如下指令克隆，否则将无法使用子模块。

```sh
git clone --recurse-submodules https://github.com/Akegarasu/lora-scripts
```

### 必需的依赖

Python 3.10.8 和 Git

### Windows

#### 安装

右键运行 `install-cn.ps1` 将自动为您创建一个虚拟环境并安装必要的依赖项。

#### 训练

编辑`train.ps1`，然后运行它。

### Linux

#### 安装

运行 `install.bash` 将创建一个虚拟环境并安装必要的依赖项。

#### 训练

训练脚本 `train.sh` **不会** 为您激活虚拟环境。您应该先激活虚拟环境。

```sh
source venv/bin/activate
```

编辑`train.sh`，然后运行它。

#### TensorBoard

运行`tensorboard.ps1`将在http://localhost:6006/上启动TensorBoard。

![](./assets/tensorboard-example.png)