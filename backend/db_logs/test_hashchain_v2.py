import hashlib, os, sqlite3, tempfile, threading

os.environ.pop("DATABASE_URL", None)
os.environ.pop("HASH_SECRET", None)


def newdb():
    os.environ["LEDGER_SQLITE"] = os.path.join(tempfile.mkdtemp(), "t.db")
    return os.environ["LEDGER_SQLITE"]


from ledger_v2 import append_record, load_entries, load_head, verify_ledger
from hashchain_v2 import verify_chain, canonical, compute_head_mac

ok_all = True


def check(name, cond, got):
    global ok_all
    ok_all &= bool(cond)
    print(("통과 " if cond else "실패 ") + name, "->", got)


def rec(i):
    return {"anon_id": "U7F3A", "job": "hr", "self_check": {"Q1": 4}, "scenario_id": f"S0{i%9+1}",
            "case_type": "A+D", "is_phishing": True, "choice": "click", "is_correct": False,
            "over_suspicion": False, "analysis": {"type": "url", "reasons": [{"text": "한글 이유"}]}}


def fill(n=5):
    for i in range(n):
        append_record(rec(i))


def attacker_recompute(db):
    """열쇠를 모르는 사람이 DB를 직접 열어 장부 전체의 지문을 SHA-256으로 다시 계산해 바꿔 놓는다."""
    c = sqlite3.connect(db)
    rows = c.execute("SELECT seq, record, created_at FROM ledger ORDER BY seq").fetchall()
    prev = "0" * 64
    last = None
    for seq, record, created_at in rows:
        body = canonical({"seq": seq, "prev_hash": prev, "record": __import__("json").loads(record),
                          "created_at": created_at})
        h = hashlib.sha256(body.encode()).hexdigest()
        c.execute("UPDATE ledger SET prev_hash=?, hash=? WHERE seq=?", (prev, h, seq))
        prev, last = h, (seq, h)
    c.execute("UPDATE ledger_head SET last_seq=?, last_hash=?, head_mac=? WHERE id=1",
              (last[0], last[1], hashlib.sha256(canonical({"kind": "head", "last_seq": last[0],
                                                           "last_hash": last[1]}).encode()).hexdigest()))
    c.commit(); c.close()


# ---- 열쇠 없는 모드(Colab) ----
db = newdb(); fill()
r = verify_ledger(); check("1) 5건 저장 후 검증", r == {"ok": True, "count": 5}, r)

c = sqlite3.connect(db)
c.execute("UPDATE ledger SET record = replace(record,'\"is_correct\":false','\"is_correct\":true') WHERE seq=2"); c.commit()
r = verify_ledger(); check("2) 2번 몰래 수정", (not r["ok"]) and r["broken_seq"] == 2, r)
c.execute("UPDATE ledger SET record = replace(record,'\"is_correct\":true','\"is_correct\":false') WHERE seq=2"); c.commit()
c.execute("DELETE FROM ledger WHERE seq=3"); c.commit()
r = verify_ledger(); check("3) 중간(3번) 삭제", (not r["ok"]) and r["broken_seq"] == 3, r)

db = newdb(); fill()
c = sqlite3.connect(db); c.execute("DELETE FROM ledger WHERE seq=5"); c.commit(); c.close()
old = verify_chain(load_entries())          # 예전 방식(head 안 넘김)
new = verify_ledger()
check("4-a) 끝(5번) 삭제를 예전 방식은 못 잡음", old["ok"] is True, old)
check("4-b) 끝(5번) 삭제를 새 방식은 잡음", (not new["ok"]) and "끝 기록이 삭제" in new["reason"], new)

db = newdb(); fill()
c = sqlite3.connect(db); c.execute("DELETE FROM ledger"); c.commit(); c.close()
new = verify_ledger(); check("5) 장부 전체 삭제도 잡음", not new["ok"], new)

# head를 지우거나 바꾸기
db = newdb(); fill()
c = sqlite3.connect(db); c.execute("DELETE FROM ledger_head"); c.commit(); c.close()
new = verify_ledger(); check("6) head 표를 지우면 잡음", not new["ok"], new)

# 열쇠 없이는 '끝 삭제 + head 되돌리기'를 못 잡음(한계 확인용 출력)
db = newdb(); fill()
c = sqlite3.connect(db)
prev = c.execute("SELECT seq, hash FROM ledger WHERE seq=4").fetchone()
c.execute("DELETE FROM ledger WHERE seq=5")
c.execute("UPDATE ledger_head SET last_seq=?, last_hash=?, head_mac=? WHERE id=1",
          (prev[0], prev[1], compute_head_mac(prev[0], prev[1]))); c.commit(); c.close()
new = verify_ledger()
print("참고) 열쇠 없는 모드에서 '끝 삭제 + head 되돌리기':", new, "(열쇠가 없으면 못 잡는 게 정상)")

# ---- 열쇠 있는 모드(사이트) ----
os.environ["HASH_SECRET"] = "시험용-열쇠-실제-값-아님"
db = newdb(); fill()
r = verify_ledger(); check("7) [열쇠] 5건 저장 후 검증", r == {"ok": True, "count": 5}, r)

attacker_recompute(db)
r = verify_ledger(); check("8) [열쇠] 열쇠 없이 장부 전체 다시 계산 -> 잡음", not r["ok"], r)

db = newdb(); fill()
c = sqlite3.connect(db)
prev = c.execute("SELECT seq, hash FROM ledger WHERE seq=4").fetchone()
c.execute("DELETE FROM ledger WHERE seq=5")
c.execute("UPDATE ledger_head SET last_seq=?, last_hash=?, head_mac=? WHERE id=1",
          (prev[0], prev[1], hashlib.sha256(canonical({"kind": "head", "last_seq": prev[0],
                                                       "last_hash": prev[1]}).encode()).hexdigest()))
c.commit(); c.close()
r = verify_ledger(); check("9) [열쇠] 끝 삭제 + head 되돌리기 -> 잡음", not r["ok"], r)

# 열쇠 없이 저장한 장부를 열쇠 켜고 검사하면 전부 변조(교체 때 장부를 비워야 하는 이유)
del os.environ["HASH_SECRET"]; db = newdb(); fill(3)
os.environ["HASH_SECRET"] = "시험용-열쇠-실제-값-아님"
r = verify_ledger(); check("10) 옛 장부를 열쇠 켠 채 검사 -> 1번부터 변조", (not r["ok"]) and r["broken_seq"] == 1, r)

# 동시 저장
db = newdb(); errs = []
def work(n):
    try:
        for j in range(8): append_record(rec(n * 8 + j))
    except Exception as e: errs.append(repr(e))
ts = [threading.Thread(target=work, args=(n,)) for n in range(5)]
[t.start() for t in ts]; [t.join() for t in ts]
r = verify_ledger(); h = load_head()
check("11) [열쇠] 동시 5명x8건", len(load_entries()) == 40 and not errs and r["ok"] and h["last_seq"] == 40, (r, errs[:2], h["last_seq"]))

print("\n전체 결과:", "모두 통과" if ok_all else "실패 있음")
