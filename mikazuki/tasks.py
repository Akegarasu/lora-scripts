import subprocess
import sys
import threading
import uuid
from enum import Enum
from typing import Dict

import psutil

from mikazuki.log import log


def kill_proc_tree(pid, including_parent=True):
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    for child in children:
        child.kill()
    gone, still_alive = psutil.wait_procs(children, timeout=5)
    if including_parent:
        parent.kill()
        parent.wait(5)

class TaskStatus(Enum):
    CREATED = 0
    RUNNING = 1
    FINISHED = 2
    TERMINATED = 3


class Task:
    def __init__(self, task_id, command):
        self.task_id = task_id
        self.lock = threading.Lock()
        self.command = command
        self.status = TaskStatus.CREATED

    def wait(self):
        self.process.wait()
        self.status = TaskStatus.FINISHED

    def execute(self):
        self.status = TaskStatus.RUNNING
        self.process = subprocess.Popen(self.command)

    def terminate(self):
        try:
            kill_proc_tree(self.process.pid, False)
        except Exception as e:
            log.error(f"Error when killing process: {e}")
            return
        self.status = TaskStatus.TERMINATED


class TaskManager:
    def __init__(self, max_concurrent=1) -> None:
        self.max_concurrent = max_concurrent
        self.tasks: Dict[Task] = {}

    def create_task(self, command):
        running_tasks = [t for _, t in self.tasks.items() if t.status == TaskStatus.RUNNING]
        if len(running_tasks) >= self.max_concurrent:
            log.error("Too many tasks running")
            return None
        task_id = str(uuid.uuid4())
        task = Task(task_id=task_id, command=command)
        self.tasks[task_id] = task
        task.execute()
        log.info(f"Task {task_id} created")
        return task_id

    def add_task(self, task_id: str, task: Task):
        self.tasks[task_id] = task

    def terminate_task(self, task_id: str):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.terminate()

    def wait_for_process(self, task_id: str):
        if task_id in self.tasks:
            task: Task = self.tasks[task_id]
            task.wait()

    def dump(self):
        return {
            "tasks": [
                {
                    "id": task.task_id,
                    "status": task.status.name,
                }
                for task in self.tasks.values()
            ]
        }


tm = TaskManager()
