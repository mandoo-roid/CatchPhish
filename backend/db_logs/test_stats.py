# -*- coding: utf-8 -*-
"""test_stats.py: 가짜 기록으로 stats.py 계산을 손계산 결과와 비교한다. (Colab에서 실행)"""
import os, tempfile
os.environ.pop("DATABASE_URL", None)
os.environ["LEDGER_SQLITE"] = os.path.join(tempfile.mkdtemp(), "stats_test.db")

from stats import compute_stats
from ledger import append_record, load_entries


def rec(anon, job, q1, sid, case_type, is_phishing, correct, over=False):
    return {"anon_id": anon, "job": job, "self_check": {"Q1": q1, "Q2": "x", "Q3": "x", "Q4": "x"},
            "scenario_id": sid, "case_type": case_type, "is_phishing": is_phishing,
            "choice": "click", "is_correct": correct, "over_suspicion": over, "analysis": None}


records = [
    # hr 3명 (오답률이 보이는 직군)
    rec("U1", "hr", 5, "S01", "A+C", True, False), rec("U1", "hr", 5, "S02", "B", True, True), rec("U1", "hr", 5, "S05", None, False, True),
    rec("U2", "hr", 4, "S01", "A+C", True, False), rec("U2", "hr", 4, "S02", "B", True, False), rec("U2", "hr", 4, "S05", None, False, True, over=True),
    rec("U3", "hr", 2, "S01", "A+C", True, True),  rec("U3", "hr", 2, "S02", "B", True, True),  rec("U3", "hr", 2, "S05", None, False, True),
    # dev 2명, finance 1명 (3명 미만이라 직군별 표에서 숨겨져야 함)
    rec("U4", "dev", 5, "S06", "A+D", True, False), rec("U4", "dev", 5, "S05", None, False, True),
    rec("U5", "dev", 3, "S06", "A+D", True, True),  rec("U5", "dev", 3, "S05", None, False, True, over=True),
    rec("U6", "finance", 1, "S01", "A+C", True, False), rec("U6", "finance", 1, "S05", None, False, True),
]

# --- 시험 1: 장부(SQLite)에 진짜로 저장했다가 읽어서 계산 (서버가 하는 순서 그대로)
for r in records:
    append_record(r)
s = compute_stats(load_entries())
print("시험 1 장부 저장 -> 읽기 -> 계산:", s)

assert s["connected"] is True
assert s["participants"] == 6                                   # U1~U6
assert s["wrong_rate_by_job"] == {"hr": 0.333}                  # hr 9건 중 3건 오답. dev·finance는 숨김
assert s["weak_types"] == [{"type": "기관 사칭", "count": 4},    # A: S01x3(+S06 U4) = 4
                           {"type": "심리 압박", "count": 3},    # C: S01 오답 3건
                           {"type": "도메인 위조", "count": 1},  # B: 1건 (동률이면 A,B,C,D 순서)
                           {"type": "연쇄형 공격", "count": 1}]  # D: 1건
assert s["confidence_gap"] == {"confident_wrong_rate": 0.5,     # Q1>=4: 8건 중 4건 오답
                               "unconfident_wrong_rate": 0.143} # Q1<=3: 7건 중 1건 오답
assert s["over_suspicion_rate"] == 0.333                        # 정상 6건 중 2건
print("시험 1 통과: 손계산과 같음")

# --- 시험 2: 기록이 하나도 없을 때 (0%가 아니라 None)
e = compute_stats([])
assert e["participants"] == 0 and e["wrong_rate_by_job"] == {} and e["weak_types"] == []
assert e["over_suspicion_rate"] is None
assert e["confidence_gap"] == {"confident_wrong_rate": None, "unconfident_wrong_rate": None}
print("시험 2 통과: 빈 장부는 None")

# --- 시험 3: 칸이 빠졌거나 이상한 기록이 섞여도 멈추지 않음
bad = load_entries() + [{"record": {"anon_id": "X"}}, {"record": "문자열"}, {"seq": 99}, "이상한 값"]
assert compute_stats(bad)["participants"] == 6
print("시험 3 통과: 이상한 기록은 건너뜀")
print("모든 시험 통과")
