from __future__ import annotations

import logging
import threading
from datetime import datetime

from app.db.session import SessionLocal
from app.services.github_health_check import (
    get_health_check_config,
    get_next_cron_run,
    parse_proxy_pool_text,
    perform_github_health_check,
)

logger = logging.getLogger(__name__)

_scheduler_lock = threading.Lock()
_scheduler_thread: threading.Thread | None = None
_stop_event: threading.Event | None = None


def start_github_health_scheduler() -> None:
    global _scheduler_thread, _stop_event
    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return
        _stop_event = threading.Event()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(_stop_event,),
            name="github-health-scheduler",
            daemon=True,
        )
        _scheduler_thread.start()


def stop_github_health_scheduler() -> None:
    global _scheduler_thread, _stop_event
    with _scheduler_lock:
        if _stop_event:
            _stop_event.set()
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_thread.join(timeout=3)
        _scheduler_thread = None
        _stop_event = None


def _scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(15):
        try:
            _run_due_health_check()
        except Exception:
            logger.exception("GitHub health scheduler tick failed")


def _run_due_health_check() -> None:
    db = SessionLocal()
    try:
        config = get_health_check_config(db, create=False)
        if not config or not config.enabled:
            return

        due_at = config.next_run_at.astimezone() if config.next_run_at else None
        current = datetime.now().astimezone()
        if config.next_run_at is None:
            config.next_run_at = get_next_cron_run(config.cron_expression, current)
            db.commit()
            return
        if due_at and due_at > current:
            return

        config.last_run_at = current
        config.next_run_at = get_next_cron_run(config.cron_expression, current)
        db.commit()

        result = perform_github_health_check(
            db,
            proxy_urls=parse_proxy_pool_text(config.proxy_pool),
            accounts_per_proxy=config.accounts_per_proxy,
            timeout_seconds=config.timeout_seconds,
            source="scheduler",
            current_user_id=None,
        )
        config = get_health_check_config(db, create=False)
        if config:
            config.last_run_at = current
            config.last_batch_no = result["batch_no"]
            config.next_run_at = get_next_cron_run(config.cron_expression, current)
        db.commit()
    finally:
        db.close()
