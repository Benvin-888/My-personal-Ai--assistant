"""
APEX / BENVIN Deriv Live Tick Stream

Phase 2.6.4 - Live Deriv Tick Streaming

Responsibilities:
    1. Maintain a dedicated public Deriv WebSocket subscription.
    2. Normalize and validate incoming tick messages.
    3. Deduplicate exact repeated ticks.
    4. Protect completed point-in-time candle state from late ticks.
    5. Reconnect with bounded exponential backoff after transport failure.
    6. Send periodic Deriv ping messages to keep the connection alive.
    7. Support graceful shutdown without emitting an incomplete candle.
    8. Optionally emit deterministic completed candles through the existing
       Phase 2.6.3 tick-to-OHLC builder.

This module deliberately does NOT:
    - authenticate accounts
    - read balances or portfolios
    - place or close trades
    - select strategies
    - calculate position size
    - make trading decisions
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque

from .deriv import DerivProviderError, DerivWebSocketProvider
from .live_ticks import LiveTick, StreamEvent, utc_now
from .models import Candle
from .tick_ohlc import SUPPORTED_TICK_OHLC_INTERVALS


PROVIDER_NAME = "Deriv"
DEFAULT_PING_INTERVAL = 30.0
DEFAULT_RECONNECT_BASE_DELAY = 1.0
DEFAULT_RECONNECT_MAX_DELAY = 30.0
DEFAULT_MAX_RECONNECT_ATTEMPTS = 5
DEFAULT_QUEUE_SIZE = 1000


class DerivStreamError(RuntimeError):
    """Raised for invalid or unrecoverable live-stream conditions."""


class _IncrementalCandleBuilder:
    """Incremental UTC OHLC builder that emits only completed buckets."""

    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self._bucket: int | None = None
        self._ticks: list[tuple[int, int, float]] = []

    def bucket_start(self, timestamp: int) -> int:
        return (timestamp // self.interval_seconds) * self.interval_seconds

    def add_tick(self, *, timestamp: int, price: float, sequence: int) -> Candle | None:
        bucket = self.bucket_start(timestamp)
        completed = None
        if self._bucket is None:
            self._bucket = bucket
        elif bucket != self._bucket:
            completed = self._finalize()
            self._bucket = bucket
            self._ticks = []
        self._ticks.append((timestamp, sequence, price))
        return completed

    def _finalize(self) -> Candle | None:
        if self._bucket is None or not self._ticks:
            return None
        ordered = sorted(self._ticks, key=lambda item: (item[0], item[1]))
        prices = [item[2] for item in ordered]
        timestamp = self._bucket
        timestamp_utc = datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
        return Candle(
            timestamp=timestamp,
            timestamp_utc=timestamp_utc,
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=None,
        )


class DerivTickStream:
    """Thread-safe, reconnecting, read-only Deriv tick subscription."""

    def __init__(
        self,
        provider_symbol: str,
        *,
        endpoint: str = "wss://ws.derivws.com/websockets/v3",
        app_id: str = "1089",
        timeout: int | float = 15,
        connection_factory: Callable[..., Any] | None = None,
        ping_interval: int | float = DEFAULT_PING_INTERVAL,
        reconnect_base_delay: int | float = DEFAULT_RECONNECT_BASE_DELAY,
        reconnect_max_delay: int | float = DEFAULT_RECONNECT_MAX_DELAY,
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        on_tick: Callable[[LiveTick], None] | None = None,
        on_candle: Callable[[dict[str, Any]], None] | None = None,
        on_event: Callable[[StreamEvent], None] | None = None,
        candle_interval: str = "1m",
    ):
        if not isinstance(provider_symbol, str) or not provider_symbol.strip():
            raise ValueError("provider_symbol must be a non-empty string.")
        if not isinstance(ping_interval, (int, float)) or ping_interval <= 0:
            raise ValueError("ping_interval must be positive.")
        if not isinstance(reconnect_base_delay, (int, float)) or reconnect_base_delay <= 0:
            raise ValueError("reconnect_base_delay must be positive.")
        if not isinstance(reconnect_max_delay, (int, float)) or reconnect_max_delay < reconnect_base_delay:
            raise ValueError("reconnect_max_delay must be >= reconnect_base_delay.")
        if not isinstance(max_reconnect_attempts, int) or isinstance(max_reconnect_attempts, bool) or max_reconnect_attempts < 0:
            raise ValueError("max_reconnect_attempts must be a non-negative integer.")
        if not isinstance(queue_size, int) or isinstance(queue_size, bool) or queue_size <= 0:
            raise ValueError("queue_size must be a positive integer.")

        self.provider_symbol = provider_symbol.strip()
        self.endpoint = endpoint.rstrip("/")
        self.app_id = app_id
        self.timeout = timeout
        self.connection_factory = connection_factory
        self.ping_interval = float(ping_interval)
        self.reconnect_base_delay = float(reconnect_base_delay)
        self.reconnect_max_delay = float(reconnect_max_delay)
        self.max_reconnect_attempts = max_reconnect_attempts
        self.candle_interval = candle_interval
        self.on_tick = on_tick
        self.on_candle = on_candle
        self.on_event = on_event

        self._queue: Deque[LiveTick] = deque(maxlen=queue_size)
        self._queue_condition = threading.Condition()
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._connection: Any | None = None
        self._ping_thread: threading.Thread | None = None
        self._sequence = 0
        self._seen_tick_keys: set[tuple[Any, ...]] = set()
        self._seen_tick_order: Deque[tuple[Any, ...]] = deque(maxlen=queue_size)
        self._last_tick_timestamp: int | None = None
        self._last_emitted_bucket: int | None = None
        self._running = False
        self._reconnect_attempt = 0
        self._dropped_duplicates = 0
        self._dropped_late_ticks = 0
        self._dropped_queue_ticks = 0
        self._last_received_at: str | None = None
        self._last_error: str | None = None

        interval_seconds = SUPPORTED_TICK_OHLC_INTERVALS.get(candle_interval)
        if interval_seconds is None:
            supported = ", ".join(SUPPORTED_TICK_OHLC_INTERVALS)
            raise ValueError(
                f"Unsupported candle interval '{candle_interval}'. Supported: {supported}."
            )
        self._candle_builder = _IncrementalCandleBuilder(interval_seconds)

    @staticmethod
    def _timestamp_to_utc(epoch: int) -> str:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _coerce_epoch(value: Any) -> int:
        if isinstance(value, bool):
            raise DerivStreamError("Deriv tick epoch must be numeric.")
        try:
            epoch = int(float(value))
        except (TypeError, ValueError) as exc:
            raise DerivStreamError("Deriv tick epoch is invalid.") from exc
        if epoch <= 0:
            raise DerivStreamError("Deriv tick epoch must be positive.")
        return epoch

    @staticmethod
    def _coerce_price(value: Any) -> float:
        if isinstance(value, bool):
            raise DerivStreamError("Deriv tick quote must be numeric.")
        try:
            price = float(value)
        except (TypeError, ValueError) as exc:
            raise DerivStreamError("Deriv tick quote is invalid.") from exc
        if price <= 0:
            raise DerivStreamError("Deriv tick quote must be positive.")
        return price

    def _connection_url(self) -> str:
        separator = "&" if "?" in self.endpoint else "?"
        return f"{self.endpoint}{separator}app_id={self.app_id}"

    def _default_connection_factory(self):
        try:
            import websocket
        except ImportError as exc:
            raise DerivStreamError(
                "Deriv live streaming requires 'websocket-client'. "
                "Install it with: pip install websocket-client"
            ) from exc
        return websocket.create_connection

    def _emit_event(self, event_type: str, *, error: str | None = None, details: dict[str, Any] | None = None) -> None:
        if self.on_event is None:
            return
        event = StreamEvent(
            event_type=event_type,
            provider=PROVIDER_NAME,
            provider_symbol=self.provider_symbol,
            occurred_at=utc_now(),
            reconnect_attempt=self._reconnect_attempt,
            error=error,
            details=details,
        )
        try:
            self.on_event(event)
        except Exception:
            # Observers must never be able to kill the market stream.
            pass

    def _connect(self) -> Any:
        factory = self.connection_factory or self._default_connection_factory()
        connection = factory(self._connection_url(), timeout=self.timeout)
        connection.send(json.dumps({
            "ticks": self.provider_symbol,
            "subscribe": 1,
        }))
        self._emit_event("connected")
        self._emit_event("subscribed", details={"provider_symbol": self.provider_symbol})
        return connection

    @staticmethod
    def _is_socket_timeout(exc: BaseException) -> bool:
        name = exc.__class__.__name__.lower()
        if "timeout" in name:
            return True
        try:
            import websocket
            timeout_type = getattr(websocket, "WebSocketTimeoutException", None)
            return timeout_type is not None and isinstance(exc, timeout_type)
        except Exception:
            return False

    def _ping_loop(self, connection: Any) -> None:
        while not self._stop_event.wait(self.ping_interval):
            try:
                connection.send(json.dumps({"ping": 1}))
            except Exception as exc:
                self._last_error = str(exc)
                return

    def _start_ping_thread(self, connection: Any) -> None:
        thread = threading.Thread(
            target=self._ping_loop,
            args=(connection,),
            name="deriv-tick-stream-ping",
            daemon=True,
        )
        self._ping_thread = thread
        thread.start()

    def _close_connection(self) -> None:
        with self._state_lock:
            connection = self._connection
            self._connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _tick_key(self, tick: dict[str, Any], epoch: int, price: float) -> tuple[Any, ...]:
        tick_id = tick.get("id")
        if isinstance(tick_id, str) and tick_id:
            return (self.provider_symbol, "id", tick_id)
        return (self.provider_symbol, epoch, price)

    def _normalize_tick(self, response: dict[str, Any]) -> LiveTick | None:
        if response.get("msg_type") != "tick":
            if response.get("error"):
                error = response.get("error")
                message = error.get("message", "Unknown Deriv error.") if isinstance(error, dict) else str(error)
                raise DerivStreamError(message)
            return None

        tick = response.get("tick")
        if not isinstance(tick, dict):
            raise DerivStreamError("Deriv tick response did not contain a tick object.")

        epoch = self._coerce_epoch(tick.get("epoch"))
        price = self._coerce_price(tick.get("quote"))
        key = self._tick_key(tick, epoch, price)

        if key in self._seen_tick_keys:
            self._dropped_duplicates += 1
            return None
        self._seen_tick_keys.add(key)
        self._seen_tick_order.append(key)
        if len(self._seen_tick_keys) > self._seen_tick_order.maxlen:
            self._seen_tick_keys = set(self._seen_tick_order)

        sequence = self._sequence + 1
        self._sequence = sequence
        self._last_received_at = utc_now()

        return LiveTick(
            timestamp=epoch,
            timestamp_utc=self._timestamp_to_utc(epoch),
            price=price,
            provider=PROVIDER_NAME,
            provider_symbol=self.provider_symbol,
            raw_tick=dict(tick),
            received_at=self._last_received_at,
            sequence=sequence,
        )

    def _bucket_start(self, timestamp: int) -> int:
        return self._candle_builder.bucket_start(timestamp)

    def _handle_tick(self, live_tick: LiveTick) -> None:
        bucket = self._bucket_start(live_tick.timestamp)
        if self._last_emitted_bucket is not None and bucket <= self._last_emitted_bucket:
            self._dropped_late_ticks += 1
            return

        if self._last_tick_timestamp is not None and live_tick.timestamp < self._last_tick_timestamp:
            self._emit_event(
                "out_of_order_tick",
                details={
                    "tick_timestamp": live_tick.timestamp,
                    "last_tick_timestamp": self._last_tick_timestamp,
                },
            )
        self._last_tick_timestamp = max(self._last_tick_timestamp or live_tick.timestamp, live_tick.timestamp)

        previous = self._candle_builder.add_tick(
            timestamp=live_tick.timestamp,
            price=live_tick.price,
            sequence=live_tick.sequence,
        )

        if previous is not None:
            candle_dict = previous.to_dict()
            completed_bucket = int(candle_dict["timestamp"])
            if self._last_emitted_bucket is not None and completed_bucket <= self._last_emitted_bucket:
                return
            self._last_emitted_bucket = completed_bucket
            if self.on_candle is not None:
                try:
                    self.on_candle(candle_dict)
                except Exception:
                    pass
            self._emit_event("candle_completed", details={"candle": candle_dict})

        if self.on_tick is not None:
            try:
                self.on_tick(live_tick)
            except Exception:
                pass

        with self._queue_condition:
            before = len(self._queue)
            self._queue.append(live_tick)
            if before == self._queue.maxlen:
                self._dropped_queue_ticks += 1
            self._queue_condition.notify_all()

    def _backoff_delay(self, attempt: int) -> float:
        return min(
            self.reconnect_max_delay,
            self.reconnect_base_delay * (2 ** max(0, attempt - 1)),
        )

    def run(self) -> dict[str, Any]:
        """Run until stopped or reconnect attempts are exhausted."""
        with self._state_lock:
            if self._running:
                raise DerivStreamError("The live stream is already running.")
            self._running = True

        self._stop_event.clear()
        self._emit_event("starting")

        try:
            while not self._stop_event.is_set():
                connection = None
                try:
                    connection = self._connect()
                    with self._state_lock:
                        self._connection = connection
                    self._reconnect_attempt = 0
                    self._last_error = None
                    self._start_ping_thread(connection)

                    while not self._stop_event.is_set():
                        try:
                            raw = connection.recv()
                        except Exception as exc:
                            if self._is_socket_timeout(exc):
                                continue
                            raise
                        if raw is None:
                            raise DerivStreamError("Deriv WebSocket returned no message.")
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        response = json.loads(raw)
                        if not isinstance(response, dict):
                            raise DerivStreamError("Deriv returned an invalid stream response.")
                        live_tick = self._normalize_tick(response)
                        if live_tick is not None:
                            self._handle_tick(live_tick)

                except Exception as exc:
                    if self._stop_event.is_set():
                        break
                    self._last_error = str(exc)
                    self._emit_event("connection_error", error=str(exc))
                    self._close_connection()
                    self._reconnect_attempt += 1
                    if self._reconnect_attempt > self.max_reconnect_attempts:
                        self._emit_event("stopped", error=str(exc), details={"reason": "reconnect_limit_exhausted"})
                        raise DerivStreamError(
                            f"Deriv live stream stopped after {self.max_reconnect_attempts} reconnect attempts: {exc}"
                        ) from exc
                    delay = self._backoff_delay(self._reconnect_attempt)
                    self._emit_event("reconnecting", details={"delay_seconds": delay})
                    if self._stop_event.wait(delay):
                        break
                finally:
                    if connection is not None:
                        try:
                            connection.close()
                        except Exception:
                            pass
                    with self._state_lock:
                        if self._connection is connection:
                            self._connection = None

            self._emit_event("stopped", details={"reason": "requested"})
            return self.stats()
        finally:
            self._stop_event.set()
            self._close_connection()
            with self._state_lock:
                self._running = False

    def stop(self) -> None:
        """Request graceful shutdown; the current candle remains uncompleted."""
        self._stop_event.set()
        self._close_connection()
        with self._queue_condition:
            self._queue_condition.notify_all()

    def get_tick(self, timeout: int | float | None = None) -> LiveTick | None:
        """Retrieve the next normalized tick from the bounded local queue."""
        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout < 0):
            raise ValueError("timeout must be non-negative when provided.")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._queue_condition:
            while not self._queue:
                if self._stop_event.is_set():
                    return None
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._queue_condition.wait(remaining)
            return self._queue.popleft()

    def stats(self) -> dict[str, Any]:
        with self._state_lock:
            running = self._running
        with self._queue_condition:
            queued = len(self._queue)
        return {
            "provider": PROVIDER_NAME,
            "provider_symbol": self.provider_symbol,
            "running": running,
            "sequence": self._sequence,
            "queued_ticks": queued,
            "dropped_duplicates": self._dropped_duplicates,
            "dropped_late_ticks": self._dropped_late_ticks,
            "dropped_queue_ticks": self._dropped_queue_ticks,
            "reconnect_attempt": self._reconnect_attempt,
            "last_received_at": self._last_received_at,
            "last_error": self._last_error,
        }

    def __enter__(self) -> "DerivTickStream":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
