"""Tests for Phase 2.6.4 live Deriv tick streaming."""

from __future__ import annotations

import json
import threading
import time

import pytest

from market.deriv_stream import DerivStreamError, DerivTickStream
from market.live_ticks import LiveTick


class FakeConnection:
    def __init__(self, messages, *, fail_after=None):
        self.messages = list(messages)
        self.fail_after = fail_after
        self.sent = []
        self.closed = False
        self.recv_count = 0

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        if self.closed:
            raise RuntimeError("closed")
        if self.fail_after is not None and self.recv_count >= self.fail_after:
            raise RuntimeError("simulated connection failure")
        if not self.messages:
            raise RuntimeError("end of fake stream")
        self.recv_count += 1
        message = self.messages.pop(0)
        if isinstance(message, BaseException):
            raise message
        return json.dumps(message)

    def close(self):
        self.closed = True


def tick(epoch, quote, *, tick_id=None, symbol="frxEURUSD"):
    data = {
        "msg_type": "tick",
        "tick": {
            "epoch": epoch,
            "quote": quote,
            "symbol": symbol,
        },
    }
    if tick_id is not None:
        data["tick"]["id"] = tick_id
    return data


def test_normalizes_tick_and_subscribes():
    connection = FakeConnection([tick(1_700_000_000, 1.1, tick_id="a")])
    stream = DerivTickStream("frxEURUSD", connection_factory=lambda *a, **k: connection)
    normalized = stream._normalize_tick(tick(1_700_000_000, 1.1, tick_id="a"))

    assert isinstance(normalized, LiveTick)
    assert normalized.price == 1.1
    assert normalized.provider == "Deriv"


def test_duplicate_tick_is_dropped():
    stream = DerivTickStream("frxEURUSD")
    first = stream._normalize_tick(tick(1_700_000_000, 1.1, tick_id="a"))
    second = stream._normalize_tick(tick(1_700_000_000, 1.1, tick_id="a"))

    assert first is not None
    assert second is None
    assert stream.stats()["dropped_duplicates"] == 1


def test_completed_candle_emitted_only_when_bucket_changes():
    candles = []
    stream = DerivTickStream("frxEURUSD", candle_interval="1m", on_candle=candles.append)

    stream._handle_tick(stream._normalize_tick(tick(1_700_000_000, 1.10)) )
    assert candles == []
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_060, 1.20)) )

    assert len(candles) == 1
    assert candles[0]["open"] == 1.10
    assert candles[0]["close"] == 1.10


def test_late_tick_cannot_mutate_completed_candle():
    candles = []
    stream = DerivTickStream("frxEURUSD", candle_interval="1m", on_candle=candles.append)

    stream._handle_tick(stream._normalize_tick(tick(1_700_000_000, 1.10)))
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_060, 1.20)))
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_001, 9.99)))

    assert len(candles) == 1
    assert candles[0]["high"] == 1.10
    assert stream.stats()["dropped_late_ticks"] == 1


def test_out_of_order_tick_within_uncompleted_bucket_is_accepted():
    stream = DerivTickStream("frxEURUSD", candle_interval="1m")
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_050, 1.20)))
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_010, 1.10)))

    assert stream.stats()["dropped_late_ticks"] == 0


def test_queue_is_bounded():
    stream = DerivTickStream("frxEURUSD", queue_size=2)
    for index in range(3):
        stream._handle_tick(stream._normalize_tick(tick(1_700_000_000 + index, 1.1 + index)))

    assert stream.stats()["queued_ticks"] == 2
    assert stream.stats()["dropped_queue_ticks"] == 1


def test_get_tick_reads_queue():
    stream = DerivTickStream("frxEURUSD")
    stream._handle_tick(stream._normalize_tick(tick(1_700_000_000, 1.1)))

    item = stream.get_tick(timeout=0)
    assert isinstance(item, LiveTick)
    assert stream.get_tick(timeout=0) is None


def test_invalid_tick_is_rejected():
    stream = DerivTickStream("frxEURUSD")
    with pytest.raises(DerivStreamError):
        stream._normalize_tick({"msg_type": "tick", "tick": {"epoch": 1, "quote": 0}})


def test_error_response_is_rejected():
    stream = DerivTickStream("frxEURUSD")
    with pytest.raises(DerivStreamError, match="Bad symbol"):
        stream._normalize_tick({"msg_type": "error", "error": {"message": "Bad symbol"}})


def test_ping_is_sent_by_ping_loop():
    connection = FakeConnection([])
    stream = DerivTickStream("frxEURUSD", ping_interval=0.01)
    stream._stop_event.clear()
    thread = threading.Thread(target=stream._ping_loop, args=(connection,))
    thread.start()
    time.sleep(0.04)
    stream.stop()
    thread.join(timeout=1)

    assert any(message.get("ping") == 1 for message in connection.sent)


def test_run_stops_cleanly_when_requested():
    connection = FakeConnection([tick(1_700_000_000, 1.1)])
    stream = DerivTickStream(
        "frxEURUSD",
        connection_factory=lambda *a, **k: connection,
        reconnect_base_delay=0.01,
        reconnect_max_delay=0.01,
    )

    result_holder = {}

    def runner():
        result_holder["result"] = stream.run()

    thread = threading.Thread(target=runner)
    thread.start()
    time.sleep(0.05)
    stream.stop()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert result_holder["result"]["provider"] == "Deriv"


def test_reconnects_after_connection_failure():
    connections = [
        FakeConnection([tick(1_700_000_000, 1.1)]),
        FakeConnection([tick(1_700_000_001, 1.2)]),
    ]
    created = []

    def factory(*args, **kwargs):
        if not connections:
            raise RuntimeError("no more connections")
        connection = connections.pop(0)
        created.append(connection)
        return connection

    stream = DerivTickStream(
        "frxEURUSD",
        connection_factory=factory,
        reconnect_base_delay=0.001,
        reconnect_max_delay=0.001,
        max_reconnect_attempts=1,
    )

    with pytest.raises(DerivStreamError):
        stream.run()

    assert len(created) == 2


def test_subscription_payload_uses_continuous_stream():
    connection = FakeConnection([tick(1_700_000_000, 1.1)])
    stream = DerivTickStream("frxEURUSD", connection_factory=lambda *a, **k: connection)

    def stopper(_):
        stream.stop()

    stream.on_tick = stopper
    stream.run()

    assert connection.sent[0] == {"ticks": "frxEURUSD", "subscribe": 1}


def test_context_manager_stops_stream():
    stream = DerivTickStream("frxEURUSD")
    with stream:
        assert stream._stop_event.is_set() is False
    assert stream._stop_event.is_set() is True


def test_socket_timeout_is_treated_as_nonfatal_read_timeout():
    stream = DerivTickStream("frxEURUSD")
    assert stream._is_socket_timeout(TimeoutError("read timed out")) is True


def test_out_of_order_ticks_produce_timestamp_ordered_open_and_close():
    candles = []
    stream = DerivTickStream("frxEURUSD", candle_interval="1m", on_candle=candles.append)
    base = (1_700_000_000 // 60) * 60
    stream._handle_tick(stream._normalize_tick(tick(base + 50, 1.20)))
    stream._handle_tick(stream._normalize_tick(tick(base + 10, 1.10)))
    stream._handle_tick(stream._normalize_tick(tick(base + 60, 1.30)))

    assert candles[0]["open"] == 1.10
    assert candles[0]["high"] == 1.20
    assert candles[0]["low"] == 1.10
    assert candles[0]["close"] == 1.20
