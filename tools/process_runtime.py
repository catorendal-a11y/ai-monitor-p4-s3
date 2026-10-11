"""Reap only an explicitly launched child and its descendants before retrying."""
import subprocess
import psutil


def stop_child(process):
    children = []
    if process.poll() is None:
        try:
            children = psutil.Process(process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            pass
        for child in children:
            try: child.terminate()
            except psutil.NoSuchProcess: pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        try: child.kill()
        except psutil.NoSuchProcess: pass
    _, alive = psutil.wait_procs(alive, timeout=3)
    if alive or process.poll() is None:
        raise RuntimeError('Child cleanup could not be confirmed; retry is blocked.')
