import time
import logging
import threading

_origin_print = print
_origin_logger_info = logging.Logger.info


class LogInterceptor:
    def __init__(self):
        self._logs = []
        self._write_lock = threading.Lock()

        self._write_counter = 0
        self._last_write_time = time.time()

    def serve(self):
        threading.Thread(target=self.watch, daemon=True).start()

    def watch(self):
        if self._write_counter >= 10:
            self._write_counter = 0
            self.push()

        elif time.time() - self._last_write_time >= 5:
            self._last_write_time = time.time()
            self.push()

    def push(self):
        pass

    def write(self, message):
        with self._write_lock:
            self._logs.append(message)

    def flush(self):
        pass


log_interceptor = LogInterceptor()


def hooked_print(msg, *args, **kwargs):
    _origin_print(msg, *args, **kwargs)
    log_interceptor.write(msg)


def hooked_info(self, msg, *args, **kwargs):
    _origin_logger_info(self, msg, *args, **kwargs)
    log_interceptor.write(msg)


__builtins__["print"] = hooked_print
logging.Logger.info = hooked_info

log_interceptor.serve()
