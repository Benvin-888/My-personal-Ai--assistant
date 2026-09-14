"""Phase 2.21: deterministic forward paper-trading evidence evaluation."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib, json, math
from statistics import mean
from typing import Any, Mapping, Sequence
from .paper_performance import PaperPerformanceEvaluation
class PaperForwardEvidenceError(ValueError): pass
class ForwardEvidenceStatus(str,Enum): PASS="PASS"; WARN="WARN"; FAIL="FAIL"; INSUFFICIENT_DATA="INSUFFICIENT_DATA"; INVALID_INPUT="INVALID_INPUT"
def _dt(v,n):
    if not isinstance(v,str) or not v.strip(): raise PaperForwardEvidenceError(f"{n} must be non-empty")
    try:d=datetime.fromisoformat(v.strip().replace("Z","+00:00"))
    except ValueError as e:raise PaperForwardEvidenceError(f"{n} must be ISO-8601") from e
    if d.tzinfo is None:raise PaperForwardEvidenceError(f"{n} must be timezone-aware")
    return d
def _fp(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
@dataclass(frozen=True)
class ForwardPaperObservation:
    observation_id:str; period_start:str; period_end:str; observed_at:str; symbol:str; interval:str; evaluation:PaperPerformanceEvaluation; metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        if not isinstance(self.observation_id,str) or not self.observation_id.strip():raise PaperForwardEvidenceError("observation_id must be non-empty")
        if _dt(self.period_end,"period_end")<=_dt(self.period_start,"period_start"):raise PaperForwardEvidenceError("period_end must be after period_start")
        _dt(self.observed_at,"observed_at")
        if not isinstance(self.symbol,str) or not self.symbol.strip():raise PaperForwardEvidenceError("symbol must be non-empty")
        if not isinstance(self.interval,str) or not self.interval.strip():raise PaperForwardEvidenceError("interval must be non-empty")
        if not isinstance(self.evaluation,PaperPerformanceEvaluation):raise PaperForwardEvidenceError("evaluation must be a PaperPerformanceEvaluation")
        if not isinstance(self.metadata,Mapping):raise PaperForwardEvidenceError("metadata must be a mapping")
    @property
    def source_evidence_fingerprint(self):return self.evaluation.evidence_fingerprint
    @property
    def evidence_fingerprint(self):return _fp(self.to_dict(False))
    def to_dict(self,include_fingerprint=True):
        d={"observation_id":self.observation_id,"period_start":self.period_start,"period_end":self.period_end,"observed_at":self.observed_at,"symbol":self.symbol,"interval":self.interval,"evaluation":self.evaluation.to_dict(),"metadata":dict(self.metadata)}
        if include_fingerprint:d["observation_fingerprint"]=self.evidence_fingerprint
        return d
@dataclass(frozen=True)
class ForwardEvidencePolicy:
    minimum_observations:int=3; minimum_total_trades:int=30; minimum_pass_fraction:float=2/3; minimum_positive_return_fraction:float=2/3; minimum_recent_pass_fraction:float=.5; minimum_recent_return_fraction_of_earlier:float=.25; maximum_drawdown_fraction:float=.2; require_unique_observation_ids:bool=True; require_unique_evidence_fingerprints:bool=True; require_non_overlapping_periods:bool=True
    def __post_init__(self):
        if not isinstance(self.minimum_observations,int) or isinstance(self.minimum_observations,bool) or self.minimum_observations<1:raise PaperForwardEvidenceError("minimum_observations must be positive integer")
        if not isinstance(self.minimum_total_trades,int) or isinstance(self.minimum_total_trades,bool) or self.minimum_total_trades<1:raise PaperForwardEvidenceError("minimum_total_trades must be positive integer")
        for n in ("minimum_pass_fraction","minimum_positive_return_fraction","minimum_recent_pass_fraction","minimum_recent_return_fraction_of_earlier","maximum_drawdown_fraction"):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)) or not 0<=float(v)<=1:raise PaperForwardEvidenceError(f"{n} must be between 0 and 1")
        for n in ("require_unique_observation_ids","require_unique_evidence_fingerprints","require_non_overlapping_periods"):
            if not isinstance(getattr(self,n),bool):raise PaperForwardEvidenceError(f"{n} must be boolean")
    def to_dict(self):return {n:getattr(self,n) for n in self.__dataclass_fields__}
@dataclass(frozen=True)
class ForwardEvidenceMetrics:
    observation_count:int; total_trade_count:int; pass_observations:int; fail_observations:int; insufficient_observations:int; pass_fraction:float; positive_return_observations:int; positive_return_fraction:float; aggregate_net_pnl:float; aggregate_gross_profit:float; aggregate_gross_loss:float; aggregate_costs:float; aggregate_return_fraction:float; weighted_average_return_fraction:float; worst_observation_return_fraction:float; average_observation_return_fraction:float; worst_drawdown_fraction:float; average_expectancy:float; average_r_multiple:float; recent_observation_count:int; recent_pass_fraction:float; recent_average_return_fraction:float; earlier_average_return_fraction:float; return_degradation_fraction:float|None
    def to_dict(self):return {n:getattr(self,n) for n in self.__dataclass_fields__}
@dataclass(frozen=True)
class ForwardEvidenceCheck:
    name:str; passed:bool; required:bool; observed:float|int|bool|None; threshold:float|int|bool|None; message:str
    def to_dict(self):return {n:getattr(self,n) for n in self.__dataclass_fields__}
@dataclass(frozen=True)
class PaperForwardEvidenceResult:
    status:ForwardEvidenceStatus; metrics:ForwardEvidenceMetrics; checks:tuple[ForwardEvidenceCheck,...]; observations:tuple[ForwardPaperObservation,...]; evidence_fingerprint:str; metadata:Mapping[str,Any]=field(default_factory=dict)
    @property
    def forward_evidence_credible(self):return self.status is ForwardEvidenceStatus.PASS
    def to_dict(self):return {"status":self.status.value,"metrics":self.metrics.to_dict(),"checks":[c.to_dict() for c in self.checks],"observations":[o.to_dict() for o in self.observations],"evidence_fingerprint":self.evidence_fingerprint,"metadata":dict(self.metadata),"forward_evidence_credible":self.forward_evidence_credible}
def _metrics(items):
    es=[o.evaluation for o in items]; n=len(es); rs=[e.metrics.return_fraction for e in es]; rn=max(1,n//2) if n else 0; recent=es[-rn:] if rn else []; earlier=es[:-rn] if rn else []; rav=mean([e.metrics.return_fraction for e in recent]) if recent else 0.; eav=mean([e.metrics.return_fraction for e in earlier]) if earlier else 0.; passed=sum(e.status.value=="PASS" for e in es)
    return ForwardEvidenceMetrics(n,sum(e.metrics.trade_count for e in es),passed,sum(e.status.value=="FAIL" for e in es),sum(e.status.value=="INSUFFICIENT_DATA" for e in es),passed/n if n else 0.,sum(x>0 for x in rs),sum(x>0 for x in rs)/n if n else 0.,sum(e.metrics.net_pnl for e in es),sum(e.metrics.gross_profit for e in es),sum(e.metrics.gross_loss for e in es),sum(e.metrics.total_costs for e in es),sum(e.metrics.net_pnl for e in es)/sum(e.metrics.initial_equity for e in es) if es else 0.,sum(e.metrics.net_pnl for e in es)/sum(e.metrics.initial_equity for e in es) if es else 0.,min(rs,default=0.),mean(rs) if rs else 0.,max((e.metrics.max_drawdown_fraction for e in es),default=0.),(mean(e.metrics.expectancy for e in es) if es else 0.),(mean(e.metrics.average_r_multiple for e in es) if es else 0.),rn,(sum(e.status.value=="PASS" for e in recent)/len(recent) if recent else 0.),rav,eav,(1-rav/eav if eav>0 else None))
class PaperForwardEvidenceEngine:
    def __init__(self,policy=None):self.policy=policy or ForwardEvidencePolicy()
    def evaluate(self,observations):
        if isinstance(observations,(str,bytes)) or not isinstance(observations,Sequence):raise PaperForwardEvidenceError("observations must be a sequence")
        items=tuple(observations)
        if not all(isinstance(o,ForwardPaperObservation) for o in items):raise PaperForwardEvidenceError("all observations must be ForwardPaperObservation instances")
        items=tuple(sorted(items,key=lambda o:(_dt(o.period_start,"period_start"),_dt(o.period_end,"period_end"),o.observation_id))); ids=[o.observation_id for o in items]; fps=[o.source_evidence_fingerprint for o in items]
        uid=len(ids)==len(set(ids)); ufp=len(fps)==len(set(fps)); no=all(_dt(items[i].period_end,"period_end")<=_dt(items[i+1].period_start,"period_start") for i in range(len(items)-1)); m=_metrics(items)
        c=[ForwardEvidenceCheck("unique_observation_ids",uid,self.policy.require_unique_observation_ids,uid,True,"unique IDs"),ForwardEvidenceCheck("unique_evidence_fingerprints",ufp,self.policy.require_unique_evidence_fingerprints,ufp,True,"unique evidence"),ForwardEvidenceCheck("non_overlapping_periods",no,self.policy.require_non_overlapping_periods,no,True,"non-overlapping periods")]
        vals=[("minimum_observations",m.observation_count>=self.policy.minimum_observations,m.observation_count,self.policy.minimum_observations),("minimum_total_trades",m.total_trade_count>=self.policy.minimum_total_trades,m.total_trade_count,self.policy.minimum_total_trades),("pass_fraction",m.pass_fraction>=self.policy.minimum_pass_fraction,m.pass_fraction,self.policy.minimum_pass_fraction),("positive_return_fraction",m.positive_return_fraction>=self.policy.minimum_positive_return_fraction,m.positive_return_fraction,self.policy.minimum_positive_return_fraction),("maximum_drawdown",m.worst_drawdown_fraction<=self.policy.maximum_drawdown_fraction,m.worst_drawdown_fraction,self.policy.maximum_drawdown_fraction),("recent_pass_fraction",m.recent_pass_fraction>=self.policy.minimum_recent_pass_fraction,m.recent_pass_fraction,self.policy.minimum_recent_pass_fraction)]
        deg=True
        if m.earlier_average_return_fraction>0:deg=m.recent_average_return_fraction>=m.earlier_average_return_fraction*self.policy.minimum_recent_return_fraction_of_earlier
        vals.append(("return_degradation",deg,m.return_degradation_fraction,1-self.policy.minimum_recent_return_fraction_of_earlier))
        for name,ok,observed,threshold in vals:c.append(ForwardEvidenceCheck(name,ok,True,observed,threshold,"passed" if ok else "failed"))
        status=ForwardEvidenceStatus.INSUFFICIENT_DATA if m.observation_count<self.policy.minimum_observations or m.total_trade_count<self.policy.minimum_total_trades else (ForwardEvidenceStatus.PASS if all(x.passed for x in c if x.required) else ForwardEvidenceStatus.FAIL)
        payload={"status":status.value,"metrics":m.to_dict(),"checks":[x.to_dict() for x in c],"observations":[o.to_dict() for o in items],"policy":self.policy.to_dict()}
        return PaperForwardEvidenceResult(status,m,tuple(c),items,_fp(payload),{"phase":"2.21","research_only":True,"broker_access":False,"order_placement":False,"execution_authorization":False,"optimization":False,"strategy_selection":False,"profitability_guarantee":False})
def evaluate_forward_paper_evidence(observations,*,policy=None):return PaperForwardEvidenceEngine(policy).evaluate(observations)
