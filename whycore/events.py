"""In-process event bus for the live view (GET /events, Server-Sent Events).

Publishers: the ledger (every step), whycore.data (every query), whycore.model (every model answer), the pipeline
(signals, verdicts, run done). Subscribers: one bounded queue per open /events connection. Publishing never blocks and
never raises; a slow or closed subscriber just drops events. Events carry `run_id` when the publisher knows it."""
from __future__ import annotations
import queue, threading, time

_subs: list[queue.Queue] = []
_lock = threading.Lock()
_seq = 0


def subscribe(maxsize: int = 2000) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    with _lock:
        _subs.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subs:
            _subs.remove(q)


def publish(type_: str, **fields) -> None:
    global _seq
    with _lock:
        _seq += 1
        ev = {"seq": _seq, "t": round(time.time(), 3), "type": type_, **fields}
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait(ev)
        except queue.Full:
            pass


def subscribers() -> int:
    with _lock:
        return len(_subs)
