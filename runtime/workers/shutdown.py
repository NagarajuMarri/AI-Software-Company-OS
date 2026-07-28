import signal
from threading import Event


class ShutdownController:
    def __init__(self):
        self._event = Event()
        self._previous = {}

    @property
    def requested(self): return self._event.is_set()
    def request(self, *_): self._event.set()

    def install(self):
        for name in ("SIGINT", "SIGTERM"):
            value = getattr(signal, name, None)
            if value is not None:
                self._previous[value] = signal.getsignal(value)
                signal.signal(value, self.request)

    def restore(self):
        for value, handler in self._previous.items():
            signal.signal(value, handler)
        self._previous.clear()
