from __future__ import annotations
"""Phase 2.16 research portfolio/correlation robustness contracts."""
from dataclasses import dataclass, field
from enum import Enum
import hashlib, json, math
from typing import Any, Mapping, Sequence
from .cohort import ResearchCohortResult

class PortfolioRobustnessError(ValueError): pass
class PortfolioRobustnessStatus(str, Enum):
    PASS="PASS"; HOLD="HOLD"; INSUFFICIENT_DATA="INSUFFICIENT_DATA"; INVALID_INPUT="INVALID_INPUT"

def _text(v: Any, n: str)->str:
    if not isinstance(v,str) or not v.strip(): raise PortfolioRobustnessError(f"{n} must be a non-empty string")
    return v.strip()
def _num(v: Any,n:str)->float:
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)): raise PortfolioRobustnessError(f"{n} must be finite numeric")
    return float(v)
def _fp(v: Any)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

@dataclass(frozen=True)
class PairCorrelationObservation:
    symbol_a:str; symbol_b:str; correlation:float; sample_size:int
    method:str="external"; period_start_utc:str=""; period_end_utc:str=""; metadata:Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        a,b=_text(self.symbol_a,"symbol_a"),_text(self.symbol_b,"symbol_b")
        if a==b: raise PortfolioRobustnessError("correlation observation requires two distinct symbols")
        c=_num(self.correlation,"correlation")
        if not -1<=c<=1: raise PortfolioRobustnessError("correlation must be between -1 and 1")
        if isinstance(self.sample_size,bool) or not isinstance(self.sample_size,int) or self.sample_size<2: raise PortfolioRobustnessError("sample_size must be an integer >= 2")
        _text(self.method,"method")
    @property
    def pair_key(self): return "|".join(sorted((self.symbol_a,self.symbol_b)))
    def to_dict(self): return {"symbol_a":self.symbol_a,"symbol_b":self.symbol_b,"correlation":self.correlation,"sample_size":self.sample_size,"method":self.method,"period_start_utc":self.period_start_utc,"period_end_utc":self.period_end_utc,"metadata":dict(self.metadata)}

@dataclass(frozen=True)
class PortfolioRobustnessPolicy:
    minimum_symbols:int=2; minimum_correlation_observations:int=1; minimum_correlation_sample_size:int=30
    maximum_abs_pair_correlation:float=.90; maximum_weighted_average_abs_correlation:float=.75
    maximum_risk_concentration_fraction:float=.70; minimum_effective_symbol_count:float=1.50
    require_correlation_evidence:bool=True
    def __post_init__(self):
        for n in ("minimum_symbols","minimum_correlation_observations","minimum_correlation_sample_size"):
            v=getattr(self,n)
            if isinstance(v,bool) or not isinstance(v,int) or v<1: raise PortfolioRobustnessError(f"{n} must be a positive integer")
        for n in ("maximum_abs_pair_correlation","maximum_weighted_average_abs_correlation","maximum_risk_concentration_fraction"):
            v=_num(getattr(self,n),n)
            if not 0<=v<=1: raise PortfolioRobustnessError(f"{n} must be between 0 and 1")
        if _num(self.minimum_effective_symbol_count,"minimum_effective_symbol_count")<1: raise PortfolioRobustnessError("minimum_effective_symbol_count must be >= 1")
        if not isinstance(self.require_correlation_evidence,bool): raise PortfolioRobustnessError("require_correlation_evidence must be a boolean")
    def to_dict(self): return {n:getattr(self,n) for n in self.__dataclass_fields__}

@dataclass(frozen=True)
class PortfolioRobustnessCheck:
    name:str; passed:bool; required:bool; actual:Any; threshold:Any; reason:str
    def to_dict(self): return {"name":self.name,"passed":self.passed,"required":self.required,"actual":self.actual,"threshold":self.threshold,"reason":self.reason}

@dataclass(frozen=True)
class PortfolioRobustnessResult:
    cohort_id:str; status:PortfolioRobustnessStatus; symbols:tuple[str,...]; observed_pairs:tuple[str,...]; missing_pairs:tuple[str,...]
    max_abs_pair_correlation:float|None; weighted_average_abs_correlation:float|None; risk_concentration_fraction:float|None; effective_symbol_count:float|None
    checks:tuple[PortfolioRobustnessCheck,...]; failures:tuple[str,...]; warnings:tuple[str,...]; evidence_fingerprint:str; eligible_for_promotion:bool
    policy:Mapping[str,Any]; metadata:Mapping[str,Any]=field(default_factory=dict)
    def to_dict(self): return {"cohort_id":self.cohort_id,"status":self.status.value,"symbols":list(self.symbols),"observed_pairs":list(self.observed_pairs),"missing_pairs":list(self.missing_pairs),"max_abs_pair_correlation":self.max_abs_pair_correlation,"weighted_average_abs_correlation":self.weighted_average_abs_correlation,"risk_concentration_fraction":self.risk_concentration_fraction,"effective_symbol_count":self.effective_symbol_count,"checks":[x.to_dict() for x in self.checks],"failures":list(self.failures),"warnings":list(self.warnings),"evidence_fingerprint":self.evidence_fingerprint,"eligible_for_promotion":self.eligible_for_promotion,"policy":dict(self.policy),"metadata":dict(self.metadata)}

class ResearchPortfolioRobustnessEngine:
    def __init__(self, policy=None): self.policy=policy or PortfolioRobustnessPolicy()
    @staticmethod
    def _pairs(symbols): return tuple(f"{a}|{b}" for i,a in enumerate(symbols) for b in symbols[i+1:])
    @staticmethod
    def _concentration(weights,symbols):
        total=sum(weights.get(s,0.0) for s in symbols)
        return None if total<=0 else max(weights.get(s,0.0) for s in symbols)/total
    @staticmethod
    def _weighted_abs(obs,weights):
        if not weights: return sum(abs(x.correlation) for x in obs)/len(obs)
        pairs=[(weights.get(x.symbol_a,0)*weights.get(x.symbol_b,0),abs(x.correlation)) for x in obs]
        pairs=[p for p in pairs if p[0]>0]
        return sum(w*c for w,c in pairs)/sum(w for w,_ in pairs) if pairs else sum(abs(x.correlation) for x in obs)/len(obs)
    @staticmethod
    def _effective(obs,weights,symbols):
        total=sum(weights.get(s,0) for s in symbols)
        if total<=0:return None
        w={s:weights.get(s,0)/total for s in symbols}; vf=sum(x*x for x in w.values())
        for o in obs: vf += 2*w.get(o.symbol_a,0)*w.get(o.symbol_b,0)*o.correlation
        return float("inf") if vf<=0 else 1/vf
    def evaluate(self,cohort,correlations,*,risk_weights=None):
        if not isinstance(cohort,ResearchCohortResult): raise PortfolioRobustnessError("cohort must be a ResearchCohortResult")
        obs=tuple(correlations)
        if any(not isinstance(x,PairCorrelationObservation) for x in obs): raise PortfolioRobustnessError("all correlations must be PairCorrelationObservation instances")
        weights=dict(risk_weights or {})
        for s,w in weights.items():
            _text(s,"risk_weights symbol")
            if _num(w,f"risk weight for {s}")<0: raise PortfolioRobustnessError("risk weights must be non-negative")
        symbols=tuple(sorted(cohort.symbols)); p=self.policy; required=self._pairs(symbols)
        if len(symbols)<p.minimum_symbols:
            return self._build(cohort.cohort_id,symbols,(),required,None,None,None,None,[("minimum_symbols",False,True,len(symbols),p.minimum_symbols,"insufficient distinct symbols for portfolio analysis")],("insufficient distinct symbols for portfolio analysis",),(),obs,weights,PortfolioRobustnessStatus.INSUFFICIENT_DATA)
        pair_map={}
        for o in obs:
            if o.symbol_a not in symbols or o.symbol_b not in symbols: raise PortfolioRobustnessError("correlation observation contains symbol outside the cohort")
            if o.pair_key in pair_map: raise PortfolioRobustnessError(f"duplicate correlation pair: {o.pair_key}")
            pair_map[o.pair_key]=o
        observed=tuple(sorted(pair_map)); missing=tuple(x for x in required if x not in pair_map); usable=[x for x in pair_map.values() if x.sample_size>=p.minimum_correlation_sample_size]
        checks=[]; failures=[]; warnings=[]
        def add(n,ok,req,actual,threshold,reason):
            checks.append(PortfolioRobustnessCheck(n,bool(ok),bool(req),actual,threshold,reason))
            if req and not ok: failures.append(reason)
        add("minimum_correlation_observations",len(usable)>=p.minimum_correlation_observations,p.require_correlation_evidence,len(usable),p.minimum_correlation_observations,"enough usable correlation observations are present" if len(usable)>=p.minimum_correlation_observations else "too few usable correlation observations")
        add("complete_pair_coverage",not missing,p.require_correlation_evidence,len(observed),len(required),"all cohort symbol pairs have correlation evidence" if not missing else "correlation evidence is missing for one or more cohort pairs")
        if any(x.sample_size<p.minimum_correlation_sample_size for x in pair_map.values()): warnings.append("one or more supplied correlation observations have insufficient sample size")
        maxc=max((abs(x.correlation) for x in usable),default=None); wa=self._weighted_abs(usable,weights) if usable else None; rc=self._concentration(weights,symbols) if weights else None; ec=self._effective(usable,weights,symbols) if usable and weights else None
        add("maximum_abs_pair_correlation",maxc is not None and maxc<=p.maximum_abs_pair_correlation,p.require_correlation_evidence,maxc,p.maximum_abs_pair_correlation,"maximum pair correlation is within the research ceiling" if maxc is not None and maxc<=p.maximum_abs_pair_correlation else "pair correlation concentration exceeds the research ceiling")
        add("weighted_average_abs_correlation",wa is None or wa<=p.maximum_weighted_average_abs_correlation,False,wa,p.maximum_weighted_average_abs_correlation,"weighted average correlation is within the research ceiling")
        add("risk_concentration",rc is None or rc<=p.maximum_risk_concentration_fraction,False,rc,p.maximum_risk_concentration_fraction,"risk concentration is within the advisory ceiling")
        add("effective_symbol_count",ec is None or ec>=p.minimum_effective_symbol_count,False,ec,p.minimum_effective_symbol_count,"effective symbol count is adequate")
        if set(weights)-set(symbols): raise PortfolioRobustnessError("risk_weights contains symbols outside the cohort")
        status=PortfolioRobustnessStatus.PASS if not failures else PortfolioRobustnessStatus.HOLD
        if not usable and p.require_correlation_evidence: status=PortfolioRobustnessStatus.INSUFFICIENT_DATA
        return self._build(cohort.cohort_id,symbols,observed,missing,maxc,wa,rc,ec,checks,failures,warnings,obs,weights,status)
    def _build(self,cid,symbols,observed,missing,maxc,wa,rc,ec,checks,failures,warnings,obs,weights,status):
        checks=tuple(x if isinstance(x,PortfolioRobustnessCheck) else PortfolioRobustnessCheck(*x) for x in checks)
        payload={"cohort_id":cid,"symbols":list(symbols),"observations":[x.to_dict() for x in obs],"weights":dict(weights),"checks":[x.to_dict() for x in checks],"failures":list(failures)}
        return PortfolioRobustnessResult(cid,status,symbols,observed,missing,maxc,wa,rc,ec,checks,tuple(failures),tuple(warnings),_fp(payload),status==PortfolioRobustnessStatus.PASS,self.policy.to_dict(),{"correlation_source_external":True,"candidate_selection":False,"execution_authorization":False,"broker_access":False})

def assess_portfolio_robustness(cohort,correlations,policy=None,*,risk_weights=None): return ResearchPortfolioRobustnessEngine(policy).evaluate(cohort,correlations,risk_weights=risk_weights)
