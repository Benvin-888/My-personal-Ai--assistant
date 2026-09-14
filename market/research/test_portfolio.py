from .cohort import ResearchCohortEngine
from .experiment import ExperimentStatus,ResearchDatasetSpec,ResearchExperimentResult,ResearchExperimentSpec
from .engine import ResearchPerformance
from .portfolio import *

def r(i,s):
 d=ResearchDatasetSpec(f"ds{i}",s,"5m","2026-01-01","2026-03-01","test",100,f"fp{i}")
 return ResearchExperimentResult(ResearchExperimentSpec(f"e{i}","strategy",d),ExperimentStatus.PASS,ResearchPerformance(1000,1010,10,1,40,55,1.5,.2,.5,20,2,10,2,2,500,200))
def c(ss): return ResearchCohortEngine().evaluate("c",[r(i+1,s) for i,s in enumerate(ss)])
def o(a,b,x=.2,n=100): return PairCorrelationObservation(a,b,x,n)

def test_pass():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD","USDJPY")),[o("EURUSD","GBPUSD",.2),o("EURUSD","USDJPY",-.1),o("GBPUSD","USDJPY",.3)],risk_weights={"EURUSD":1,"GBPUSD":1,"USDJPY":1}); assert x.status==PortfolioRobustnessStatus.PASS and x.eligible_for_promotion
def test_high_corr_holds():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD","USDJPY")),[o("EURUSD","GBPUSD",.95),o("EURUSD","USDJPY",.1),o("GBPUSD","USDJPY",.2)]); assert x.status==PortfolioRobustnessStatus.HOLD
def test_missing_pair():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD","USDJPY")),[o("EURUSD","GBPUSD")]); assert x.status==PortfolioRobustnessStatus.HOLD and len(x.missing_pairs)==2
def test_no_evidence(): assert ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[]).status==PortfolioRobustnessStatus.INSUFFICIENT_DATA
def test_low_sample():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","GBPUSD",.1,10)]); assert x.status==PortfolioRobustnessStatus.INSUFFICIENT_DATA and x.warnings
def test_optional_gate(): assert ResearchPortfolioRobustnessEngine(PortfolioRobustnessPolicy(require_correlation_evidence=False)).evaluate(c(("EURUSD","GBPUSD")),[]).status==PortfolioRobustnessStatus.PASS
def test_order_independent(): assert o("GBPUSD","EURUSD").pair_key==o("EURUSD","GBPUSD").pair_key
def test_duplicate_rejected():
 try: ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","GBPUSD"),o("GBPUSD","EURUSD")])
 except PortfolioRobustnessError: pass
 else: assert False
def test_outside_rejected():
 try: ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","USDJPY")])
 except PortfolioRobustnessError: pass
 else: assert False
def test_concentration():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD","USDJPY")),[o("EURUSD","GBPUSD"),o("EURUSD","USDJPY"),o("GBPUSD","USDJPY")],risk_weights={"EURUSD":7,"GBPUSD":1,"USDJPY":2}); assert x.risk_concentration_fraction==.7
def test_effective_deterministic():
 args=(c(("EURUSD","GBPUSD","USDJPY")),[o("EURUSD","GBPUSD",.4),o("EURUSD","USDJPY",.1),o("GBPUSD","USDJPY",.2)]); kw={"EURUSD":1,"GBPUSD":1,"USDJPY":1}; a=ResearchPortfolioRobustnessEngine().evaluate(*args,risk_weights=kw); b=ResearchPortfolioRobustnessEngine().evaluate(*args,risk_weights=kw); assert a.effective_symbol_count==b.effective_symbol_count and a.evidence_fingerprint==b.evidence_fingerprint
def test_bad_corr():
 try: PairCorrelationObservation("EURUSD","GBPUSD",1.1,100)
 except PortfolioRobustnessError: pass
 else: assert False
def test_negative_weight():
 try: ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","GBPUSD")],risk_weights={"EURUSD":-1,"GBPUSD":1})
 except PortfolioRobustnessError: pass
 else: assert False
def test_min_symbols(): assert ResearchPortfolioRobustnessEngine(PortfolioRobustnessPolicy(minimum_symbols=3)).evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","GBPUSD")]).status==PortfolioRobustnessStatus.INSUFFICIENT_DATA
def test_audit_controls():
 x=ResearchPortfolioRobustnessEngine().evaluate(c(("EURUSD","GBPUSD")),[o("EURUSD","GBPUSD")]); assert x.to_dict()["metadata"]["execution_authorization"] is False
