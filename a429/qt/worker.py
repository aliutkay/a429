"""AXIL Studio istekleri için tek iş parçacıklı worker (sonuçlar GUI thread'ine sinyalle döner)."""
from __future__ import annotations

import concurrent.futures

from PySide6.QtCore import QObject, Signal


class Worker(QObject):
    _done = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._closed = False
        self._done.connect(self._deliver)
        self.pending = 0

    def _emit_done(self, fut, ok, err):
        if self._closed:
            return
        try:
            self._done.emit(fut, ok, err)
        except RuntimeError:
            pass

    def run(self, fn, ok=None, err=None):
        if self._closed:
            return
        self.pending += 1
        fut = self._pool.submit(fn)
        fut.add_done_callback(lambda f: self._emit_done(f, ok, err))

    def _deliver(self, fut, ok, err):
        self.pending -= 1
        if self._closed or fut.cancelled():
            return
        exc = fut.exception()
        if exc is not None:
            if err:
                err(exc)
        elif ok:
            ok(fut.result())

    def shutdown(self):
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
