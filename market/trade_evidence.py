"""Phase 2.44 trade evidence contracts.

Stores evidence about decisions. This module has no execution authority.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeEvidence:
    trade_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: str
    regime: str
    session: str
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "session": self.session,
            "evidence_fingerprint": self.evidence_fingerprint,
        }
