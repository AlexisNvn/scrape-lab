import asyncio
import contextlib
import os
import time
from collections.abc import Callable

import psutil


class ProcessMonitor:
    """Sample this harness and descendants; retain CPU of processes that exit."""

    def __init__(self, interval: float = 0.05):
        self.root = psutil.Process(os.getpid())
        self.interval = interval
        self.baseline = {p.pid for p in self.root.children(recursive=True)}
        self.owned: dict[tuple[int, float], psutil.Process] = {}
        self.cpu: dict[tuple[int, float], float] = {}
        self.peak_memory_bytes = 0
        self.task: asyncio.Task | None = None
        times = self.root.cpu_times()
        self.root_cpu_start = times.user + times.system

    def sample(self) -> None:
        memory = 0
        with contextlib.suppress(psutil.Error):
            for child in self.root.children(recursive=True):
                if child.pid not in self.baseline:
                    with contextlib.suppress(psutil.Error):
                        self.owned[child.pid, child.create_time()] = child
        for proc in [self.root, *self.owned.values()]:
            with contextlib.suppress(psutil.Error):
                if not proc.is_running():
                    continue
                memory += proc.memory_info().rss
                times = proc.cpu_times()
                value = times.user + times.system
                if proc.pid == self.root.pid:
                    value = max(0, value - self.root_cpu_start)
                self.cpu[proc.pid, proc.create_time()] = value
        self.peak_memory_bytes = max(self.peak_memory_bytes, memory)

    async def _loop(self) -> None:
        while True:
            self.sample()
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self.sample()
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self.sample()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    @property
    def cpu_time_s(self) -> float:
        return sum(self.cpu.values())

    async def cleanup(self) -> None:
        # Kill only descendants created by this attempt, checking process identity.
        self.sample()
        await asyncio.to_thread(terminate_processes, list(self.owned.values()))


def terminate_processes(processes: list[psutil.Process]) -> None:
    alive = []
    for process in reversed(processes):
        with contextlib.suppress(psutil.NoSuchProcess):
            if process.is_running():
                process.terminate()
                alive.append(process)
    _, alive = psutil.wait_procs(alive, timeout=3)
    for process in alive:
        with contextlib.suppress(psutil.NoSuchProcess):
            process.kill()
    _, alive = psutil.wait_procs(alive, timeout=3)
    if alive:
        raise RuntimeError(f"Could not terminate owned processes: {[p.pid for p in alive]}")


class Timer:
    def __init__(self, callback: Callable[[float], None]):
        self.callback = callback

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.callback(time.perf_counter() - self.start)
