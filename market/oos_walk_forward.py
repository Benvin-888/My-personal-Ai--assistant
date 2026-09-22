"""Out-of-sample and walk-forward evidence analysis for APEX.

Phase 2.57 separates development evidence from chronologically unseen
evaluation evidence. It validates supplied OOS/walk-forward evidence; it
does not optimize strategies, fetch market data, execute trades, or claim
future profitability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from statistics import mean, median
from typing import Any, Iterable, Mapping

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INVALID_EVIDENCE = "INVALID_EVIDENCE"
OOS_EVIDENCE = "OOS_EVIDENCE"
OOS_STABILITY = "OOS_STABILITY"

def _finite(v: Any) -> bool:
    if isinstance(v, bool): return False
    try: return isfinite(float(v))
    except (TypeError, ValueError): return False

def _ts(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v.strip(): return None
    s=v.strip()
    if s.endswith('Z'): s=s[:-1]+'+00:00'
    try: d=datetime.fromisoformat(s)
    except ValueError: return None
    if d.tzinfo is None: return None
    return d.astimezone(timezone.utc)

def _fingerprint(v: Any) -> str:
    payload=json.dumps(v,sort_keys=True,separators=(",",":"),default=str)
    return sha256(payload.encode()).hexdigest()

@dataclass(frozen=True)
class OOSWalkForwardCriteria:
    min_test_windows: int = 3
    min_test_trades_per_window: int = 10
    require_cost_coverage: bool = True
    require_risk_coverage: bool = True
    require_chronological_windows: bool = True
    require_locked_parameters: bool = True
    min_profitable_window_fraction: float = 0.67
    def __post_init__(self):
        for n in ('min_test_windows','min_test_trades_per_window'):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<1: raise ValueError(f'{n} must be a positive integer')
        if not 0 < self.min_profitable_window_fraction <= 1: raise ValueError('min_profitable_window_fraction must be between 0 and 1')

@dataclass(frozen=True)
class OOSWindowEvidence:
    window_id: str
    train_start_utc: str
    train_end_utc: str
    test_start_utc: str
    test_end_utc: str
    test_trade_count: int
    test_pnl: float
    parameter_fingerprint: str
    selection_locked: bool = True
    cost_covered: bool = False
    risk_covered: bool = False
    metadata: Mapping[str,Any] = None
    def __post_init__(self):
        if not isinstance(self.window_id,str) or not self.window_id.strip(): raise ValueError('window_id is required')
        if self.test_trade_count < 1 or not _finite(self.test_pnl): raise ValueError('invalid test evidence')
        if not isinstance(self.parameter_fingerprint,str) or not self.parameter_fingerprint.strip(): raise ValueError('parameter_fingerprint is required')
        if _ts(self.train_start_utc) is None or _ts(self.train_end_utc) is None or _ts(self.test_start_utc) is None or _ts(self.test_end_utc) is None: raise ValueError('all timestamps must be timezone-aware ISO timestamps')
        if not (_ts(self.train_start_utc) < _ts(self.train_end_utc) <= _ts(self.test_start_utc) < _ts(self.test_end_utc)): raise ValueError('window chronology is invalid or overlapping')
    @property
    def profitable(self): return self.test_pnl > 0
    def to_dict(self):
        return {'window_id':self.window_id,'train_start_utc':self.train_start_utc,'train_end_utc':self.train_end_utc,'test_start_utc':self.test_start_utc,'test_end_utc':self.test_end_utc,'test_trade_count':self.test_trade_count,'test_pnl':self.test_pnl,'parameter_fingerprint':self.parameter_fingerprint,'selection_locked':self.selection_locked,'cost_covered':self.cost_covered,'risk_covered':self.risk_covered,'metadata':dict(self.metadata or {})}

@dataclass(frozen=True)
class OOSWalkForwardSummary:
    status: str
    criteria: OOSWalkForwardCriteria
    total_windows: int
    valid_windows: int
    profitable_windows: int
    profitable_window_fraction: float | None
    total_test_trades: int
    total_test_pnl: float | None
    mean_window_pnl: float | None
    median_window_pnl: float | None
    min_window_pnl: float | None
    max_window_pnl: float | None
    cost_complete_windows: int
    risk_complete_windows: int
    chronology_valid: bool
    parameter_selection_locked: bool
    leakage_detected: bool
    windows: tuple[OOSWindowEvidence,...]
    limitations: tuple[str,...]
    evidence_fingerprint: str
    def to_dict(self):
        return {'status':self.status,'criteria':self.criteria.__dict__,'total_windows':self.total_windows,'valid_windows':self.valid_windows,'profitable_windows':self.profitable_windows,'profitable_window_fraction':self.profitable_window_fraction,'total_test_trades':self.total_test_trades,'total_test_pnl':self.total_test_pnl,'mean_window_pnl':self.mean_window_pnl,'median_window_pnl':self.median_window_pnl,'min_window_pnl':self.min_window_pnl,'max_window_pnl':self.max_window_pnl,'cost_complete_windows':self.cost_complete_windows,'risk_complete_windows':self.risk_complete_windows,'chronology_valid':self.chronology_valid,'parameter_selection_locked':self.parameter_selection_locked,'leakage_detected':self.leakage_detected,'windows':[w.to_dict() for w in self.windows],'limitations':list(self.limitations),'evidence_fingerprint':self.evidence_fingerprint}

def evaluate_oos_walk_forward(windows: Iterable[OOSWindowEvidence], *, criteria: OOSWalkForwardCriteria|None=None) -> OOSWalkForwardSummary:
    c=criteria or OOSWalkForwardCriteria()
    if not isinstance(c,OOSWalkForwardCriteria): raise TypeError('criteria must be OOSWalkForwardCriteria')
    supplied=tuple(windows)
    limitations=[]; leakage=False; chronology=True
    ordered=sorted(supplied,key=lambda w:(_ts(w.test_start_utc),w.window_id))
    seen_ids=set(); previous_test_end=None
    for w in ordered:
        if w.window_id in seen_ids: leakage=True
        seen_ids.add(w.window_id)
        train_end=_ts(w.train_end_utc); test_start=_ts(w.test_start_utc); test_end=_ts(w.test_end_utc)
        if train_end > test_start: chronology=False; leakage=True
        if previous_test_end is not None and test_start < previous_test_end: chronology=False; leakage=True
        previous_test_end=test_end
        if c.require_locked_parameters and not w.selection_locked: leakage=True
    if not ordered: return OOSWalkForwardSummary(INSUFFICIENT_DATA,c,0,0,0,None,0,None,None,None,None,None,0,0,False,False,False,(),('no_walk_forward_windows',),_fingerprint([]))
    if not chronology: limitations.append('chronology_invalid_or_test_windows_overlap')
    if leakage: limitations.append('selection_or_data_leakage_detected')
    if c.require_cost_coverage and any(not w.cost_covered for w in ordered): limitations.append('cost_coverage_incomplete')
    if c.require_risk_coverage and any(not w.risk_covered for w in ordered): limitations.append('risk_coverage_incomplete')
    if len(ordered)<c.min_test_windows: limitations.append('too_few_test_windows')
    if any(w.test_trade_count<c.min_test_trades_per_window for w in ordered): limitations.append('test_window_sample_below_minimum')
    valid=[w for w in ordered if w.test_trade_count>=1 and _finite(w.test_pnl)]
    profitable=sum(w.profitable for w in valid); frac=profitable/len(valid) if valid else None
    cost_count=sum(w.cost_covered for w in valid); risk_count=sum(w.risk_covered for w in valid)
    sufficient=len(valid)>=c.min_test_windows and all(w.test_trade_count>=c.min_test_trades_per_window for w in valid)
    complete=(not c.require_cost_coverage or cost_count==len(valid)) and (not c.require_risk_coverage or risk_count==len(valid))
    if leakage or not chronology: status=INVALID_EVIDENCE
    elif not sufficient: status=OOS_EVIDENCE
    elif not complete: status=OOS_EVIDENCE
    elif frac is not None and frac>=c.min_profitable_window_fraction: status=OOS_STABILITY
    else: status=OOS_EVIDENCE
    pnls=[w.test_pnl for w in valid]
    payload=[w.to_dict() for w in ordered]
    return OOSWalkForwardSummary(status,c,len(ordered),len(valid),profitable,frac,sum(w.test_trade_count for w in valid),sum(pnls) if pnls else None,mean(pnls) if pnls else None,median(pnls) if pnls else None,min(pnls) if pnls else None,max(pnls) if pnls else None,cost_count,risk_count,chronology,not (c.require_locked_parameters and any(not w.selection_locked for w in ordered)),leakage,ordered,tuple(limitations),_fingerprint(payload))

def evaluate_trade_evidence_windows(records: Iterable[Mapping[str,Any]], *, criteria: OOSWalkForwardCriteria|None=None) -> OOSWalkForwardSummary:
    windows=[]
    for r in records:
        if not isinstance(r,Mapping): continue
        try:
            windows.append(OOSWindowEvidence(window_id=str(r['window_id']),train_start_utc=r['train_start_utc'],train_end_utc=r['train_end_utc'],test_start_utc=r['test_start_utc'],test_end_utc=r['test_end_utc'],test_trade_count=int(r['test_trade_count']),test_pnl=float(r['test_pnl']),parameter_fingerprint=str(r['parameter_fingerprint']),selection_locked=bool(r.get('selection_locked',False)),cost_covered=bool(r.get('cost_covered',False)),risk_covered=bool(r.get('risk_covered',False)),metadata=r.get('metadata') or {}))
        except (KeyError,TypeError,ValueError):
            continue
    return evaluate_oos_walk_forward(windows,criteria=criteria)
