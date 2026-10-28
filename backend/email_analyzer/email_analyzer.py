# 캐치피싱 이메일 탐지 엔진 (웹용)
# email_practice.ipynb의 analyze_email_sample을 웹용으로 옮기고 항목을 늘린 파일
# 결과는 README의 결과지 6칸 그대로 돌려준다.
# 배점은 B 확정 (10/24). 배점을 바꿀 때는 POINTS만 바꾸면 된다

import re
from email import message_from_string
from email.utils import parseaddr

POINTS = {  # 합계 100 (B 확정 10/24)
    "DMARC 실패": 28,
    "SPF 실패": 17,
    "DKIM 실패": 0,
    "표시 이름 위장": 17,
    "답장 주소 불일치": 17,
    "첨부 파일 위험": 11,
    "긴급성·압박 문구": 10,
}

# 우리 회사 공식 메일 주소 (게임 속 가상 회사, B 설계: company.example)
COMPANY_DOMAINS = {"company.example"}
# 회사 내부 부서처럼 보이게 하는 표시 이름에 자주 쓰이는 말
INTERNAL_WORDS = ["인사", "총무", "보안", "정보보안", "경영지원", "재무", "회계", "관리자"]
# 영어 부서 이름은 대문자 낱말로만 찾는다 (Smith의 ith, Chris의 hr 같은 오탐 방지, A 10/28)
INTERNAL_WORDS_EN = ["IT", "HR"]
# 위험한 첨부 확장자 (실행되는 파일)
DANGEROUS_EXT = (".lnk", ".exe", ".scr", ".js", ".vbs", ".bat", ".cmd", ".hta", ".iso")
# 서두르게 하거나 겁주는 말 (사례조사 유형 C)
URGENT_WORDS = ["오늘 중", "오늘 마감", "즉시", "긴급", "불이익", "벌금", "정지", "제한", "마감", "빠른 처리"]


def _looks_internal(display):
    """표시 이름이 회사 내부 부서처럼 보이면 True"""
    if any(w in display for w in INTERNAL_WORDS):
        return True
    # 앞뒤에 영어 글자가 붙어 있지 않을 때만 인정 (IT팀, HR 담당은 O / Smith, CHRIS는 X)
    return any(re.search(rf"(?<![A-Za-z]){w}(?![A-Za-z])", display) for w in INTERNAL_WORDS_EN)


def _domain(header_value):
    name, addr = parseaddr(header_value or "")
    return (addr.split("@")[-1].lower() if "@" in addr else None), name


def analyze_email(raw_text, filename="message.eml", attachment=None):
    """메일 원문을 분석해서 결과지 6칸을 돌려준다. attachment: 첨부 파일 이름 (없으면 None)"""
    if not raw_text or len(raw_text) > 50000:
        raise ValueError("메일 내용이 비어 있거나 너무 깁니다.")
    msg = message_from_string(raw_text)
    reasons, unavailable = [], []

    def add(factor, text):
        reasons.append({"factor": factor, "points": POINTS[factor], "text": text})

    # 1. 메일 인증 (메일 서버가 적어 둔 검사 결과를 읽음. 칸이 없으면 확인 못 함)
    auth = (msg.get("Authentication-Results") or "").lower()
    if not auth:
        unavailable.append("auth")
    else:
        if "dmarc=fail" in auth:
            add("DMARC 실패", "보낸 도메인의 메일 정책 검사(DMARC)에 실패했습니다. 회사 이름을 빌려 보냈을 가능성이 큽니다.")
        if "spf=fail" in auth or "spf=softfail" in auth:
            add("SPF 실패", "보낸 도메인이 허락하지 않은 서버에서 발송된 메일입니다.")
        if "dkim=fail" in auth:
            add("DKIM 실패", "메일의 전자 서명이 맞지 않습니다. 중간에 바뀌었거나 위조됐을 수 있습니다.")

    # 2. 표시 이름 위장: 이름은 회사 내부 부서인데 주소는 회사 도메인이 아님
    from_domain, display = _domain(msg.get("From"))
    if from_domain and from_domain not in COMPANY_DOMAINS and _looks_internal(display):
        add("표시 이름 위장", f"보낸 사람 이름은 회사 부서('{display}')처럼 보이지만 주소는 회사 도메인이 아닌 {from_domain} 입니다.")

    # 3. 답장 주소 불일치: 답장이 다른 곳으로 감
    reply_domain, _ = _domain(msg.get("Reply-To"))
    if from_domain and reply_domain and reply_domain != from_domain:
        add("답장 주소 불일치", f"답장하면 보낸 주소({from_domain})가 아닌 다른 곳({reply_domain})으로 갑니다.")

    # 4. 첨부 파일 위험: 실행 파일이거나 이중 확장자 (예: 문서.pdf.lnk)
    if attachment:
        low = attachment.lower()
        if low.endswith(DANGEROUS_EXT):
            add("첨부 파일 위험", f"첨부 파일 '{attachment}'은 문서처럼 보이지만 실행되는 파일입니다.")

    # 5. 긴급성·압박 문구 (본문과 제목)
    body = msg.get_payload() if not msg.is_multipart() else ""
    text = f"{msg.get('Subject') or ''} {body}"
    found = [w for w in URGENT_WORDS if w in text]
    if found:
        add("긴급성·압박 문구", f"\"{found[0]}\" 같은 말로 서두르게 하거나 겁을 줍니다.")

    return {
        "type": "email",
        "input": filename,
        "score": sum(r["points"] for r in reasons),
        "model_probability": None,
        "reasons": reasons,
        "unavailable": unavailable,
    }


def build_raw(card):
    """게임 시나리오 카드(scenarios.json)로 메일 원문을 만든다."""
    lines = [f"From: {card.get('from') or card.get('sender') or ''}"]
    if card.get("reply_to"):
        lines.append(f"Reply-To: {card['reply_to']}")
    lines.append(f"Subject: {card.get('subject') or ''}")
    if card.get("auth_results"):
        lines.append(f"Authentication-Results: mx.company.example; {card['auth_results']}")
    return "\n".join(lines) + "\n\n" + (card.get("body") or "") + "\n"
