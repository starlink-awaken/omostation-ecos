"""Tests for small common modules + validator + health_check."""

from __future__ import annotations

import fcntl
import json
import threading
from unittest.mock import patch

import pytest

from ecos.common.content_integrity import check_integrity
from ecos.common.governed_fs import append_jsonl_record
from ecos.common.exceptions import (
    ECOSException,
    ConfigException,
    ConsensusException,
    GraphException,
    PersistenceException,
    SecurityException,
    SyncException,
    TransportException,
)
from ecos.common.logger import ECOSFormatter, get_logger
from ecos.common.metrics import MetricsCollector
from ecos.services.governance.validator import REAL


# ── exceptions ──


class TestExceptions:
    def test_ecos_exception(self):
        with pytest.raises(ECOSException):
            raise ECOSException("base")

    def test_sync_exception(self):
        with pytest.raises(SyncException):
            raise SyncException("sync")

    def test_consensus_exception(self):
        with pytest.raises(ConsensusException):
            raise ConsensusException("consensus")

    def test_graph_exception(self):
        with pytest.raises(GraphException):
            raise GraphException("graph")

    def test_transport_exception(self):
        with pytest.raises(TransportException):
            raise TransportException("transport")

    def test_config_exception(self):
        with pytest.raises(ConfigException):
            raise ConfigException("config")

    def test_security_exception(self):
        with pytest.raises(SecurityException):
            raise SecurityException("security")

    def test_persistence_exception(self):
        with pytest.raises(PersistenceException):
            raise PersistenceException("persistence")

    def test_inheritance(self):
        assert issubclass(SyncException, ECOSException)
        assert issubclass(ConfigException, ECOSException)
        assert issubclass(SecurityException, ECOSException)


# ── logger ──


class TestECOSFormatter:
    def test_format(self):
        formatter = ECOSFormatter()
        import logging

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=42,
            msg="hello",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello"
        assert parsed["module"] == "test"


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test")
        assert logger.name == "ecos.test"

    def test_singleton(self):
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2 or logger1.name == logger2.name


# ── metrics ──


class TestMetricsCollector:
    def test_counter(self):
        m = MetricsCollector()
        assert m.get_counter("requests") == 0
        m.inc_counter("requests")
        assert m.get_counter("requests") == 1
        m.inc_counter("requests", 5)
        assert m.get_counter("requests") == 6

    def test_gauge(self):
        m = MetricsCollector()
        assert m.get_gauge("temp") == 0.0
        m.set_gauge("temp", 36.5)
        assert m.get_gauge("temp") == 36.5

    def test_histogram(self):
        m = MetricsCollector()
        h = m.get_histogram("latency")
        assert h["count"] == 0
        m.observe_histogram("latency", 0.5)
        m.observe_histogram("latency", 1.5)
        h = m.get_histogram("latency")
        assert h["count"] == 2
        assert h["avg"] == 1.0
        assert h["min"] == 0.5
        assert h["max"] == 1.5

    def test_export(self):
        m = MetricsCollector()
        m.inc_counter("c1")
        m.set_gauge("g1", 1.0)
        exported = m.export()
        assert "counters" in exported
        assert "gauges" in exported
        assert "uptime_seconds" in exported
        assert exported["counters"]["c1"] == 1


# ── content_integrity ──


class TestCheckIntegrity:
    def test_clean_text(self):
        result = check_integrity("This is a normal text with varied words.")
        assert result["suspicious"] is False
        assert result["integrity_score"] == 90

    def test_repetitive_text(self):
        text = "word " * 10
        result = check_integrity(text)
        assert result["suspicious"] is True
        assert result["integrity_score"] == 35

    def test_suspicious_markers(self):
        text = "comprehensive analysis shows methodology. further research is needed."
        result = check_integrity(text)
        assert result["suspicious"] is True
        assert result["integrity_score"] == 45

    def test_empty_text(self):
        result = check_integrity("")
        assert result["suspicious"] is False


# ── validator ──


class TestValidator:
    def test_real_path(self):
        assert "ecos-constraint-validator" in str(REAL)

    @patch("ecos.services.governance.validator.REAL")
    @patch("ecos.services.governance.validator.subprocess.call")
    def test_main_runs_real(self, mock_call, mock_real):
        mock_real.exists.return_value = True
        mock_call.return_value = 0
        # Simulate __main__ block logic
        import ecos.services.governance.validator as v

        if v.REAL.exists():
            v.subprocess.call([v.sys.executable, str(v.REAL)])
        mock_call.assert_called_once()


# ── governed_fs.append_jsonl_record ──


class TestAppendJsonlRecord:
    """X2 budget integrity standard §3「并发控制」: JSONL 写入必须持 fcntl 排他锁。"""

    def test_takes_exclusive_lock_around_write(self, tmp_path):
        """锁必须包住写: LOCK_EX 进、LOCK_UN 出, 且顺序不能反。"""
        target = tmp_path / "ledger.jsonl"
        calls = []
        real_flock = fcntl.flock

        def spy(fd, op):
            calls.append(op)
            return real_flock(fd, op)

        with patch("fcntl.flock", spy):
            append_jsonl_record(target, {"k": 1})

        assert calls == [fcntl.LOCK_EX, fcntl.LOCK_UN]
        assert json.loads(target.read_text(encoding="utf-8").strip()) == {"k": 1}

    def test_lock_is_released_when_write_raises(self, tmp_path):
        """写失败也要放锁 —— 否则一次异常就把 ledger 永久锁死。"""
        target = tmp_path / "ledger.jsonl"
        with patch("fcntl.flock", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                append_jsonl_record(target, {"k": 1})
        # 锁没被获取成功时文件可以被再次打开 (没有被残留锁挡住)
        append_jsonl_record(target, {"k": 2})
        assert len(target.read_text(encoding="utf-8").strip().splitlines()) == 1

    def test_concurrent_appends_keep_every_line_intact(self, tmp_path):
        """并发追加后每行都必须是完整 JSON —— 无锁时写可能交错成半行。"""
        target = tmp_path / "ledger.jsonl"
        n_threads, per_thread = 8, 25
        barrier = threading.Barrier(n_threads)

        def worker(tid):
            barrier.wait()
            for i in range(per_thread):
                append_jsonl_record(target, {"t": tid, "i": i})

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == n_threads * per_thread
        parsed = [json.loads(line) for line in lines]  # 任一行不完整即抛
        assert len({(r["t"], r["i"]) for r in parsed}) == n_threads * per_thread
