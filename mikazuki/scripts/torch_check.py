import sys

def check_torch_gpu():
    try:
        import torch
        print(f'Torch {torch.__version__}')
        if torch.cuda.is_available():
            if torch.version.cuda:
                print(
                    f'Torch backend: nVidia CUDA {torch.version.cuda} cuDNN {torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else "N/A"}')
                for device in [torch.cuda.device(i) for i in range(torch.cuda.device_count())]:
                    print(f'Torch detected GPU: {torch.cuda.get_device_name(device)} VRAM {round(torch.cuda.get_device_properties(device).total_memory / 1024 / 1024)} Arch {torch.cuda.get_device_capability(device)} Cores {torch.cuda.get_device_properties(device).multi_processor_count}')
        else:
            print("Torch is not able to use GPU, please check your torch installation.\n Use --skip-prepare-environment to disable this check")
    except Exception as e:
        print(f'Could not load torch: {e}')
        sys.exit(1)

check_torch_gpu()