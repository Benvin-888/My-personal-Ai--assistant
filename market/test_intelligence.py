from __future__ import annotations
import copy, pytest
from market.intelligence import IntelligenceStatus, MarketIntelligenceEngine, MarketIntelligenceError, MarketIntelligenceSnapshot
from market.strategy import StrategyConfig, StrategyFactory, StrategyRegistry
from market.strategy.strategies import MeanReversionStrategy, TrendMomentumStrategy
T='2026-09-19T10:00:00Z'
def analysis(): return {'success':True,'pair':'EURUSD','interval':'5m','latest_timestamp_utc':T,'candle_count':100,'indicators':{'ema_fast':{'value':1.161},'ema_slow':{'value':1.160},'rsi':{'value':62.},'macd':{'histogram':.0002},'bollinger_bands':{'lower':1.158,'middle':1.160,'upper':1.162}},'classification':{'trend':'BULLISH','volatility':'LOW'},'metadata':{'latest_close':1.161}}
def rf():
 r=StrategyRegistry(); r.register(TrendMomentumStrategy(),StrategyConfig(strategy_id='trend_momentum',weight=1.)); r.register(MeanReversionStrategy(),StrategyConfig(strategy_id='mean_reversion',weight=1.)); f=StrategyFactory(); f.register('trend_momentum',TrendMomentumStrategy); f.register('mean_reversion',MeanReversionStrategy); return r,f
def ctx(): return {'regime':{'success':True,'analysis':'market_regime','status':'EVALUATED','pair':'EURUSD','interval':'5m','timestamp_utc':T,'regime':'BULLISH_TREND','analysis_usable':True},'session':{'success':True,'analysis':'forex_session','status':'EVALUATED','timestamp_utc':T,'phase':'SINGLE_SESSION','active_sessions':['LONDON']},'operational_state':{'success':True,'analysis':'market_operational_state','status':'HEALTHY','pair':'EURUSD','interval':'5m','timestamp_utc':T,'analysis_usable':True}}
def test_snapshot():
 r,f=rf(); x=MarketIntelligenceEngine().evaluate(analysis(),registry=r,factory=f,**ctx()); assert x.status is IntelligenceStatus.EVALUATED; assert x.opportunity['analysis']=='trade_opportunity'; assert x.execution_authorized is False; assert x.evidence_fingerprint
def test_deterministic():
 r,f=rf(); e=MarketIntelligenceEngine(); a=e.evaluate(analysis(),registry=r,factory=f,**ctx()); b=e.evaluate(analysis(),registry=r,factory=f,**ctx()); assert a.to_dict()==b.to_dict()
def test_fingerprint_changes():
 r,f=rf(); a=analysis(); b=copy.deepcopy(a); b['indicators']['rsi']['value']=48.; e=MarketIntelligenceEngine(); assert e.evaluate(a,registry=r,factory=f,**ctx()).evidence_fingerprint!=e.evaluate(b,registry=r,factory=f,**ctx()).evidence_fingerprint
def test_identity_guard():
 r,f=rf(); bad=ctx(); bad['regime']=dict(bad['regime'],pair='GBPUSD');
 with pytest.raises(MarketIntelligenceError,match='regime pair'): MarketIntelligenceEngine().evaluate(analysis(),registry=r,factory=f,**bad)
def test_failed_analysis_rejected():
 r,f=rf(); a=analysis(); a['success']=False; x=MarketIntelligenceEngine().evaluate(a,registry=r,factory=f); assert x.status is IntelligenceStatus.REJECTED and not x.candidate
def test_no_execution_authorization():
 with pytest.raises(MarketIntelligenceError): MarketIntelligenceSnapshot(IntelligenceStatus.EVALUATED,'EURUSD','5m',T,{}, {},evidence_fingerprint='x',execution_authorized=True)
