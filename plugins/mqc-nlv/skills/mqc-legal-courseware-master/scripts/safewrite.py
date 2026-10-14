# -*- coding: utf-8 -*-
"""几方同时写同一个课件时不丢改动：编辑器、对话里的 AI、命令行可能同时在写 deck.json 与 ai/requests.json。

两件事，只用标准库：
  lock(folder)       课件文件夹的写锁。读—改—写整段持锁，别的进程（或别的线程）等它写完再读。
                     用系统的文件锁（POSIX 的 flock、Windows 的 msvcrt），进程退出系统自动放锁，
                     锁文件 .nlv-lock 一直留着、从不删除（有的沙箱不许删文件）。同一线程里嵌套持锁不会自己卡住。
  write_text(p, s)   先写到本进程、本线程独有的暂存文件，再改名覆盖。
                     原来暂存名是固定的 <文件>.nlv-new：两个进程同时写，一个改名时把另一个还没写完的暂存文件
                     搬了过去，读到的是半个文件（实测四个进程各记 25 条请求，只剩 29 条，还有进程读到空文件崩掉）。
"""
import contextlib
import os
import threading
import time

try:
    import fcntl
except ImportError:                                     # Windows
    fcntl = None
    import msvcrt

_REG = threading.Lock()
_RLOCKS = {}
_DEPTH = threading.local()


def _stage(path):
    return f"{path}.{os.getpid()}-{threading.get_ident()}.nlv-new"


def write_text(path, text):
    stage = _stage(path)
    with open(stage, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(stage, path)            # 改名覆盖，不靠删除


def write_bytes(path, data):
    stage = _stage(path)
    with open(stage, "wb") as f:
        f.write(data)
    os.replace(stage, path)


def _os_lock(f):
    if fcntl:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)


def _os_unlock(f):
    try:
        if fcntl:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


@contextlib.contextmanager
def lock(folder, timeout=30.0):
    """课件文件夹的写锁（可嵌套）。等了 timeout 秒还拿不到就报错，不无限等。"""
    key = os.path.abspath(folder)
    with _REG:
        rl = _RLOCKS.setdefault(key, threading.RLock())
    if not rl.acquire(timeout=timeout):
        raise TimeoutError("课件正被别处写着，等了半分钟还没写完：稍后再试")
    depth = getattr(_DEPTH, "d", None)
    if depth is None:
        depth = _DEPTH.d = {}
    f = None
    try:
        if depth.get(key, 0) == 0:
            os.makedirs(key, exist_ok=True)
            f = open(os.path.join(key, ".nlv-lock"), "a+b")
            t0 = time.time()
            while True:
                try:
                    _os_lock(f)
                    break
                except OSError:
                    if time.time() - t0 > timeout:
                        f.close()
                        f = None
                        raise TimeoutError("课件正被别处写着，等了半分钟还没写完：稍后再试")
                    time.sleep(0.02)
        depth[key] = depth.get(key, 0) + 1
        try:
            yield
        finally:
            depth[key] -= 1
            if f is not None:
                _os_unlock(f)
                f.close()
    finally:
        rl.release()
