from typing import Protocol


class Worker(Protocol):
    worker_id: str
    def run_one(self): ...
    def stop(self): ...
