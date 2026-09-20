from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib, json
from typing import Any, Mapping

from .opportunity import OpportunityStatus, TradeOpportunityEngine
from .strategy.ensemble import EnsembleEngine
from .strategy.factory import StrategyFactory
from .strategy.registry import StrategyRegistry

class MarketIntelligenceError(ValueError): pass
class IntelligenceStatus(str, Enum):
    EVALUATED='EVALUATED'; REJECTED='REJECTED'; INVALID_INPUT='INVALID_INPUT'; ERROR='ERROR'

def _fingerprint(v: Any) -> str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def _mapping(v: Any,n: str):
    if not isinstance(v,Mapping): raise MarketIntelligenceError(f'{n} must be a mapping')
    return v
def _identity(v: Mapping[str,Any], n: str):
    p=v.get('pair'); i=v.get('interval'); t=v.get('latest_timestamp_utc',v.get('timestamp_utc'))
    if not isinstance(p,str) or not p.strip(): raise MarketIntelligenceError(f'{n} pair must be a non-empty string')
    if not isinstance(i,str) or not i.strip(): raise MarketIntelligenceError(f'{n} interval must be a non-empty string')
    if t is not None and (not isinstance(t,str) or not t.strip()): raise MarketIntelligenceError(f'{n} timestamp must be a non-empty string when supplied')
    return p.strip().upper().replace('/',''),i.strip(),t

def _check(v,n,expected):
    p=v.get('pair'); i=v.get('interval'); t=v.get('timestamp_utc')
    if p is not None and str(p).strip().upper().replace('/','')!=expected[0]: raise MarketIntelligenceError(f'{n} pair does not match technical analysis')
    if i is not None and str(i).strip()!=expected[1]: raise MarketIntelligenceError(f'{n} interval does not match technical analysis')
    if expected[2] is not None and t is not None and str(t).strip()!=expected[2]: raise MarketIntelligenceError(f'{n} timestamp does not match technical analysis')

@dataclass(frozen=True)
class MarketIntelligenceSnapshot:
    status: IntelligenceStatus; pair: str; interval: str; timestamp_utc: str|None
    ensemble: Mapping[str,Any]; opportunity: Mapping[str,Any]
    regime: Mapping[str,Any]|None=None; session: Mapping[str,Any]|None=None; operational_state: Mapping[str,Any]|None=None
    evidence_fingerprint: str=''; execution_authorized: bool=False; reasons: tuple[str,...]=(); metadata: Mapping[str,Any]=field(default_factory=dict)
    def __post_init__(self):
        if self.execution_authorized: raise MarketIntelligenceError('market intelligence cannot authorize execution')
        if not self.evidence_fingerprint: raise MarketIntelligenceError('evidence_fingerprint is required')
    @property
    def candidate(self): return self.status is IntelligenceStatus.EVALUATED and self.opportunity.get('status')==OpportunityStatus.CANDIDATE.value
    def to_dict(self):
        return {'success':self.status is IntelligenceStatus.EVALUATED,'market':'forex','analysis':'market_intelligence','status':self.status.value,'pair':self.pair,'interval':self.interval,'timestamp_utc':self.timestamp_utc,'ensemble':dict(self.ensemble),'opportunity':dict(self.opportunity),'regime':dict(self.regime) if self.regime is not None else None,'session':dict(self.session) if self.session is not None else None,'operational_state':dict(self.operational_state) if self.operational_state is not None else None,'candidate':self.candidate,'execution_authorized':False,'evidence_fingerprint':self.evidence_fingerprint,'reasons':list(self.reasons),'metadata':dict(self.metadata)}

class MarketIntelligenceEngine:
    def __init__(self,*,ensemble=None,opportunity=None): self.ensemble=ensemble or EnsembleEngine(); self.opportunity=opportunity or TradeOpportunityEngine()
    def evaluate(self,analysis,*,registry,factory,regime=None,session=None,operational_state=None):
        try:
            a=_mapping(analysis,'analysis'); pair,interval,timestamp=_identity(a,'analysis')
            if not isinstance(registry,StrategyRegistry): raise MarketIntelligenceError('registry must be a StrategyRegistry')
            if not isinstance(factory,StrategyFactory): raise MarketIntelligenceError('factory must be a StrategyFactory')
            if a.get('success') is not True: return self._reject(pair,interval,timestamp,'technical analysis is not successful')
            for n,v in {'regime':regime,'session':session,'operational_state':operational_state}.items():
                if v is not None: _check(_mapping(v,n),n,(pair,interval,timestamp))
            ens=self.ensemble.evaluate(dict(a),registry,factory)
            if not isinstance(ens,Mapping): raise MarketIntelligenceError('strategy ensemble returned an invalid result')
            sp=dict(session) if session is not None else None
            if sp is not None: sp.update({k:sp.get(k,v) for k,v in {'pair':pair,'interval':interval,'timestamp_utc':timestamp}.items()})
            opp=self.opportunity.assess(ens,regime=dict(regime) if regime is not None else None,session=sp,operational_state=dict(operational_state) if operational_state is not None else None).to_dict()
            payload={'pair':pair,'interval':interval,'timestamp_utc':timestamp,'ensemble':dict(ens),'opportunity':dict(opp),'regime':dict(regime) if regime is not None else None,'session':sp,'operational_state':dict(operational_state) if operational_state is not None else None}
            status=IntelligenceStatus.EVALUATED if opp.get('status')==OpportunityStatus.CANDIDATE.value else IntelligenceStatus.REJECTED
            if opp.get('status')==OpportunityStatus.ERROR.value: status=IntelligenceStatus.ERROR
            return MarketIntelligenceSnapshot(status,pair,interval,timestamp,dict(ens),dict(opp),dict(regime) if regime is not None else None,sp,dict(operational_state) if operational_state is not None else None,_fingerprint(payload),False,tuple(opp.get('reasons',())),{'contract_version':'2.40','read_only':True,'point_in_time':True,'execution_boundary':'external'})
        except MarketIntelligenceError: raise
        except Exception as exc: return self._error(str(a.get('pair','UNKNOWN')) if isinstance(analysis,Mapping) else 'UNKNOWN',str(a.get('interval','UNKNOWN')) if isinstance(analysis,Mapping) else 'UNKNOWN',a.get('latest_timestamp_utc') if isinstance(analysis,Mapping) else None,str(exc))
    @staticmethod
    def _reject(pair,interval,timestamp,reason): return MarketIntelligenceSnapshot(IntelligenceStatus.REJECTED,pair,interval,timestamp,{}, {'status':OpportunityStatus.REJECTED.value,'reasons':[reason]}, evidence_fingerprint=_fingerprint({'pair':pair,'interval':interval,'timestamp_utc':timestamp,'reason':reason}), reasons=(reason,), metadata={'contract_version':'2.40','read_only':True})
    @staticmethod
    def _error(pair,interval,timestamp,error): return MarketIntelligenceSnapshot(IntelligenceStatus.ERROR,pair,interval,timestamp,{}, {'status':OpportunityStatus.ERROR.value,'error':error}, evidence_fingerprint=_fingerprint({'pair':pair,'interval':interval,'timestamp_utc':timestamp,'error':error}), reasons=(error,), metadata={'contract_version':'2.40','read_only':True})
