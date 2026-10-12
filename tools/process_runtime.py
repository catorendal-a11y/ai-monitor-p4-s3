"""Reap only an explicitly launched child and its descendants before retrying."""
import subprocess
import os
import psutil


class ChildCleanupError(RuntimeError):
    """Worker startup/cleanup could not be confirmed; do not retry."""


def start_child(command, **options):
    """Windows starts suspended, assigns a kill-on-close job, then resumes."""
    if os.name!='nt': return subprocess.Popen(command,**options)
    from windows_job import WindowsJob
    job=WindowsJob()
    process=None
    try:
        options['creationflags']=options.get('creationflags',0)|subprocess.CREATE_NO_WINDOW|0x4
        process=subprocess.Popen(command,**options)
        job.attach_and_resume(process)
        process._aim_job=job
        return process
    except BaseException:
        cleanup_failed=False
        try:
            if process is not None:
                if process.poll() is None: process.kill()
                process.wait(timeout=3)
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream is not None: stream.close()
        except BaseException: cleanup_failed=True
        finally:
            try: job.release()
            except OSError: cleanup_failed=True
        if cleanup_failed: raise ChildCleanupError('Worker startup cleanup unconfirmed; retry blocked') from None
        raise


def stop_child(process):
    job=vars(process).get('_aim_job')
    if job is not None:
        job.stop()
        process.wait(timeout=3)
        return
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
