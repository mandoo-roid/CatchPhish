# 캐치피싱 서버 입구 (Vercel이 이 파일의 app을 실행함)
# 지금은 서버 약속 4번(링크 직접 검사)과 화면만 연결. 나머지 약속(1~3, 5~6)은 이어서 추가.

import os
import sys

from flask import Flask, jsonify, request, send_from_directory

# 하는 일: 저장소 맨 바깥 폴더 위치를 찾고, 링크 탐지 엔진 폴더를 불러올 수 있게 등록
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "url_analyzer"))

from url_analyzer import analyze_url  # noqa: E402  (위에서 경로를 등록한 뒤 불러와야 해서 여기에 둠)

app = Flask(__name__)
FRONTEND = os.path.join(ROOT, "frontend")


@app.get("/")
def home():
    # 하는 일: 주소로 들어오면 링크 검사 화면(frontend/index.html)을 보여줌
    return send_from_directory(FRONTEND, "index.html")


@app.post("/api/check-url")
def check_url():
    # 서버 약속 4번: 화면이 {"url": "..."}를 보내면 결과지 6칸을 돌려줌
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    if not isinstance(url, str):
        return jsonify({"error": "링크는 글자로 보내야 합니다."}), 400
    try:
        return jsonify(analyze_url(url))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "분석 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요."}), 500
