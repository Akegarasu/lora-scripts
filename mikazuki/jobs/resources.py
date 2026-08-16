import threading
from typing import Optional


class DeviceLease:
    """Process-local lease shared by training and caption subprocesses."""

    def __init__(self, capacity: int = 1) -> None:
        self.capacity = max(1, int(capacity))
        self._semaphore = threading.BoundedSemaphore(self.capacity)

    def acquire(self, blocking: bool = True) -> bool:
        return self._semaphore.acquire(blocking=blocking)

    def release(self) -> None:
        self._semaphore.release()


_gpu_lease: Optional[DeviceLease] = None
_gpu_lease_lock = threading.Lock()


def get_gpu_lease(capacity: int = 1) -> DeviceLease:
    global _gpu_lease
    with _gpu_lease_lock:
        if _gpu_lease is None:
            _gpu_lease = DeviceLease(capacity)
        return _gpu_lease
