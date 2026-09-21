from market.mongodb_evidence_query import MongoTradeEvidenceQuery
from market.mongodb_journal import MongoTradeJournal
class FakeCursor:
    def __init__(self, documents): self.documents=list(documents)
    def sort(self, field, direction): self.documents.sort(key=lambda x:x.get(field,0), reverse=(direction==-1)); return self
    def limit(self, value): self.documents=self.documents[:value]; return self
    def __iter__(self): return iter(self.documents)
class FakeCollection:
    def __init__(self): self.docs={}
    def replace_one(self, q, replacement, upsert=False):
        key = q.get('_id')
        if key in self.docs or upsert:
            document = dict(replacement)
            document['_id'] = key
            self.docs[key] = document
    def find_one(self,q): return self.docs.get(q.get('_id'))
    def find(self,q): return FakeCursor([dict(d) for d in self.docs.values() if all(d.get(k)==v for k,v in q.items())])
    def count_documents(self,q): return sum(1 for d in self.docs.values() if all(d.get(k)==v for k,v in q.items()))
class FakeDatabase:
    def __init__(self): self.collections={'trade_evidence':FakeCollection()}
    def __getitem__(self,n): return self.collections[n]
class FakeAdmin:
    def command(self,n): return {'ok':1}
class FakeClient:
    def __init__(self): self.databases={'benvin':FakeDatabase()}; self.admin=FakeAdmin()
    def __getitem__(self,n): return self.databases[n]
def make_query():
    j=MongoTradeJournal(FakeClient())
    for d in ({'trade_id':'T-1','symbol':'EURUSD','status':'CONFIRMED','timestamp':1,'evidence_fingerprint':'fp-a'},{'trade_id':'T-2','symbol':'GBPUSD','status':'FAILED','timestamp':3,'evidence_fingerprint':'fp-b'},{'trade_id':'T-3','symbol':'EURUSD','status':'CONFIRMED','timestamp':2,'evidence_fingerprint':'fp-a'}): j.save(d)
    return MongoTradeEvidenceQuery(j)
def test_get_and_filtered_queries():
    q=make_query(); assert q.get('T-1')['symbol']=='EURUSD'; assert [x['trade_id'] for x in q.find_by_symbol('EURUSD')]==['T-3','T-1']; assert [x['trade_id'] for x in q.find_by_status('CONFIRMED')]==['T-3','T-1']; assert [x['trade_id'] for x in q.find_by_fingerprint('fp-a')]==['T-3','T-1']
def test_generic_find_and_count():
    q=make_query(); assert [x['trade_id'] for x in q.find({'symbol':'EURUSD'})]==['T-3','T-1']; assert q.count({'symbol':'EURUSD'})==2

def test_recent_and_count():
    q=make_query(); assert [x['trade_id'] for x in q.recent(2)]==['T-2','T-3']; assert q.count()==3; assert q.count({'symbol':'EURUSD'})==2
def test_invalid_inputs_are_rejected():
    q=make_query()
    for f in (q.get,q.find_by_symbol,q.find_by_status,q.find_by_fingerprint):
        try: f('')
        except ValueError: pass
        else: raise AssertionError('expected ValueError')
    try: q.recent(0)
    except ValueError: pass
    else: raise AssertionError('expected ValueError')
def test_query_layer_has_no_execution_authority():
    q=make_query(); assert not hasattr(q,'buy'); assert not hasattr(q,'sell'); assert not hasattr(q,'execute')
