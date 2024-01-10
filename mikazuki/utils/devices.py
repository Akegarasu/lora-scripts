from mikazuki.log import log

available_devices = []
printable_devices = []


def check_torch_gpu():
    try:
        import torch
        log.info(f'Torch {torch.__version__}')
        if torch.cuda.is_available():
            if torch.version.cuda:
                log.info(
                    f'Torch backend: nVidia CUDA {torch.version.cuda} cuDNN {torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else "N/A"}')

                devices = [torch.cuda.device(i) for i in range(torch.cuda.device_count())]

                for pos, device in enumerate(devices):
                    available_devices.append(device)
                    printable_devices.append(f"GPU {pos}: {torch.cuda.get_device_name(device)} ({round(torch.cuda.get_device_properties(device).total_memory / 1024 / 1024 / 1024)} GB)")
                    log.info(f'Torch detected GPU: {torch.cuda.get_device_name(device)} VRAM {round(torch.cuda.get_device_properties(device).total_memory / 1024 / 1024)} Arch {torch.cuda.get_device_capability(device)} Cores {torch.cuda.get_device_properties(device).multi_processor_count}')
        else:
            log.error("Torch is not able to use GPU, please check your torch installation.\n Use --skip-prepare-environment to disable this check")
            log.error("！！！Torch 无法使用 GPU，您无法正常开始训练！！！\n您的显卡可能并不支持，或是 torch 安装有误。请检查您的 torch 安装。")
    except Exception as e:
        log.error(f'Could not load torch: {e}')
