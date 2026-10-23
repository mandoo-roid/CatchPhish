# 캐치피싱 링크 탐지 엔진 (웹용)
# url_practice.ipynb의 analyze_url_sample + analyze_url_v2를 하나로 합치고 보완한 파일
# 결과는 README의 결과지 6칸(type, input, score, model_probability, reasons, unavailable) 그대로 돌려준다.
# 링크에 접속하지 않는다. 주소 모양과 도메인 등록 정보만 본다.

import datetime
import socket

import Levenshtein
import tldextract

# 하는 일: 인터넷에서 목록을 받지 않고, 설치할 때 들어 있는 주소 끝자리 목록만 쓰게 함
# 이유: Vercel 서버는 파일을 저장할 수 없고 잠깐만 켜져서, 매번 목록을 받으면 느리고 실패할 수 있음
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# 유명 이름 목록: 철자를 흉내 낸 가짜 주소를 잡을 때 비교함 (사례조사에서 나온 것부터, 나중에 늘리기)
BRANDS = ["naver", "kakao", "google", "telegram", "coupang", "microsoft"]

# 진짜 공식 주소 목록: 여기에 있으면 유명 이름이 들어 있어도 진짜로 봄
# 이유: kakaocorp.com처럼 진짜 회사 주소를 가짜로 오해하지 않게 하려고
OFFICIAL_DOMAINS = {
    "naver.com", "kakao.com", "kakaocorp.com", "google.com", "telegram.org",
    "coupang.com", "microsoft.com", "gov.kr",
}

# 정부기관 이름: 도메인 유사(35점)에 씀
GOV_WORDS = ["gov", "minwon"]

# 공공기관을 뜻하는 단어: 기관명 불일치(15점)에 씀 (임시, 팀 논의로 늘리기)
# nhis = 국민건강보험공단, health = 건강보험·건강검진 사칭, police = 경찰, tax = 세금
ORG_WORDS = ["gov", "minwon", "nhis", "health", "police", "tax"]

# 인증·로그인을 유도하는 단어: 키워드(10점)에 씀
KEYWORDS = ["verify", "login", "signin", "account", "secure", "update", "confirm", "check"]

MAX_URL_LENGTH = 2000  # 너무 긴 입력은 받지 않음 (서버 보호)


def _is_real_gov(ext):
    # 하는 일: 진짜 정부 주소인지 확인 (예: minwon.go.kr, www.gov.kr)
    return ext.suffix == "go.kr" or (ext.domain == "gov" and ext.suffix == "kr")


def _creation_days(registered_domain):
    # 하는 일: 도메인이 만들어진 지 며칠 됐는지 조회. 실패하면 None
    # 이유: 조회 실패는 0점이 아니라 unavailable에 적는다 (README 약속 3번)
    try:
        import whois
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(4)  # 4초 안에 답이 없으면 포기 (서버가 오래 멈추지 않게)
        try:
            info = whois.whois(registered_domain)
        finally:
            socket.setdefaulttimeout(old)
        created = info.creation_date
        if isinstance(created, list):
            created = created[0]
        if created is None:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - created).days
    except Exception:
        return None


def analyze_url(url, use_whois=True):
    """링크 하나를 분석해서 결과지 6칸을 돌려준다."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise ValueError("링크가 비어 있거나 너무 깁니다.")
    if "://" not in url:
        url = "http://" + url  # 'naver.com'처럼 앞부분 없이 넣어도 분석되게

    reasons, unavailable = [], []
    ext = _extract(url)
    name = ext.domain.lower()
    if not name:
        raise ValueError("링크에서 사이트 주소를 찾지 못했습니다.")
    registered = f"{ext.domain}.{ext.suffix}".lower() if ext.suffix else name
    is_official = registered in OFFICIAL_DOMAINS or _is_real_gov(ext)

    # 주소 조각 모으기: 이름 + 앞부분을 점(.)과 하이픈(-)으로 잘게 나눔
    # 예: taiegram-login.example → ["example", "taiegram-login", "taiegram", "login"]
    labels = [name] + [p.lower() for p in ext.subdomain.split(".") if p]
    tokens = []
    for label in labels:
        tokens.append(label)
        tokens.extend(t for t in label.split("-") if t)

    if not is_official:
        # 1. 도메인 유사 (35점): 유명 이름·정부 이름이 들어 있거나 철자만 살짝 다름
        for word in BRANDS + GOV_WORDS:
            hit = any(word in t for t in tokens)
            # 철자 비교는 5글자 이상 조각만 (짧은 조각은 우연히 비슷할 수 있어서)
            near = any(len(t) >= 5 and t != word and Levenshtein.distance(t, word) <= 2 for t in tokens)
            if hit or (word in BRANDS and near):
                if word in GOV_WORDS:
                    text = f"정부기관 이름('{word}')을 따라 했지만 진짜 정부 주소가 아닙니다."
                else:
                    text = f"유명 이름('{word}')과 비슷하지만 똑같지는 않은 도메인입니다."
                reasons.append({"factor": "도메인 유사", "points": 35, "text": text})
                break

        # 2. 기관명 불일치 (15점): 공공기관 단어가 있는데 진짜 정부 주소가 아님
        if any(w in t for w in ORG_WORDS for t in tokens):
            reasons.append({"factor": "기관명 불일치", "points": 15,
                            "text": "공공기관 이름을 내세웠지만 주소 끝이 정부 공식 주소(.go.kr)가 아닙니다."})

        # 3. 키워드 (10점): 주소에 인증·로그인 유도 단어
        low = url.lower()
        found = [k for k in KEYWORDS if k in low]
        if found:
            reasons.append({"factor": "키워드", "points": 10,
                            "text": f"주소에 {', '.join(found[:2])}처럼 인증을 유도하는 단어가 들어 있습니다."})

        # 4. URL 구조 (10점): 사이트 이름에 하이픈 (기준은 팀 논의 후 조정, 지금은 1개부터)
        host = ".".join(p for p in [ext.subdomain, ext.domain, ext.suffix] if p)
        if "-" in host:
            reasons.append({"factor": "URL 구조", "points": 10,
                            "text": "하이픈(-)이 들어간 주소입니다. 기관이나 회사 이름에 단어를 이어 붙여 꾸몄을 가능성이 있습니다."})

    # 5. 생성일 (30점): 만든 지 30일 미만이면 점수. 조회 실패는 unavailable
    days = _creation_days(registered) if (use_whois and ext.suffix) else None
    if days is None:
        unavailable.append("whois")
    elif days < 30 and not is_official:
        reasons.append({"factor": "생성일", "points": 30,
                        "text": f"도메인이 만들어진 지 {days}일밖에 안 됐습니다."})

    return {
        "type": "url",
        "input": url,
        "score": sum(r["points"] for r in reasons),  # README 약속 1번: 이유 점수의 합
        "model_probability": None,  # AI 모델은 다음 단계에서 연결
        "reasons": reasons,
        "unavailable": unavailable,
    }
