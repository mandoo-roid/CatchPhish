# -*- coding: utf-8 -*-
"""feedback.py (C): 결과 화면의 "이렇게 해 보세요" 문장을 고른다.

- 하는 일: 어떤 유형을 몇 번 틀렸는지, 어떤 행동으로 틀렸는지를 받아 짧은 팁을 최대 2개 돌려준다.
- 이유: A가 임시로 만든 CASE_TIPS는 "가장 많이 틀린 유형 2개의 문장"만 보여 줬다. 여기에 행동(전화) 기준 팁과 모두 맞힌 경우의 칭찬을 더했다.
- 참고: 서버·DB에 접속하지 않는 계산 함수다. 새 파일이라 올려도 사이트가 바뀌지 않는다. A가 api/index.py의 result()에서 호출해야 쓰인다.
"""

# 하는 일: 유형별 팁 (한 문장, 행동 하나). 유형 이름은 서버 CASE_NAMES와 같다: A 기관 사칭, B 도메인 위조, C 심리 압박, D 연쇄형
TYPE_TIPS = {
    "A": "기관이나 회사 이름이 보여도 믿지 말고, 공식 앱이나 대표번호로 직접 확인하세요.",
    "B": "주소를 한 글자씩 읽어 보세요. 한 글자만 달라도 가짜일 수 있어요.",
    "C": "‘오늘 중’, ‘불이익’처럼 서두르게 하는 말이 보이면 일단 멈추세요.",
    "D": "앱 설치나 정보 입력을 요구하면 거기서 멈추세요. 한 번 누르면 다음 함정으로 이어져요.",
}

# 하는 일: 유형이 아니라 "행동"을 보고 고르는 팁 (적힌 번호로 전화해서 틀린 경우)
CALL_TIP = "적힌 번호로 전화하지 마세요. 공식 대표번호를 직접 찾아 거세요."

# 하는 일: 하나도 안 속았을 때 보여 줄 칭찬
# 참고: A 10/30 수정. 예전 문장("의심될 땐 … 확인하는 습관을 이어 가세요")은 "모두 확인하라"로 읽힐 수 있어서, 근거를 보고 판단한 점을 칭찬하는 문장으로 바꿈
PRAISE = "잘 막으셨어요. 보낸 곳과 요구하는 행동을 보고 판단한 게 정확했어요."

ORDER = "ABCD"   # 틀린 횟수가 같을 때 먼저 보여 줄 순서
MAX_TIPS = 2     # 짧고 핵심적으로: 화면에는 최대 2개


def make_tips(missed, wrong_choices=None):
    """missed: 유형별 틀린 횟수 {"A": 2, "C": 2} (A+C는 A와 C에 각각 1, 서버가 이미 이렇게 셈)
    wrong_choices: 틀렸을 때 고른 행동별 횟수 {"click": 1, "call": 1}
    -> 팁 문장 목록 (최대 2개). 하나도 안 틀렸으면 칭찬 한 줄."""
    # 하는 일: 모르는 유형이나 0번은 버린다 (이상한 값이 와도 멈추지 않게)
    missed = {t: n for t, n in (missed or {}).items() if t in TYPE_TIPS and isinstance(n, int) and n > 0}
    called = (wrong_choices or {}).get("call", 0)

    if not missed and not called:
        return [PRAISE]

    # 하는 일: 가장 많이 틀린 유형부터, 횟수가 같으면 A, B, C, D 순서
    types = sorted(missed, key=lambda t: (-missed[t], ORDER.index(t)))
    tips = []
    if types:
        tips.append(TYPE_TIPS[types[0]])         # 1번 팁: 가장 많이 속은 유형
    if called:
        tips.append(CALL_TIP)                    # 2번 팁: 전화로 속은 적이 있으면 이 팁이 먼저
    elif len(types) > 1:
        tips.append(TYPE_TIPS[types[1]])         # 아니면 두 번째로 많이 속은 유형
    return tips[:MAX_TIPS]
