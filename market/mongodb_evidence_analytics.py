"""Deterministic performance analytics over persisted APEX trade evidence."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .mongodb_evidence_query import MongoTradeEvidenceQuery


@dataclass(frozen=True)
class TradeEvidencePerformanceSummary:
    """Read-only aggregate metrics derived from trade evidence."""

    total_records: int
    status_counts: dict[str, int]
    symbols: dict[str, int]
    pnl_records: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    total_pnl: float | None
    gross_profit: float | None
    gross_loss: float | None
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None


def _numeric_pnl(document: Mapping[str, Any]) -> float | None:
    """Return a finite realized P&L value when evidence explicitly provides one."""
    value = document.get("realized_pnl")
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def summarize_trade_evidence(
    query: MongoTradeEvidenceQuery,
    filters: Mapping[str, Any] | None = None,
) -> TradeEvidencePerformanceSummary:
    """Build deterministic, read-only performance aggregates from trade evidence.

    ``realized_pnl`` is intentionally optional. Records without a finite numeric
    value are retained in record/status counts but excluded from P&L statistics.
    No trade is inferred to be profitable from status alone.
    """
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping or None")
    records = query.find(filters)

    status_counts: dict[str, int] = {}
    symbols: dict[str, int] = {}
    pnls: list[float] = []
    for document in records:
        status = str(document.get("status", "")).strip()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        symbol = str(document.get("symbol", "")).strip()
        if symbol:
            symbols[symbol] = symbols.get(symbol, 0) + 1
        pnl = _numeric_pnl(document)
        if pnl is not None:
            pnls.append(pnl)

    winners = sum(1 for value in pnls if value > 0)
    losers = sum(1 for value in pnls if value < 0)
    breakeven = sum(1 for value in pnls if value == 0)
    total_pnl = sum(pnls) if pnls else None
    gross_profit = sum(value for value in pnls if value > 0) if pnls else None
    gross_loss = sum(value for value in pnls if value < 0) if pnls else None
    win_rate = winners / len(pnls) if pnls else None
    if gross_loss is not None and gross_loss < 0:
        profit_factor = gross_profit / abs(gross_loss) if gross_profit is not None else None
    else:
        profit_factor = None
    expectancy = total_pnl / len(pnls) if pnls else None

    return TradeEvidencePerformanceSummary(
        total_records=len(records),
        status_counts=status_counts,
        symbols=symbols,
        pnl_records=len(pnls),
        winning_trades=winners,
        losing_trades=losers,
        breakeven_trades=breakeven,
        total_pnl=total_pnl,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
    )
