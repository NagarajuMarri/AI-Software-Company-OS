class InMemoryExternalTaskQueue:
    def __init__(self): self._ids = []
    def enqueue(self, task_id):
        if task_id not in self._ids: self._ids.append(task_id)
    def dequeue(self):
        return self._ids.pop(0) if self._ids else None
    def list(self): return tuple(self._ids)
