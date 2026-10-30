# -*- coding: utf-8 -*-
"""test_feedback.py: 정해 둔 입력에 맞는 팁이 나오는지 시험한다. (Colab에서 실행)"""
from feedback import make_tips, TYPE_TIPS, CALL_TIP, PRAISE

A, B, C, D = (TYPE_TIPS[t] for t in "ABCD")

# 1) 하나도 안 틀렸으면 칭찬 한 줄
assert make_tips({}, {}) == [PRAISE]
assert make_tips(None, None) == [PRAISE]
print("시험 1 통과: 전부 맞히면 칭찬")

# 2) 횟수가 같으면 A, B, C, D 순서 (A+C 시나리오는 A와 C가 늘 같이 오른다)
assert make_tips({"A": 2, "C": 2}, {"click": 2}) == [A, C]
assert make_tips({"D": 1, "B": 1}, {"click": 2}) == [B, D]
print("시험 2 통과: 같은 횟수면 A, B, C, D 순서")

# 3) 더 많이 틀린 유형이 먼저
assert make_tips({"C": 3, "A": 1}, {"click": 4}) == [C, A]
print("시험 3 통과: 많이 틀린 유형이 먼저")

# 4) 전화로 속은 적이 있으면 두 번째 자리는 전화 팁
assert make_tips({"A": 1, "C": 1}, {"call": 1}) == [A, CALL_TIP]
assert make_tips({"D": 1}, {"call": 1}) == [D, CALL_TIP]
print("시험 4 통과: 전화로 속으면 전화 팁")

# 5) 틀린 유형이 하나뿐이고 전화도 아니면 팁 한 개
assert make_tips({"B": 1}, {"click": 1}) == [B]
print("시험 5 통과: 팁이 하나일 수도 있음")

# 6) 모르는 유형·이상한 값은 건너뜀, 팁은 최대 2개
assert make_tips({"X": 3, "A": 1}, {"click": 1}) == [A]
assert make_tips({"A": 1, "B": 1, "C": 1, "D": 1}, {"call": 1}) == [A, CALL_TIP]
assert len(make_tips({"A": 1, "B": 1, "C": 1, "D": 1}, {"click": 4})) == 2
assert make_tips({"A": "많이", "C": -1}, {}) == [PRAISE]
print("시험 6 통과: 이상한 값은 건너뛰고 최대 2개")

# 7) 문장이 짧은지 (일반 직원이 한눈에 읽도록 한 문장씩, 60자 이하)
for t in list(TYPE_TIPS.values()) + [CALL_TIP, PRAISE]:
    assert len(t) <= 60, (len(t), t)
print("시험 7 통과: 모든 문장이 60자 이하")
print("모든 시험 통과")
