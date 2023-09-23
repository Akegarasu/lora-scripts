
import sys
import os

from typing import Optional

from mikazuki.tasks import tm
from mikazuki.log import log


def run_train(toml_path: str,
              trainer_file: str = "./sd-scripts/train_network.py",
              multi_gpu: bool = False,
              cpu_threads: Optional[int] = 2):
    log.info(f"Training started with config file / 训练开始，使用配置文件: {toml_path}")
    args = [
        sys.executable, "-m", "accelerate.commands.launch", "--num_cpu_threads_per_process", str(cpu_threads),
        trainer_file,
        "--config_file", toml_path,
    ]
    if multi_gpu:
        args.insert(3, "--multi_gpu")

    customize_env = os.environ.copy()
    customize_env["ACCELERATE_DISABLE_RICH"] = "1"
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
