import os, sqlite3, threading, tempfile
os.environ.pop("DATABASE_URL", None)
os.environ["LEDGER_SQLITE"] = os.path.join(tempfile.mkdtemp(), "t.db")
from ledger import append_record, load_entries
from hashchain import verify_chain

def rec(i):
    return {"anon_id": "U7F3A", "job": "hr", "self_check": {"Q1": 4, "Q2": "있었지만 그냥 지웠다"},
            "scenario_id": f"S0{i%9+1}", "case_type": "A+D", "is_phishing": True, "choice": "click",
            "is_correct": False, "over_suspicion": False,
            "analysis": {"type": "url", "input": "x.example", "score": 60, "model_probability": 0.8,
                         "reasons": [{"factor": "f", "points": 10, "text": "한글 이유"}], "unavailable": []}}

for i in range(5): append_record(rec(i))
print("1) 5건 저장 후 검증:", verify_chain(load_entries()))

db = os.environ["LEDGER_SQLITE"]
c = sqlite3.connect(db)
c.execute("UPDATE ledger SET record = replace(record,'\"is_correct\":false','\"is_correct\":true') WHERE seq=2"); c.commit()
print("2) DB에서 2번 몰래 수정:", verify_chain(load_entries()))
c.execute("UPDATE ledger SET record = replace(record,'\"is_correct\":true','\"is_correct\":false') WHERE seq=2"); c.commit()
c.execute("DELETE FROM ledger WHERE seq=3"); c.commit(); c.close()
print("3) DB에서 3번 삭제:", verify_chain(load_entries()))

os.environ["LEDGER_SQLITE"] = os.path.join(tempfile.mkdtemp(), "t2.db")
errs = []
def work(n):
    try:
        for j in range(8): append_record(rec(n*8+j))
    except Exception as e: errs.append(repr(e))
ts = [threading.Thread(target=work, args=(n,)) for n in range(5)]
[t.start() for t in ts]; [t.join() for t in ts]
es = load_entries()
print("4) 동시 5명x8건:", len(es), "건, 오류", errs[:2], verify_chain(es))
