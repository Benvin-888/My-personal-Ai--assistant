"""Phase 2.43 Brain market analysis explanation contracts."""

from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(frozen=True)
class MarketExplanation:
    """Human-facing explanation generated from deterministic market evidence."""

    symbol: str
    timeframe: str
    regime: str
    session: str
    opportunity_state: str
    evidence_fingerprint: str
    supporting_factors: tuple[str, ...]
    caution_factors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "session": self.session,
            "opportunity_state": self.opportunity_state,
            "evidence_fingerprint": self.evidence_fingerprint,
            "supporting_factors": list(self.supporting_factors),
            "caution_factors": list(self.caution_factors),
        }


def explain_market_snapshot(snapshot: Mapping[str, Any]) -> MarketExplanation:
    """Convert deterministic market evidence into an explanation object.

    This layer explains evidence only. It cannot authorize or execute trades.
    """

    return MarketExplanation(
        symbol=str(snapshot.get("symbol", "")),
        timeframe=str(snapshot.get("timeframe", "")),
        regime=str(snapshot.get("regime", "unknown")),
        session=str(snapshot.get("session", "unknown")),
        opportunity_state=str(snapshot.get("opportunity_state", "unknown")),
        evidence_fingerprint=str(snapshot.get("evidence_fingerprint", "")),
        supporting_factors=tuple(snapshot.get("supporting_factors", ())),
        caution_factors=tuple(snapshot.get("caution_factors", ())),
    )
