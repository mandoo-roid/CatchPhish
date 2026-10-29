# -*- coding: utf-8 -*-
"""stats.py (C): 장부 기록 목록으로 관리자 통계를 계산한다.

- 하는 일: load_entries()가 돌려준 기록 목록을 받아, 관리자 화면(/admin)이 기다리는 모양의 dict를 만든다.
- 이유: 서버 약속 5번(/api/admin/stats). 기록이 쌓여도 숫자로 요약하는 코드가 없으면 화면에 보여 줄 수 없다.
- 참고: DB에 직접 접속하지 않는다. 기록 목록만 받아서 계산하므로 Colab에서 가짜 기록으로 시험할 수 있다.
"""

# 하는 일: 유형 이름. 서버(api/index.py)의 CASE_NAMES와 같은 이름을 쓴다
CASE_NAMES = {"A": "기관 사칭", "B": "도메인 위조", "C": "심리 압박", "D": "연쇄형 공격"}

# 하는 일: 직군을 보여 줄 순서 (팀 결정 직군 5개)
JOB_ORDER = ["hr", "finance", "sales", "dev", "office"]

# 하는 일: 한 직군의 참여 인원이 이 숫자보다 적으면 그 직군의 오답률은 숨긴다
# 이유: 인원이 너무 적으면 한 사람의 결과가 그대로 드러난다 (팀 논의 포인트, 지금은 3명)
MIN_GROUP = 3

# 하는 일: 자신감 기준. Q1이 이 점수 이상이면 "자신 있다" (서버 /api/result와 같은 기준, 팀 확정)
CONFIDENT_MIN = 4


def _rate(part, whole):
    # 하는 일: 비율(0~1)을 구한다. 전체가 0이면 0이 아니라 None
    # 이유: 기록이 없는데 0%로 보여 주면 거짓 정보가 된다
    return round(part / whole, 3) if whole else None


def _records(entries):
    # 하는 일: 장부 기록 목록에서 쓸 수 있는 record만 꺼낸다
    # 이유: 옛 시험 기록처럼 칸이 빠진 기록이 있어도 통계 계산이 멈추지 않게 한다
    for e in entries:
        r = e.get("record") if isinstance(e, dict) else None
        if (isinstance(r, dict) and isinstance(r.get("anon_id"), str)
                and isinstance(r.get("is_correct"), bool)):
            yield r


def _q1(record):
    # 하는 일: 문진표 Q1(자신감, 1~5)을 꺼낸다. 값이 이상하면 None
    sc = record.get("self_check")
    q1 = sc.get("Q1") if isinstance(sc, dict) else None
    if isinstance(q1, int) and not isinstance(q1, bool) and 1 <= q1 <= 5:
        return q1
    return None


def compute_stats(entries):
    """장부 기록 목록 -> 관리자 통계 dict (api/index.py admin_stats 주석의 모양)."""
    recs = list(_records(entries))

    # --- 참여 인원: 서로 다른 anon_id 수
    participants = len({r["anon_id"] for r in recs})

    # --- 직군별 오답률 (인원이 MIN_GROUP명 미만인 직군은 목록에서 뺀다)
    by_job = {}
    for r in recs:
        j = by_job.setdefault(r.get("job"), {"people": set(), "answers": 0, "wrong": 0})
        j["people"].add(r["anon_id"])
        j["answers"] += 1
        j["wrong"] += 0 if r["is_correct"] else 1
    jobs = [j for j in JOB_ORDER if j in by_job] + sorted(
        j for j in by_job if j not in JOB_ORDER and isinstance(j, str))
    wrong_rate_by_job = {
        j: _rate(by_job[j]["wrong"], by_job[j]["answers"])
        for j in jobs if len(by_job[j]["people"]) >= MIN_GROUP
    }

    # --- 많이 속은 유형: 틀린 기록의 case_type을 "+"로 나눠 유형마다 센다 (서버와 같은 방식)
    counts = {}
    for r in recs:
        if r["is_correct"]:
            continue
        for t in (r.get("case_type") or "").split("+"):
            if t in CASE_NAMES:
                counts[t] = counts.get(t, 0) + 1
    weak_types = [{"type": CASE_NAMES[t], "count": counts[t]}
                  for t in sorted(counts, key=lambda t: (-counts[t], t))]

    # --- 자신감 vs 실제: Q1 4점 이상("자신 있다")과 3점 이하의 오답률 비교
    conf = {"answers": 0, "wrong": 0}
    unconf = {"answers": 0, "wrong": 0}
    for r in recs:
        q1 = _q1(r)
        if q1 is None:
            continue
        g = conf if q1 >= CONFIDENT_MIN else unconf
        g["answers"] += 1
        g["wrong"] += 0 if r["is_correct"] else 1
    confidence_gap = {
        "confident_wrong_rate": _rate(conf["wrong"], conf["answers"]),
        "unconfident_wrong_rate": _rate(unconf["wrong"], unconf["answers"]),
    }

    # --- 과잉 의심 비율: 정상 메시지 기록 중 over_suspicion이 참인 비율
    # 참고: 카드 파일이 아니라 기록의 is_phishing을 본다 (S08이 예전엔 피싱, 지금은 정상이라 섞이지 않게)
    normal = [r for r in recs if r.get("is_phishing") is False]
    over = sum(1 for r in normal if r.get("over_suspicion") is True)

    return {
        "connected": True,
        "participants": participants,
        "wrong_rate_by_job": wrong_rate_by_job,
        "weak_types": weak_types,
        "confidence_gap": confidence_gap,
        "over_suspicion_rate": _rate(over, len(normal)),
    }
