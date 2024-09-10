from mikazuki.log import log
from packaging.version import Version

available_devices = []
printable_devices = []


def check_torch_gpu():
    try:
        import torch
        log.info(f'Torch {torch.__version__}')
        if not torch.cuda.is_available():
            log.error("Torch is not able to use GPU, please check your torch installation.\n Use --skip-prepare-environment to disable this check")
            log.error("！！！Torch 无法使用 GPU，您无法正常开始训练！！！\n您的显卡可能并不支持，或是 torch 安装有误。请检查您的 torch 安装。")
            return

        if Version(torch.__version__) < Version("2.3.0"):
            log.warning("Torch version is lower than 2.3.0, which may not be able to train FLUX model properly. Please re-run the installation script (install.ps1 or install.bash) to upgrade Torch.")
            log.warning("！！！Torch 版本低于 2.3.0，将无法正常训练 FLUX 模型。请重新运行安装脚本（install-cn.ps1）以升级 Torch！！！")

        if torch.version.cuda:
            log.info(
                f'Torch backend: nVidia CUDA {torch.version.cuda} cuDNN {torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else "N/A"}')
        elif torch.version.hip:
            log.info(f'Torch backend: AMD ROCm HIP {torch.version.hip}')

        devices = [torch.cuda.device(i) for i in range(torch.cuda.device_count())]

        for pos, device in enumerate(devices):
            name = torch.cuda.get_device_name(device)
            memory = torch.cuda.get_device_properties(device).total_memory
            available_devices.append(device)
            printable_devices.append(f"GPU {pos}: {name} ({round(memory / (1024**3))} GB)")
            log.info(
                f'Torch detected GPU: {name} VRAM {round(memory / 1024 / 1024)} Arch {torch.cuda.get_device_capability(device)} Cores {torch.cuda.get_device_properties(device).multi_processor_count}')
    except Exception as e:
        log.error(f'Could not load torch: {e}')
