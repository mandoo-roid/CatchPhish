# -*- coding: utf-8 -*-
"""game_log.py (A 11/20): 자유 훈련 게임 기록을 장부와 따로 모은다.

하는 일: 한 판이 끝날 때 점수, 정확도, 틀렸다가 다시 나온 문자를 맞힌 수 등을 표 하나에 남긴다.
이유: 게임의 교육 효과(즉각 교정, 판을 거듭할수록 정확도)를 시범 운영 숫자로 보여 주려고 (교수님·A 11/20).
참고: 팀 결정 16번 "게임 점수는 장부에 넣지 않는다"를 지키려고 장부(ledger)와 다른 표(game_logs)에 둔다.
      위변조 검사(해시체인)는 하지 않는다. 체험 기록과 섞이지 않고, 관리자 통계·기록 검사에도 들어가지 않는다.
      연결 방법은 ledger_v2와 같다 (DATABASE_URL이 있으면 PostgreSQL, 없으면 SQLite 파일).
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

try:
    import psycopg
except ImportError:
    psycopg = None

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS game_logs (
    created_at TEXT NOT NULL,
    record     TEXT NOT NULL
)
"""


def _connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        if psycopg is None:
            raise RuntimeError("DATABASE_URL이 있는데 psycopg가 설치되어 있지 않습니다.")
        return psycopg.connect(url), "%s"
    path = os.environ.get("LEDGER_SQLITE", "ledger_test.db")
    return sqlite3.connect(path, timeout=30), "?"


def append_game(record: dict) -> None:
    """한 판 기록을 저장한다."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        cur.execute(f"INSERT INTO game_logs (created_at, record) VALUES ({ph}, {ph})",
                    (datetime.now(timezone.utc).isoformat(), json.dumps(record, ensure_ascii=False, sort_keys=True)))
        conn.commit()
    finally:
        conn.close()


def load_games() -> list:
    """저장된 판 기록 전체를 오래된 것부터 돌려준다. 표가 없으면 빈 목록."""
    conn, _ = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        conn.commit()
        cur.execute("SELECT created_at, record FROM game_logs ORDER BY created_at")
        return [{"created_at": c, "record": json.loads(r)} for c, r in cur.fetchall()]
    finally:
        conn.close()
