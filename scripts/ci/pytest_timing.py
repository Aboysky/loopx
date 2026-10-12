"""Stream pytest-owned timings from the controller, including interrupted runs.

This is a CI observation adapter, not a splitter, timing cache or test gate.
Load explicitly with ``-p scripts.ci.pytest_timing``. No configuration or test
selection changes; node ids and phase/outcome values come from pytest itself.
"""
from __future__ import annotations

import json
import hashlib
import math
import time

import pytest


PREFIX = "LOOPX_PYTEST_TIMING "


def pytest_configure(config):
    # xdist sends TestReports to the controller. Worker output would duplicate
    # reports and can be lost when a worker is killed.
    if not hasattr(config, "workerinput"):
        config.pluginmanager.register(TimingObserver(config), "loopx-ci-timing-observer")


class TimingObserver:
    def __init__(self, config):
        self.config = config
        self.started = time.perf_counter()
        self.collection = None

    def emit(self, **row):
        row["elapsed_seconds"] = round(time.perf_counter() - self.started, 6)
        line = PREFIX + json.dumps(row, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.ensure_newline()
            reporter.write_line(line)
            reporter._tw.flush()

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session):
        self.emit(event="start", version=1)

    def record_collection(self, ids):
        if self.collection is None:
            self.collection = tuple(ids)
            self.emit(event="collection", selected=len(ids))
        elif self.collection != tuple(ids):
            # xdist owns rejecting different worker collections. Preserve the
            # observation without changing that decision or claiming coverage.
            self.emit(event="collection_mismatch")

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node, ids):
        self.record_collection(ids)

    def pytest_collection_finish(self, session):
        if not getattr(self.config.option, "numprocesses", None):
            self.record_collection([item.nodeid for item in session.items])

    def pytest_runtest_logreport(self, report):
        duration = report.duration
        # Parameter ids can contain tens of thousands of characters. Preserve
        # exact identity without repeating that payload for every phase.
        self.emit(event="phase", test_id=hashlib.sha256(
            report.nodeid.encode("utf-8", errors="surrogatepass")).hexdigest(),
                  display_nodeid=report.nodeid[:256], phase=report.when,
                  outcome=report.outcome,
                  seconds=duration if math.isfinite(duration) and duration >= 0 else None)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        self.emit(event="end", exit_code=int(session.exitstatus))
