"""Checkpointer for pause / review / resume. SQLite under CHECKPOINT_DIR (the compose volume /data/checkpoints), so a
paused run survives a restart of the agents container. Memory fallback when the directory cannot be created or
CHECKPOINTER=memory (tests); the trace says so because a paused run then dies with the process."""
from __future__ import annotations
import logging, os, sqlite3
from langgraph.checkpoint.memory import MemorySaver
from floodsense_agents.settings import settings

log = logging.getLogger("floodsense.checkpoints")


def build_checkpointer():
    if settings.checkpointer == "memory":
        return MemorySaver()
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        os.makedirs(settings.checkpoint_dir, exist_ok=True)
        path = os.path.join(settings.checkpoint_dir, "floodsense.sqlite")
        conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        log.info("checkpointer: sqlite %s", path)
        return saver
    except Exception as e:
        if settings.checkpointer == "sqlite":
            raise
        log.warning("checkpointer: sqlite unavailable (%s) -> MemorySaver; paused runs will not survive a restart", str(e)[:120])
        return MemorySaver()
