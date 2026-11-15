"""Startup warm-up: load everything the first analysis needs in a background thread, so the server
answers /health straight away (Render needs that) and the first /api/analyze doesn't pay for it.

Order: embedder (model files), search index (corpus + cached vectors), one dummy query embedding
(the first embed call is slow), classifier (saved file or training). Each part's time is logged.
If warm-up fails, requests still load what they need on first use; ready stays false."""
import logging
import threading
import time

from app.pipeline.classify import ensure_classifier
from app.pipeline.embed import get_embedder
from app.pipeline.retrieve import get_index

log = logging.getLogger("ticket-assistant")

_state = {"started": False, "ready": False}


def warm_up() -> None:
    total = time.perf_counter()
    try:
        t = time.perf_counter()
        embedder = get_embedder()
        log.info("warm-up: embedder %s loaded in %.1fs", embedder.name, time.perf_counter() - t)

        t = time.perf_counter()
        index = get_index()
        log.info("warm-up: search index ready in %.1fs (%d documents, vectors %s)", time.perf_counter() - t,
                 len(index.docs), "rebuilt" if index.vectors_rebuilt else "loaded from cache")

        t = time.perf_counter()
        embedder.embed(["warm up: vpn disconnects when working from home"])
        log.info("warm-up: first query embedded in %.1fs", time.perf_counter() - t)

        t = time.perf_counter()
        source = ensure_classifier()
        log.info("warm-up: classifier %s in %.1fs", source, time.perf_counter() - t)
    except Exception:
        log.exception("warm-up failed after %.1fs; requests will load what they need on first use",
                      time.perf_counter() - total)
        return
    _state["ready"] = True
    log.info("warm-up: ready in %.1fs", time.perf_counter() - total)


def start_warm_up() -> threading.Thread:
    _state["started"] = True
    thread = threading.Thread(target=warm_up, name="warm-up", daemon=True)
    thread.start()
    return thread


def warm_up_started() -> bool:
    return _state["started"]


def is_ready() -> bool:
    return _state["ready"]
