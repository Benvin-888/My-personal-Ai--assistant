from dataclasses import replace
import pytest
from market.paper import PaperTradingEngine
from market.paper_performance import PaperPerformancePolicy,evaluate_paper_performance
from market.paper_forward import *
from market.test_paper_performance import make_plan
def obs(day):
 d=f"2026-01-{day:02d}"; c=[{"timestamp_utc":f"{d}T00:00:00+00:00","open":1.1,"high":1.101,"low":1.099,"close":1.1005},{"timestamp_utc":f"{d}T00:05:00+00:00","open":1.1005,"high":1.103,"low":1.1,"close":1.1025},{"timestamp_utc":f"{d}T00:10:00+00:00","open":1.1025,"high":1.104,"low":1.102,"close":1.103}]; r=PaperTradingEngine().run(c,lambda f:make_plan() if len(f)==1 else None); e=evaluate_paper_performance(r,policy=PaperPerformancePolicy(minimum_trades=1)); return ForwardPaperObservation(f"obs-{day}",f"{d}T00:00:00+00:00",f"{d}T00:20:00+00:00",f"{d}T01:00:00+00:00","EURUSD","5m",e)
def p():return ForwardEvidencePolicy(minimum_observations=3,minimum_total_trades=3)
def test_fingerprint():assert len(obs(1).evidence_fingerprint)==64
def test_small():assert evaluate_forward_paper_evidence([obs(1)]).status is ForwardEvidenceStatus.INSUFFICIENT_DATA
def test_pass():assert evaluate_forward_paper_evidence([obs(1),obs(2),obs(3)],policy=p()).status is ForwardEvidenceStatus.PASS
def test_sort():assert [x.observation_id for x in evaluate_forward_paper_evidence([obs(3),obs(1),obs(2)],policy=p()).observations]==["obs-1","obs-2","obs-3"]
def test_dup_id():
 a=obs(1);b=replace(obs(2),observation_id=a.observation_id);assert evaluate_forward_paper_evidence([a,b],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).status is ForwardEvidenceStatus.FAIL
def test_dup_fp():
 a=obs(1);b=replace(a,observation_id="x",period_start="2026-01-02T00:00:00+00:00",period_end="2026-01-02T00:20:00+00:00",observed_at="2026-01-02T01:00:00+00:00");assert evaluate_forward_paper_evidence([a,b],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).status is ForwardEvidenceStatus.FAIL
def test_overlap():
 a=obs(1);b=replace(obs(2),period_start="2026-01-01T00:10:00+00:00");assert evaluate_forward_paper_evidence([a,b],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).status is ForwardEvidenceStatus.FAIL
def test_metrics():
 r=evaluate_forward_paper_evidence([obs(1)],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1));assert r.metrics.total_trade_count==1 and r.metrics.aggregate_net_pnl>0
def test_recent():assert evaluate_forward_paper_evidence([obs(1),obs(2),obs(3)],policy=p()).metrics.recent_observation_count==1
def test_degradation():
 a=obs(1);m=replace(a.evaluation.metrics,return_fraction=-.01,return_pct=-1,net_pnl=-10,gross_profit=0,gross_loss=10,winning_trades=0,losing_trades=1,breakeven_trades=0,win_rate=0,loss_rate=1,expectancy=-10,average_r_multiple=-1,best_trade=-10,worst_trade=-10);b=replace(obs(3),evaluation=replace(a.evaluation,metrics=m));assert evaluate_forward_paper_evidence([a,b],policy=ForwardEvidencePolicy(minimum_observations=2,minimum_total_trades=2,minimum_recent_return_fraction_of_earlier=.5)).status is ForwardEvidenceStatus.FAIL
def test_bad_policy():
 with pytest.raises(PaperForwardEvidenceError):ForwardEvidencePolicy(minimum_pass_fraction=1.5)
def test_bad_member():
 with pytest.raises(PaperForwardEvidenceError):PaperForwardEvidenceEngine().evaluate(["bad"])
def test_bad_timestamp():
 with pytest.raises(PaperForwardEvidenceError):ForwardPaperObservation("x","bad","2026-01-01T00:20:00+00:00","2026-01-01T01:00:00+00:00","EURUSD","5m",obs(1).evaluation)
def test_empty():assert evaluate_forward_paper_evidence([]).status is ForwardEvidenceStatus.INSUFFICIENT_DATA
def test_deterministic():
 a=evaluate_forward_paper_evidence([obs(1),obs(2),obs(3)],policy=p());b=evaluate_forward_paper_evidence([obs(1),obs(2),obs(3)],policy=p());assert a.evidence_fingerprint==b.evidence_fingerprint
def test_no_execution():
 r=evaluate_forward_paper_evidence([obs(1)],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1));assert not r.metadata["broker_access"] and not r.metadata["execution_authorization"]
def test_to_dict():
 r=evaluate_forward_paper_evidence([obs(1)],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1));assert r.to_dict()["metrics"]["observation_count"]==1
def test_dd():
 a=obs(1);a=replace(a,evaluation=replace(a.evaluation,metrics=replace(a.evaluation.metrics,max_drawdown_fraction=.3,max_drawdown_pct=30)));assert evaluate_forward_paper_evidence([a],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).status is ForwardEvidenceStatus.FAIL
def test_boundary():
 a=obs(1);b=replace(obs(2),period_start=a.period_end);assert next(x for x in evaluate_forward_paper_evidence([a,b],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).checks if x.name=="non_overlapping_periods").passed
def test_metadata():
 a=replace(obs(1),metadata={"session":"London"});assert evaluate_forward_paper_evidence([a],policy=ForwardEvidencePolicy(minimum_observations=1,minimum_total_trades=1)).observations[0].metadata["session"]=="London"
