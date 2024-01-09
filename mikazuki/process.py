
import sys
import os

from typing import Optional

from mikazuki.tasks import tm
from mikazuki.log import log


def run_train(toml_path: str,
              trainer_file: str = "./sd-scripts/train_network.py",
              gpu_ids: Optional[list] = ["0"],
              cpu_threads: Optional[int] = 2):
    log.info(f"Training started with config file / 训练开始，使用配置文件: {toml_path}")
    args = [
        sys.executable, "-m", "accelerate.commands.launch",  # use -m to avoid python script executable error
        "--num_cpu_threads_per_process", str(cpu_threads),  # cpu threads
        "--quiet",  # silence accelerate error message
        trainer_file,
        "--config_file", toml_path,
    ]

    if len(gpu_ids) > 1:
        args[3:3] = ["--multi_gpu", "--num_processes", "2"]
        customize_env["CUDA_VISIBLE_DEVICES"] = ",".join(gpu_ids)

    customize_env = os.environ.copy()
    customize_env["ACCELERATE_DISABLE_RICH"] = "1"
    customize_env["PYTHONUNBUFFERED"] = "1"

    try:
        task = tm.create_task(args, customize_env)
        if not task:
            return
        result = task.communicate()
        if result.returncode != 0:
            log.error(f"Training failed / 训练失败")
        else:
            log.info(f"Training finished / 训练完成")
    except Exception as e:
        log.error(f"An error occurred when training / 创建训练进程时出现致命错误: {e}")
