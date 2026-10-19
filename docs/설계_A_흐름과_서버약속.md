# 설계 A: 전체 흐름과 서버 약속 (초안)

담당: A / 상태: 맞춰 보기 전 초안 (칸 이름은 `docs/AI_인수인계.md`의 칸 이름 사전 기준)

---

## 1. 화면 목록과 순서

### 직원이 보는 화면

```
① 시작 안내 → ② 문진표 → ③ 게임 ⇄ ④ 해설 → ⑤ 내 결과 → ⑥ 링크 직접 검사
                          (시나리오마다 반복)
```

| 번호 | 화면 | 보이는 것 | 부르는 서버 약속 |
|---|---|---|---|
| ① | 시작 안내 | "이 체험은 평가가 아니며 결과는 익명으로 모입니다", 시작 버튼 | 없음 |
| ② | 문진표 | 자가 체크 질문 4개(B 설계), 마지막에 직군 선택 | 1 `/api/start` |
| ③ | 게임 | 메일·문자·링크 한 개, 행동 버튼 3개 | 2 `/api/answer` |
| ④ | 해설 | "당했습니다 / 안전합니다", 위험 점수와 이유, 확인할 점(clues), 다음 버튼 | 없음 (③의 답장으로 표시) |
| ⑤ | 내 결과 | 자신감과 실제의 차이, 약한 유형, 습관 팁 | 3 `/api/result` |
| ⑥ | 링크 직접 검사 | 링크 입력 칸, 검사 버튼, 결과 | 4 `/api/check-url` |

### 회사 담당자가 보는 화면

| 번호 | 화면 | 보이는 것 | 부르는 서버 약속 |
|---|---|---|---|
| ⑦ | 관리자 입장 | 회사 코드 입력 칸 | 5 `/api/admin/stats` (코드가 맞으면 ⑧로) |
| ⑧ | 통계 | 참여 인원, 직군별 오답률, 많이 속은 유형, 자신감 vs 실제, 과잉 의심 비율, 기록 검사 버튼 | 5 `/api/admin/stats`, 6 `/api/admin/verify` |

### 설계 이유

- **이름 대신 익명 번호(`anon_id`):** 직원이 평가받는다고 느끼지 않게 하고, 개인정보를 남기지 않기 위해
- **③에서 서버가 그 자리에서 분석:** 신청서의 "AI가 실시간으로 분석하는 과정을 체험"을 구현. 결과지(JSON 6칸)가 해설에 그대로 쓰임
- **④는 서버에 다시 묻지 않음:** ③의 답장에 해설 재료가 다 들어 있어 주고받는 횟수가 줄어듦
- **관리자에게 개인 결과는 안 보임:** 직원이 체험을 꺼리지 않게. 교육에는 직군별 경향이면 충분
- **⑥ 링크 직접 검사:** 게임 후에도 실생활에서 계속 쓰는 기능 → 실용성·지속가능성 근거

---

## 2. 서버 약속(API) 목록

| 번호 | 주소 | 언제 | 화면 → 서버 | 서버 → 화면 |
|---|---|---|---|---|
| 1 | `POST /api/start` | 문진표 제출 | `self_check`, `job` | `anon_id`, `scenarios`(풀 시나리오 목록) |
| 2 | `POST /api/answer` | 행동을 고를 때마다 | `anon_id`, `scenario_id`, `choice` | `is_correct`, `over_suspicion`, `is_phishing`, `analysis`, `clues`, `explanation` |
| 3 | `POST /api/result` | 게임 끝 | `anon_id` | `played`, `wrong`, `confidence`, `gap_message`, `weak_types`, `tips` |
| 4 | `POST /api/check-url` | 링크 직접 검사 | `url` | `analysis` |
| 5 | `POST /api/admin/stats` | 관리자 통계 | `company_code` | `participants`, `wrong_rate_by_job`, `weak_types`, `confidence_gap`, `over_suspicion_rate` |
| 6 | `POST /api/admin/verify` | 기록 검사 버튼 | `company_code` | C의 `verify_chain` 결과 그대로 |
| 7 | (서버 내부) | 2번이 올 때마다 | — | 장부에 한 줄 기록 (C의 `build_entry`) |

### 1번 예시: 시작

화면 → 서버
```json
{ "self_check": { "Q1": 4, "Q2": "있었지만 그냥 지웠다", "Q3": "official", "Q4": "있다" }, "job": "hr" }
```

서버 → 화면 (정답 관련 칸은 빼고 보냄)
```json
{
  "anon_id": "U7F3A",
  "scenarios": [
    {
      "scenario_id": "S06",
      "channel": "sms",
      "sender": "정부24 / 010-0000-0000",
      "subject": null,
      "body": "[정부24] 민생 지원금 신청 대상자입니다. ...",
      "link": "https://gov24-support.example/app",
      "attachment": null
    }
  ]
}
```

### 2번 예시: 행동 선택 (가장 중요)

화면 → 서버
```json
{ "anon_id": "U7F3A", "scenario_id": "S06", "choice": "click" }
```

서버 → 화면
```json
{
  "is_correct": false,
  "over_suspicion": false,
  "is_phishing": true,
  "analysis": {
    "type": "url",
    "input": "https://gov24-support.example/app",
    "score": 60,
    "model_probability": null,
    "reasons": [
      { "factor": "도메인 유사", "points": 35, "text": "정부기관 이름('gov')을 따라 했지만 진짜 정부 주소가 아닙니다." },
      { "factor": "기관명 불일치", "points": 15, "text": "공공기관 이름을 내세웠지만 주소 끝이 정부 공식 주소(.go.kr)가 아닙니다." },
      { "factor": "URL 구조", "points": 10, "text": "하이픈(-)이 들어간 주소입니다. 기관이나 회사 이름에 단어를 이어 붙여 꾸몄을 가능성이 있습니다." }
    ],
    "unavailable": ["whois"]
  },
  "clues": ["기관 사칭 + 지원금 미끼", "앱 설치 유도", "gov가 들어간 주소지만 정부 주소가 아님"],
  "explanation": "문자 → 가짜 설치 페이지 → 가짜 문서 뷰어 앱 → 2차 악성 앱으로 이어지는 연쇄형 공격입니다."
}
```

- `analysis`는 README의 결과지 6칸 그대로. 링크가 있는 카드는 링크를, 이메일 카드는 헤더(`from`, `reply_to`, `auth_results`)로 만든 메일 원문을 탐지 엔진에 넣는다.
- 링크도 헤더도 없는 카드(예: 전화 유도 메일)는 `analysis`를 `null`로 보내고, 해설은 `clues`와 `explanation`으로만 보여준다.

### 채점 규칙 (팀 결정)

| 시나리오 | `click` | `call` | `official` |
|---|---|---|---|
| 피싱 (`is_phishing: true`) | 오답 | 오답 | 정답 |
| 정상 (`is_phishing: false`) | 정답 | 정답 | 정답, `over_suspicion: true` |

### 설계 이유

- **정답은 미리 보내지 않음:** 1번 시나리오 목록에서 `is_phishing`, `clues`, `explanation`을 빼서, 브라우저 개발자 도구로 정답을 엿볼 수 없게 한다.
- **채점은 서버가 함:** 화면은 고른 행동만 보내고 맞았는지는 서버가 판단한다. 장부 기록을 믿을 수 있게 하기 위해.
- **입력 검증:** `choice`는 `click`·`call`·`official`만, `job`은 직군 코드 5개만, `scenario_id`는 그 사람에게 준 목록 안에서만 받는다. `url`은 길이를 제한하고, **접속하지 않고** 주소와 등록 정보만 분석한다.
- **관리자 요청에는 매번 `company_code`:** 로그인을 만들지 않기로 했으므로(팀 결정), 코드가 맞을 때만 통계와 검사 결과를 돌려준다. 코드는 저장소에 적지 않고 Vercel 환경 변수에 둔다.

### 장부 한 줄에 넣을 것 (C와 맞춰 볼 초안)

```json
{
  "anon_id": "U7F3A",
  "job": "hr",
  "self_check": { "Q1": 4, "Q2": "...", "Q3": "official", "Q4": "있다" },
  "scenario_id": "S06",
  "case_type": "A+D",
  "is_phishing": true,
  "choice": "click",
  "is_correct": false,
  "over_suspicion": false,
  "analysis": { "...결과지 6칸..." }
}
```
C의 `build_entry(prev_entry, record)`의 `record` 자리에 이것을 넣으면 `seq`, `prev_hash`, `created_at`, `hash`는 C의 코드가 붙인다.

---

## 3. 화면과 서버가 결과지(JSON 6칸)를 쓰는 곳

| 결과지 칸 | 쓰는 곳 |
|---|---|
| `score` | ④ 해설, ⑥ 링크 검사 |
| `reasons` | ④ 해설("왜 위험한지"), ⑥, 관리자 통계의 약한 유형 계산 |
| `unavailable` | ④, ⑥에 "확인하지 못한 항목" 안내 (화면에는 B의 표시 이름으로) |
| `model_probability` | `null`이면 화면에서 숨김, 모델이 붙으면 표시 |
| 결과지 전체 | 장부에 통째로 저장 (C) |

---

## 4. 탐지 엔진과 시나리오 맞추기 규칙

시나리오 링크를 지금 엔진에 넣어 본 결과 (10/19):

| 시나리오 | 링크 | 점수 |
|---|---|---|
| S06 정부24 지원금 | `gov24-support.example/app` | 60 |
| S04 텔레그램 사칭 | `taiegram-login.example/verify` | 20 |
| S01 건강보험 사칭 | `health-notice.example/check` | 10 |

**규칙 제안:** 시나리오를 만들면 링크를 엔진에 넣어 본다. 피싱인데 점수가 너무 낮으면 A가 엔진을 보완하고(하이픈으로 나눈 단어마다 철자 비교, 기관 이름 목록 확대, 본문 긴급성 키워드), 그래도 안 되면 B가 시나리오를 조정한다.

---

## 5. Vercel 배포를 위한 폴더 구조 (초안)

```
api/
  index.py                  ← 서버 입구. 서버 약속 1~6을 받는 곳 (Flask)
backend/
  url_analyzer/
    url_analyzer.py         ← 링크 탐지 엔진 (노트북의 analyze_url_v2를 옮김)  [A]
  email_analyzer/
    email_analyzer.py       ← 이메일 탐지 엔진 (노트북의 analyze_email_sample을 옮김)  [B]
  db_logs/
    hashchain.py            ← 해시체인 (이미 있음)  [C]
    ledger.py               ← DB에 기록 저장·불러오기  [C]
    stats.py                ← 통계·맞춤 피드백 계산  [C]
scenarios/
  scenarios.json            ← 시나리오 카드 (정답·clues 포함, 서버만 읽음)  [B]
frontend/                   ← 화면 HTML·JS  [B]
requirements.txt            ← 서버가 쓰는 파이썬 도구 목록
vercel.json                 ← Vercel 설정
```

- Vercel은 요청이 올 때만 잠깐 켜지므로 **기록은 파일이 아니라 외부 PostgreSQL**에 저장한다(팀 결정).
- DB 주소, 회사 코드, (나중에) 해시 비밀 열쇠는 **Vercel 환경 변수**에만 둔다. 저장소에 올리지 않는다.
- 화면 파일 위치(`frontend/`를 그대로 쓸지, Vercel 기본 위치로 옮길지)와 `api/index.py`, `vercel.json`의 정확한 작성법은 **Vercel 공식 문서로 확인한 뒤** 확정한다.
- whois 조회는 짧은 시간 제한을 두고, 실패하면 `unavailable`에 적는다.

---

## 6. 팀 논의 포인트

1. **장부 한 줄 칸**(2번 아래 초안)이 C의 설계와 맞는지
2. **시나리오 카드에서 화면으로 보내는 칸**(1번 예시)이 B의 카드 양식과 맞는지. 이메일 카드에 `from`, `reply_to`, `auth_results` 칸 추가 여부
3. **링크·헤더가 없는 카드**는 `analysis: null`로 두고 해설만 보여줄지
4. **회사 코드:** 시연용 1개로 할지, 회사별로 나눌지 (지금 제안: 1개)
5. **엔진·시나리오 맞추기 규칙**(4번) 채택 여부
6. **자신감 기준:** 문진표 Q1에서 몇 점 이상을 "자신 있다"로 볼지 (제안: 4점 이상)
