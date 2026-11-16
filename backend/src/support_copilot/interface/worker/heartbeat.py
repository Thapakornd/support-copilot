"""Independent, bounded lease renewal; uncertainty means ownership is lost."""

from threading import Event, Thread


class Heartbeat:
    def __init__(self, store, job, interval):
        self.store = store
        self.job = job
        self.interval = interval
        self.lost = Event()
        self.done = Event()
        self.thread = Thread(target=self._run, daemon=True, name="embedding-heartbeat")

    def _run(self):
        while not self.done.wait(self.interval):
            try:
                if not self.store.renew(self.job):
                    self.lost.set()
                    return
            except Exception:  # noqa: BLE001 -- no exception text may escape the worker
                self.lost.set()
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.done.set()
        self.thread.join(timeout=0.2)
