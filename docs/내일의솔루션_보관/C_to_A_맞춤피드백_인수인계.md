# C → A 인수인계: 맞춤 피드백 연결 (10/30 C)

**한 줄 요약:** `CASE_TIPS`(임시)를 대체할 `feedback.py`를 C가 만들었고, 시험도 통과했어요. A는 `api/index.py`의 `result()`에 **3곳(약 10줄)**만 고치면 돼요. 화면(`game.html`)은 안 고쳐도 돼요.

## 0. 올리는 순서 (순서가 바뀌면 안 돼요)

1. **C**가 `backend/db_logs/feedback.py`, `test_feedback.py`를 올려요. 새 파일이라 **사이트는 바뀌지 않아요.**
2. **A**가 `api/index.py`를 고쳐요 (아래 2번). 이게 올라가야 사이트에 반영돼요.
3. A가 게임을 한 판 해서 확인해요 (아래 4번).

※ `feedback.py`가 없는 상태에서 2번만 먼저 올려도 **게임은 안 깨져요.** 불러오기 실패 시 기존 `CASE_TIPS`로 돌아가게 해 놨어요(ledger, stats 때와 같은 방식).

## 1. feedback.py가 하는 일

`make_tips(missed, wrong_choices)` 함수 하나예요. 서버 DB에 접속하지 않고 계산만 해요.

| 입력 | 뜻 | 예 |
|---|---|---|
| `missed` | 유형별 틀린 횟수 (`result()`가 이미 만들고 있는 값) | `{"A": 2, "C": 2}` |
| `wrong_choices` | **틀렸을 때** 고른 행동별 횟수 (새로 세야 함) | `{"click": 1, "call": 1}` |

돌려주는 값: **팁 문장 목록, 최대 2개** (`"tips"`에 그대로 넣으면 돼요. 화면은 이미 `r.tips`를 목록으로 그려요).

### 팁을 고르는 규칙

| 상황 | 결과 |
|---|---|
| 하나도 안 틀림 | 칭찬 한 줄 |
| 틀림 | ① 가장 많이 틀린 유형의 팁 |
| ② 두 번째 팁: 전화(`call`)로 속은 적이 있으면 | **전화 팁** ("적힌 번호로 전화하지 마세요…") |
| ② 전화로 속은 적이 없으면 | 두 번째로 많이 틀린 유형의 팁 |
| 틀린 횟수가 같을 때 | A, B, C, D 순서 |

문장은 모두 한 문장, 60자 이하예요 (일반 직원이 한눈에 읽도록). 문장은 **`feedback.py` 맨 위의 `TYPE_TIPS`, `CALL_TIP`, `PRAISE`**에 있어서, 문장만 고칠 때는 그 파일만 바꾸면 돼요.

## 2. A가 고칠 곳: `api/index.py` (3곳)

### (1) 불러오기 추가 — `# 관리자 통계 계산 코드 (C의 stats.py)` 줄 **바로 위**에 넣기

```python
# 맞춤 피드백 코드 (C의 feedback.py)
# 하는 일: 결과 화면 "이렇게 해 보세요" 문장을 고른다. 불러오기에 실패하면 아래 CASE_TIPS(임시)로 그대로 동작한다
try:
    from feedback import make_tips  # noqa: E402
except Exception as e:  # noqa: BLE001
    print("feedback 불러오기 실패:", type(e).__name__)
    make_tips = None

```

(`sys.path`에 `backend/db_logs`가 이미 들어 있어서 따로 경로를 더하지 않아도 돼요.)

### (2) `result()` 안에서 틀린 행동 세기 — 2줄 바꾸기

```python
# 바꾸기 전
    wrong, over, missed = 0, 0, {}
# 바꾼 뒤
    wrong, over, missed, wrong_choices = 0, 0, {}, {}
```

그리고 `if not ok:` 안의 `wrong += 1` 바로 아래에 한 줄 추가:

```python
        if not ok:
            wrong += 1
            wrong_choices[a["choice"]] = wrong_choices.get(a["choice"], 0) + 1   # 추가
            for t in (card.get("case_type") or "").split("+"):
```

### (3) `tips` 줄 바꾸기

```python
# 바꾸기 전
        "tips": [CASE_TIPS[t] for t in weak if t in CASE_TIPS][:2],
# 바꾼 뒤
        "tips": make_tips(missed, wrong_choices) if make_tips else [CASE_TIPS[t] for t in weak if t in CASE_TIPS][:2],
```

`CASE_TIPS`는 **지우지 마세요.** `feedback.py` 불러오기에 실패했을 때의 대비용이에요.

> 같은 내용을 `git apply`로 바로 적용할 수 있는 패치 파일(`api_index_feedback.patch`)도 같이 드려요. 적용해 볼 수 있는 줄 번호는 10/30 21:44 커밋(`6ed7220`) 기준이에요.

## 3. 안 바뀌는 것 (건드리지 마세요)

- `weak_types`(많이 속은 유형 이름), `gap_message`, 화면의 "이렇게 해 보세요" 영역: 그대로예요
- 장부에 저장되는 10칸, `stats.py`, `ledger.py`, `hashchain.py`: 영향 없어요
- 서버 약속의 응답 칸 이름: 그대로예요 (`tips`는 원래도 문장 목록)

## 4. 시험 결과와 확인 방법

**C가 한 시험 (Colab, 가짜 입력)**: `test_feedback.py` 7가지 모두 통과 (전부 맞힘 칭찬, 같은 횟수면 A→D 순서, 많이 틀린 유형 우선, 전화 팁, 팁 1개인 경우, 이상한 값 건너뜀, 문장 60자 이하).

**서버에 패치를 적용해 `/api/result`를 직접 호출한 시험 (10/30)**:

| 보낸 답 | 나온 tips |
|---|---|
| S01 click(틀림), S05 click(정상이라 정답) | 기관 사칭 팁, 심리 압박 팁 |
| S01 call(틀림), S04 click(틀림) | 심리 압박 팁(C가 2번 틀림), 전화 팁 |
| S01 official(정답), S05 click(정답) | 칭찬 한 줄 |

**A가 사이트에서 확인할 것** (`Ctrl+Shift+R` 새로고침 후)
1. 일부러 링크를 눌러 틀린 판 → 결과 화면 "이렇게 해 보세요"에 **유형 팁 2개**가 나오는지
2. 전화를 눌러 틀린 판 → 두 번째 팁이 **전화 팁**인지
3. 전부 공식 경로 확인으로 간 판 → **칭찬 한 줄**이 나오는지 (이때 "많이 속은 유형" 제목은 원래 안 보여요)

## 5. 알아 둘 점

- **칭찬 문구는 "많이 속은 유형" 제목 없이 "이렇게 해 보세요" 아래에 나올 수 있어요.** 지금 `game.html`은 `weak_types`가 비면 그 영역 전체를 그리지 않아서(`if (r.weak_types.length)`), **전부 맞힌 판에서는 칭찬 팁이 화면에 안 나와요.** 칭찬을 보여 주고 싶으면 `renderResult`에서 팁 부분만 조건 밖으로 빼야 해요. (`game.html`은 A의 파일이라 A가 정해 주세요. 안 고쳐도 서버는 정상이고, 지금은 `gap_message`의 "모든 피싱을 잘 막으셨어요"가 대신 보여요.)
- `result()`는 아직 화면이 보낸 선택 목록으로 다시 채점해요(기존 팀 결정). 이 인수인계에서 바꾸지 않았어요.
- 팁 문장은 C가 정한 초안이에요. 팀(B 포함)이 읽고 어색하면 `feedback.py` 문장만 고치면 돼요.
- 교내 전시회용 "쉬운 버전"에서도 같은 `make_tips`를 쓸 수 있어요.

## 6. 파일 목록

| 파일 | 위치 | 누가 | 상태 |
|---|---|---|---|
| `feedback.py` | `backend/db_logs/` | C가 올림 | 새 파일, 사이트 영향 없음 |
| `test_feedback.py` | `backend/db_logs/` | C가 올림 | 시험용 |
| `api/index.py` | `api/` | **A**가 수정 | 3곳 |

문제가 생기면 오류 메시지를 그대로 C에게 전해 주세요.
