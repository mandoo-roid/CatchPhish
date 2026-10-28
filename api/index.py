# 캐치피싱 서버 입구 (Vercel이 이 파일의 app을 실행함)
# 서버 약속 (docs/설계_A_흐름과_서버약속.md):
#   1 /api/start   2 /api/answer   3 /api/result   4 /api/check-url
# 5, 6(관리자)은 겉모양과 주소만 먼저 만들어 둠. 통계 계산·장부 검사는 C의 DB 연결 뒤에 채운다.
# 7(장부 기록)은 C의 DB 연결 뒤에 추가한다.
# 지금은 DB가 없어서 서버가 기록을 저장하지 않는다. 결과(3번)는 화면이 보낸 선택 목록으로 서버가 다시 채점한다.

import hmac
import json
import os
import random
import secrets
import sys

from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "url_analyzer"))
sys.path.insert(0, os.path.join(ROOT, "backend", "email_analyzer"))

from url_analyzer import analyze_url  # noqa: E402
from email_analyzer import analyze_email, build_raw  # noqa: E402

app = Flask(__name__)
FRONTEND = os.path.join(ROOT, "frontend")

# 팀 결정 (인수인계서 6-1)
JOBS = {"hr", "finance", "sales", "dev", "office"}
CHOICES = {"click", "call", "official"}
CASE_NAMES = {"A": "기관 사칭", "B": "도메인 위조", "C": "심리 압박", "D": "연쇄형 공격"}
# 맞춤 피드백 문장 (임시. C가 정할 규칙으로 바꿀 자리)
CASE_TIPS = {
    "A": "기관이나 회사 이름이 보여도 믿기 전에, 그 기관의 대표번호나 공식 앱으로 직접 확인하세요.",
    "B": "주소를 한 글자씩 읽어 보세요. 진짜 이름과 한 글자만 달라도 가짜일 수 있어요.",
    "C": "\"오늘 중\", \"불이익\" 같은 말로 서두르게 하면 잠깐 멈추는 것부터 시작하세요.",
    "D": "앱 설치나 추가 입력을 요구하면 첫 단계에서 멈추세요. 한 번 누르면 다음 함정으로 이어져요.",
}

# 시나리오 카드 읽기 (B가 쓴 파일, 정답 포함이라 서버만 읽음)
with open(os.path.join(ROOT, "scenarios", "scenarios.json"), encoding="utf-8") as f:
    SCENARIOS = {s["scenario_id"]: s for s in json.load(f)["scenarios"]}

PUBLIC_FIELDS = ["scenario_id", "channel", "sender", "subject", "body", "link", "attachment"]


def pick_scenarios(job):
    # 하는 일: 공통 카드(job_group이 common)와 내 직군 카드만 골라 순서를 섞는다 (팀 결정: 공통 4 + 직군 1 = 5개)
    # 이유: 직군에 맞는 문제를 풀게 하고, 정상 메시지가 늘 같은 자리에 나와 위치를 외우는 일을 막으려고
    # 참고: 정답·채점은 scenario_id로 찾기 때문에 순서를 섞어도 채점에는 영향이 없다
    cards = [s for s in SCENARIOS.values() if s.get("job_group") in ("common", job)]
    random.shuffle(cards)
    return cards


def grade(card, choice):
    # 채점 규칙 (팀 결정): 피싱이면 official만 정답, 정상이면 모두 정답이고 official은 과잉 의심
    if card["is_phishing"]:
        return choice == "official", False
    return True, choice == "official"


def analyze_card(card):
    # 이메일 카드는 이메일 탐지 엔진, 링크가 있는 문자 카드는 링크 탐지 엔진으로 분석
    if card.get("channel") == "email":
        try:
            return analyze_email(build_raw(card), f"{card['scenario_id']}.eml", card.get("attachment"))
        except Exception:
            return None
    if card.get("link"):
        try:
            return analyze_url(card["link"])
        except Exception:
            return None
    return None


def bad(msg):
    return jsonify({"error": msg}), 400


@app.get("/")
def home():
    # 첫 화면: 체험 시작 / 링크 바로 검사 (설계 A 화면 순서)
    return send_from_directory(FRONTEND, "home.html")


@app.get("/check")
def check_page():
    # 링크 직접 검사 화면 (서버 약속 4번을 쓰는 화면)
    return send_from_directory(FRONTEND, "index.html")


@app.get("/game")
def game():
    return send_from_directory(FRONTEND, "game.html")


@app.get("/admin")
def admin_page():
    # 회사 담당자용 관리자 화면 (회사 코드로 입장)
    return send_from_directory(FRONTEND, "admin.html")


@app.post("/api/start")
def start():
    # 서버 약속 1번: 문진표 답과 직군을 받고, 익명 번호와 풀 시나리오(정답 빼고)를 돌려줌
    data = request.get_json(silent=True) or {}
    if data.get("job") not in JOBS:
        return bad("직군을 골라 주세요.")
    if not isinstance(data.get("self_check"), dict):
        return bad("문진표 답이 없습니다.")
    cards = [{k: s.get(k) for k in PUBLIC_FIELDS} for s in pick_scenarios(data["job"])]
    return jsonify({"anon_id": "U" + secrets.token_hex(3).upper(), "scenarios": cards})


@app.post("/api/answer")
def answer():
    # 서버 약속 2번: 고른 행동을 받아 서버가 채점하고, 해설 재료를 돌려줌
    data = request.get_json(silent=True) or {}
    card = SCENARIOS.get(data.get("scenario_id"))
    if card is None:
        return bad("없는 시나리오입니다.")
    if data.get("choice") not in CHOICES:
        return bad("행동은 click, call, official 중 하나여야 합니다.")
    ok, over = grade(card, data["choice"])
    return jsonify({
        "is_correct": ok,
        "over_suspicion": over,
        "is_phishing": card["is_phishing"],
        "analysis": analyze_card(card),
        "clues": card["clues"],
        "explanation": card["explanation"],
    })


@app.post("/api/result")
def result():
    # 서버 약속 3번: DB 연결 전이라 화면이 보낸 선택 목록으로 다시 채점해 결과를 만든다
    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    q1 = (data.get("self_check") or {}).get("Q1")
    if not isinstance(answers, list) or not answers or not isinstance(q1, int) or not 1 <= q1 <= 5:
        return bad("결과를 계산할 정보가 부족합니다.")
    wrong, over, missed = 0, 0, {}
    for a in answers:
        card = SCENARIOS.get(a.get("scenario_id")) if isinstance(a, dict) else None
        if card is None or a.get("choice") not in CHOICES:
            return bad("선택 목록이 올바르지 않습니다.")
        ok, o = grade(card, a["choice"])
        over += o
        if not ok:
            wrong += 1
            for t in (card.get("case_type") or "").split("+"):
                if t:
                    missed[t] = missed.get(t, 0) + 1
    played = len(answers)
    correct = played - wrong
    if q1 >= 4 and wrong > 0:
        gap = f"자신 있다고 하셨지만 이번엔 {wrong}번 속으셨어요."
    elif q1 <= 2 and wrong == 0:
        gap = "자신 없다고 하셨지만 모두 잘 막으셨어요."
    elif wrong == 0:
        gap = "모든 피싱을 잘 막으셨어요."
    else:
        gap = f"{played}문제 중 {wrong}번 속으셨어요."
    weak = sorted(missed, key=lambda t: -missed[t])
    return jsonify({
        "played": played,
        "correct": correct,
        "wrong": wrong,
        "over_suspicion": over,
        "confidence": q1,
        "accuracy": round(correct / played * 100),
        "gap_message": gap,
        "weak_types": [CASE_NAMES[t] for t in weak if t in CASE_NAMES],
        "tips": [CASE_TIPS[t] for t in weak if t in CASE_TIPS][:2],
    })


@app.post("/api/check-url")
def check_url():
    # 서버 약속 4번: 화면이 {"url": "..."}를 보내면 결과지 6칸을 돌려줌
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    if not isinstance(url, str):
        return bad("링크는 글자로 보내야 합니다.")
    try:
        return jsonify(analyze_url(url))
    except ValueError as e:
        return bad(str(e))
    except Exception:
        return jsonify({"error": "분석 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요."}), 500


# ───────── 관리자 (서버 약속 5, 6번) ─────────
# 회사 코드는 Vercel 환경 변수 COMPANY_CODE에만 둔다. 저장소·문서에 코드 값을 적지 않는다.

def _check_company_code(data):
    expected = os.environ.get("COMPANY_CODE")
    if not expected:
        return jsonify({"error": "관리자 화면이 아직 설정되지 않았습니다. (회사 코드 미설정)"}), 503
    given = data.get("company_code")
    if not isinstance(given, str) or not hmac.compare_digest(given, expected):
        return jsonify({"error": "회사 코드가 맞지 않습니다."}), 401
    return None


@app.post("/api/admin/stats")
def admin_stats():
    # 서버 약속 5번. C가 DB와 통계 계산을 연결하면 아래 "connected": False 부분을 채운다.
    # 채울 모양 (설계 A 기준):
    # {"connected": true, "participants": 37,
    #  "wrong_rate_by_job": {"hr": 0.42, ...},          # 직군별 오답률 (0~1)
    #  "weak_types": [{"type": "기관 사칭", "count": 21}, ...],   # 많이 속은 유형
    #  "confidence_gap": {"confident_wrong_rate": 0.38, "unconfident_wrong_rate": 0.29},  # 자신감 vs 실제
    #  "over_suspicion_rate": 0.18}                       # 정상 메시지 과잉 의심 비율
    data = request.get_json(silent=True) or {}
    err = _check_company_code(data)
    if err:
        return err
    return jsonify({"connected": False, "message": "기록 저장(DB)이 아직 연결되지 않아 통계가 없습니다."})


@app.post("/api/admin/verify")
def admin_verify():
    # 서버 약속 6번. C의 verify_chain 결과를 그대로 돌려줄 자리.
    data = request.get_json(silent=True) or {}
    err = _check_company_code(data)
    if err:
        return err
    return jsonify({"connected": False, "message": "기록 저장(DB)이 아직 연결되지 않아 검사할 장부가 없습니다."})
