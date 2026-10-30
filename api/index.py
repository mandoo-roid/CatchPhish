# 캐치피싱 서버 입구 (Vercel이 이 파일의 app을 실행함)
# 서버 약속 (docs/설계_A_흐름과_서버약속.md):
#   1 /api/start   2 /api/answer   3 /api/result   4 /api/check-url
# 5(관리자 통계)는 겉모양과 주소만 먼저 만들어 둠. 통계 계산은 C의 stats.py가 오면 채운다.
# 6(기록 검사): C의 hashchain.verify_chain으로 장부 전체를 다시 계산해 위변조를 검사한다 (A 10/28 연결).
# 8(연쇄형 단계): /api/chain. 연쇄형 카드의 2·3단계 행동을 받아 다음 단계나 해설을 돌려주고, 끝나면 장부에 한 줄 저장 (A 10/29).
# 7(장부 기록): 2번(/api/answer)에서 채점이 끝나면 C의 ledger.append_record로 장부에 한 줄 저장한다 (A 10/28).
# 결과(3번)는 지금처럼 화면이 보낸 선택 목록으로 서버가 다시 채점한다 (팀 결정 10/28).

import hmac
import json
import os
import random
import re
import secrets
import sys

from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "url_analyzer"))
sys.path.insert(0, os.path.join(ROOT, "backend", "email_analyzer"))

from url_analyzer import analyze_url  # noqa: E402
from email_analyzer import analyze_email, build_raw, URGENT_WORDS  # noqa: E402

# 장부(DB) 저장 코드 (C의 ledger.py, hashchain.py)
# 하는 일: db_logs 폴더의 장부 코드를 불러온다
# 이유: 게임 기록을 해시체인 장부에 남기려고 (서버 약속 7번)
# 참고: 불러오기에 실패해도 게임은 그대로 돌아가게 try로 감쌌다 (팀 결정: 장부 저장이 실패해도 게임은 계속)
sys.path.insert(0, os.path.join(ROOT, "backend", "db_logs"))
try:
    from ledger import append_record, load_entries  # noqa: E402
    from hashchain import verify_chain  # noqa: E402
    LEDGER_READY = True
except Exception as e:  # noqa: BLE001
    print("장부 코드 불러오기 실패:", type(e).__name__)
    LEDGER_READY = False

# 맞춤 피드백 코드 (C의 feedback.py)
# 하는 일: 결과 화면 "이렇게 해 보세요" 문장을 고른다. 불러오기에 실패하면 아래 CASE_TIPS(임시)로 그대로 동작한다
try:
    from feedback import make_tips  # noqa: E402
except Exception as e:  # noqa: BLE001
    print("feedback 불러오기 실패:", type(e).__name__)
    make_tips = None

# 관리자 통계 계산 코드 (C의 stats.py)
# 하는 일: 장부 기록 목록을 관리자 화면용 숫자로 바꾸는 compute_stats를 불러온다
# 이유: 서버 약속 5번 (/api/admin/stats)
# 참고: 장부 코드와 따로 감쌌다. 통계 코드에 문제가 생겨도 게임 기록 저장과 기록 검사는 그대로 돌아간다
try:
    from stats import compute_stats  # noqa: E402
    STATS_READY = True
except Exception as e:  # noqa: BLE001
    print("통계 코드 불러오기 실패:", type(e).__name__)
    STATS_READY = False

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


ANON_ID = re.compile(r"^U[0-9A-F]{6}$")  # /api/start가 만드는 익명 번호 모양
SURVEY_KEYS = ("Q1", "Q2", "Q3", "Q4")


def save_to_ledger(data, card, choice, ok, over, analysis, stopped_step=None):
    # 하는 일: 장부 한 줄(10칸, 설계 A "장부 한 줄에 넣을 것")을 만들어 C의 append_record로 저장한다
    # 이유: 서버 약속 7번. 관리자 통계와 기록 검사가 이 장부를 쓴다
    # 참고: 화면이 직군·문진표를 안 보내면(옛 화면) 저장하지 않고 넘어간다. 저장이 실패해도 게임은 계속하고 서버 로그에만 남긴다
    if not LEDGER_READY:
        return False
    anon, job, sc = data.get("anon_id"), data.get("job"), data.get("self_check")
    if not (isinstance(anon, str) and ANON_ID.match(anon) and job in JOBS and isinstance(sc, dict)):
        return False
    # 하는 일: 문진표는 Q1~Q4만, 짧은 값만 남긴다 / 이유: 정해진 값만 받는다는 보안 원칙
    self_check = {k: sc[k] for k in SURVEY_KEYS if isinstance(sc.get(k), (int, str)) and len(str(sc[k])) <= 60}
    record = {
        "anon_id": anon, "job": job, "self_check": self_check,
        "scenario_id": card["scenario_id"], "case_type": card.get("case_type"),
        "is_phishing": card["is_phishing"], "choice": choice,
        "is_correct": ok, "over_suspicion": over, "analysis": analysis,
    }
    # 하는 일: 연쇄형 카드면 몇 단계에서 멈췄는지(stopped_step)를 함께 남긴다 (A 10/29 결정)
    # 참고: 연쇄형이 아닌 카드 기록에는 이 칸을 넣지 않는다. 값 1·2·3 = 그 단계에서 멈춤, 0 = 멈추지 못함 (choice로 click·call 구분)
    if stopped_step is not None:
        record["stopped_step"] = stopped_step
    try:
        append_record(record)
        return True
    except Exception as e:  # noqa: BLE001
        # 참고: DB 주소가 로그에 남지 않게 오류 종류와 앞부분만 적는다
        print("장부 저장 실패:", type(e).__name__, str(e)[:120])
        return False


def bad(msg):
    return jsonify({"error": msg}), 400


CHAIN_PUBLIC = ["title", "body", "continue_label", "stop_label"]  # 단계 화면에 보여 줄 칸 (해설은 끝날 때만)


def chain_step(card, step):
    # 하는 일: 연쇄형 카드의 step단계(2부터) 화면 내용을 해설 없이 돌려준다
    # 이유: 정답·해설은 미리 보내지 않는다는 보안 원칙. 단계 해설은 체험이 끝날 때 서버가 보낸다
    info = card["chain"][step - 2]
    return {"scenario_id": card["scenario_id"], "step": step, **{k: info.get(k) for k in CHAIN_PUBLIC}}


def final_answer(card, ok, over, analysis, explanation, logged, stopped_step=None):
    # 하는 일: 해설 화면에 필요한 답을 한 모양으로 만든다 (2번 answer와 연쇄형 chain이 함께 씀)
    text_clues = [w for w in URGENT_WORDS if w in (card.get("body") or "")] if card.get("channel") == "sms" else []
    out = {
        "is_correct": ok,
        "over_suspicion": over,
        "is_phishing": card["is_phishing"],
        "analysis": analysis,
        "clues": card["clues"],
        "explanation": explanation,
        "logged": logged,  # 장부에 저장됐는지 (확인용)
        "text_clues": text_clues,  # 문자 본문에서 찾은 압박 문구 (점수와 별도)
    }
    if stopped_step is not None:
        out["stopped_step"] = stopped_step
    return out


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
    analysis = analyze_card(card)
    # 하는 일: 연쇄형 체험을 아는 새 화면(chain: true)이 연쇄형 카드에서 '링크 열기'를 고르면, 해설 대신 2단계 화면을 돌려준다
    # 이유: 연쇄형(D)은 단계를 직접 겪으며 배우게 하려고 (10/28 제안, B 문장 확정 10/29)
    # 참고: 장부에는 체험이 끝난 뒤 /api/chain에서 한 줄만 저장한다. 옛 화면은 chain을 안 보내서 지금처럼 동작한다
    is_chain = bool(data.get("chain")) and bool(card.get("chain"))
    if is_chain and data["choice"] == "click":
        return jsonify({"chain_step": chain_step(card, 2)})
    stopped = ({"official": 1, "call": 0}.get(data["choice"]) if is_chain else None)
    logged = save_to_ledger(data, card, data["choice"], ok, over, analysis, stopped)
    # 문자 카드의 본문 압박 문구(text_clues)는 final_answer에서 함께 만든다 (A 10/29, 점수·결과지·장부와 별도)
    return jsonify(final_answer(card, ok, over, analysis, card["explanation"], logged, stopped))


@app.post("/api/chain")
def chain():
    # 서버 약속 8번(새로 추가): 연쇄형 카드의 2·3단계에서 고른 행동을 받아 다음 단계나 마지막 해설을 돌려준다
    # 하는 일: action이 stop이면 그 단계에서 멈춤, continue면 다음 단계로. 마지막 단계에서 continue면 끝까지 진행(0)
    # 이유: 연쇄형(D) 체험. 채점은 지금 규칙 그대로라 2단계 이후는 모두 오답(1단계 공식 확인만 정답)
    # 참고: 서버는 기억하지 않는다. 화면이 보낸 단계 번호를 믿는다 (결과 3번과 같은 방식)
    data = request.get_json(silent=True) or {}
    card = SCENARIOS.get(data.get("scenario_id"))
    if card is None or not card.get("chain"):
        return bad("연쇄형 카드가 아닙니다.")
    last = len(card["chain"]) + 1  # 마지막 단계 번호 (1단계 + 추가 단계 수)
    step, action = data.get("step"), data.get("action")
    if not isinstance(step, int) or not 2 <= step <= last or action not in ("continue", "stop"):
        return bad("단계 번호나 행동이 맞지 않습니다.")
    if action == "continue" and step < last:
        return jsonify({"chain_step": chain_step(card, step + 1)})
    info = card["chain"][step - 2]
    if action == "stop":
        stopped, explanation = step, info.get("stop_explanation") or card["explanation"]
    else:
        stopped, explanation = 0, info.get("end_explanation") or card["explanation"]
    ok, over = grade(card, "click")
    analysis = analyze_card(card)
    logged = save_to_ledger(data, card, "click", ok, over, analysis, stopped)
    return jsonify(final_answer(card, ok, over, analysis, explanation, logged, stopped))


@app.get("/favicon.ico")
def favicon():
    # 하는 일: 사이트 아이콘 요청에 '내용 없음'으로 답한다 / 이유: 브라우저 개발자 도구의 빨간 오류(404)를 없애려고
    return "", 204


def job_compare(job, anon, wrong, played):
    # 하는 일: 장부에 쌓인 같은 직군 사람들의 평균 오답률과 내 오답률을 함께 돌려준다 (A 10/30)
    # 이유: 신청서 ⑤ "집계 결과 기반 개인별 맞춤 피드백". 내 결과를 전체 집계와 비교해 보여 주려고
    # 참고: 평균에는 내 기록을 넣지 않는다. 계산은 관리자 통계와 같은 C의 compute_stats를 쓰므로,
    #       같은 직군이 3명 미만이면 평균이 없어 None(화면에 안 나옴). 장부를 못 읽어도 결과 화면은 그대로 나온다
    if job not in JOBS or not (LEDGER_READY and STATS_READY) or not played:
        return None
    try:
        others = [e for e in load_entries()
                  if not (isinstance(e.get("record"), dict) and e["record"].get("anon_id") == anon)]
        avg = compute_stats(others)["wrong_rate_by_job"].get(job)
    except Exception as e:  # noqa: BLE001
        print("직군 비교 계산 실패:", type(e).__name__)
        return None
    if avg is None:
        return None
    return {"avg": avg, "mine": round(wrong / played, 3)}


@app.post("/api/result")
def result():
    # 서버 약속 3번: DB 연결 전이라 화면이 보낸 선택 목록으로 다시 채점해 결과를 만든다
    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    q1 = (data.get("self_check") or {}).get("Q1")
    if not isinstance(answers, list) or not answers or not isinstance(q1, int) or not 1 <= q1 <= 5:
        return bad("결과를 계산할 정보가 부족합니다.")
    wrong, over, missed, wrong_choices = 0, 0, {}, {}
    for a in answers:
        card = SCENARIOS.get(a.get("scenario_id")) if isinstance(a, dict) else None
        if card is None or a.get("choice") not in CHOICES:
            return bad("선택 목록이 올바르지 않습니다.")
        ok, o = grade(card, a["choice"])
        over += o
        if not ok:
            wrong += 1
            wrong_choices[a["choice"]] = wrong_choices.get(a["choice"], 0) + 1
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
        "job_compare": job_compare(data.get("job"), data.get("anon_id"), wrong, played),
        "played": played,
        "correct": correct,
        "wrong": wrong,
        "over_suspicion": over,
        "confidence": q1,
        "accuracy": round(correct / played * 100),
        "gap_message": gap,
        "weak_types": [CASE_NAMES[t] for t in weak if t in CASE_NAMES],
        "tips": make_tips(missed, wrong_choices) if make_tips else [CASE_TIPS[t] for t in weak if t in CASE_TIPS][:2],
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
    # 서버 약속 5번: 장부 전체를 불러와 C의 compute_stats로 계산한 결과를 그대로 돌려준다
    # 돌려주는 모양 (설계 A 기준, C의 stats.py):
    # {"connected": true, "participants": 37,
    #  "wrong_rate_by_job": {"hr": 0.42, ...},          # 직군별 오답률 (0~1). 인원 3명 미만 직군은 빠짐
    #  "weak_types": [{"type": "기관 사칭", "count": 21}, ...],   # 많이 속은 유형
    #  "confidence_gap": {"confident_wrong_rate": 0.38, "unconfident_wrong_rate": 0.29},  # 자신감 vs 실제
    #  "over_suspicion_rate": 0.18}                       # 정상 메시지 과잉 의심 비율
    # 참고: 기록이 없어서 계산할 수 없는 비율은 0이 아니라 null로 온다. 회사 코드가 맞아야 계산한다
    data = request.get_json(silent=True) or {}
    err = _check_company_code(data)
    if err:
        return err
    if not (LEDGER_READY and STATS_READY):
        return jsonify({"connected": False, "message": "장부나 통계 코드를 불러오지 못해 통계를 보여 줄 수 없습니다."})
    try:
        return jsonify(compute_stats(load_entries()))
    except Exception as e:  # noqa: BLE001
        # 참고: DB 주소가 로그에 남지 않게 오류 종류와 앞부분만 적는다
        print("통계 계산 실패:", type(e).__name__, str(e)[:120])
        return jsonify({"error": "통계를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}), 500


@app.post("/api/admin/verify")
def admin_verify():
    # 서버 약속 6번: 장부 전체를 불러와 C의 verify_chain으로 검사한 결과를 그대로 돌려준다
    # 하는 일: 이상 없으면 {"ok": true, "count": 개수}, 문제가 있으면 {"ok": false, "broken_seq": 번호, "reason": 이유}
    # 이유: 기록이 몰래 바뀌거나 중간에 지워졌는지 관리자가 직접 확인하게 하려고 (증적 로그)
    # 참고: 관리자 화면(admin.html)은 이 모양을 이미 보여 줄 수 있다. 회사 코드가 맞아야 검사한다
    data = request.get_json(silent=True) or {}
    err = _check_company_code(data)
    if err:
        return err
    if not LEDGER_READY:
        return jsonify({"connected": False, "message": "장부 코드를 불러오지 못해 검사할 수 없습니다."})
    try:
        return jsonify(verify_chain(load_entries()))
    except Exception as e:  # noqa: BLE001
        print("기록 검사 실패:", type(e).__name__, str(e)[:120])
        return jsonify({"error": "기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}), 500
