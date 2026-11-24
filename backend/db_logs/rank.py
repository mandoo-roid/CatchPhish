# -*- coding: utf-8 -*-
"""rank.py (A 11/24): 자유 훈련 순위표. 한 사람(게임 번호) 한 줄, 최고 점수만 남긴다.

하는 일: 점수를 받으면 그 사람의 최고 점수보다 높을 때만 바꾼다. 위에서부터 몇 명을 돌려준다.
이유: 전시 때 "1등 기록 깨기" 경품 (A 11/24). 한 사람이 여러 판 해도 순위표가 그 사람으로 가득 차지 않게.
참고: 게임 기록(game_logs)과 다른 표(rankings)다. 연결 방법은 game_log.py와 같다.
      제작팀 기록은 이 표에 넣지 않고 서버 코드(api/index.py)의 TEAM_RECORD로 둔다. 지워지거나 덮이지 않게.
"""
import os
import sqlite3
from datetime import datetime, timezone

try:
    import psycopg
except ImportError:
    psycopg = None

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rankings (
    player  TEXT PRIMARY KEY,
    nick    TEXT NOT NULL,
    score   INTEGER NOT NULL,
    updated TEXT NOT NULL
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


def submit(player: str, nick: str, score: int) -> dict:
    """점수를 낸다. 돌려주는 것: {"best": 이 사람 최고 점수, "improved": 이번에 최고 점수가 올랐는지}"""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        cur.execute(f"SELECT score FROM rankings WHERE player = {ph}", (player,))
        row = cur.fetchone()
        prev = row[0] if row else None
        now = datetime.now(timezone.utc).isoformat()
        if prev is None or score > prev:
            cur.execute(
                f"INSERT INTO rankings (player, nick, score, updated) VALUES ({ph}, {ph}, {ph}, {ph}) "
                "ON CONFLICT (player) DO UPDATE SET nick = excluded.nick, score = excluded.score, updated = excluded.updated",
                (player, nick, score, now))
        else:
            # 점수는 그대로 두고 별명만 바꾼다 (별명을 고쳤을 수 있으니)
            cur.execute(f"UPDATE rankings SET nick = {ph} WHERE player = {ph}", (nick, player))
        conn.commit()
        return {"best": max(score, prev or 0), "improved": prev is None or score > prev}
    finally:
        conn.close()


def top(n: int = 10) -> list:
    """높은 점수부터 n명. 점수가 같으면 먼저 낸 사람이 위."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        conn.commit()
        cur.execute(f"SELECT player, nick, score FROM rankings ORDER BY score DESC, updated ASC LIMIT {ph}", (n,))
        return [{"player": p, "nick": k, "score": s} for p, k, s in cur.fetchall()]
    finally:
        conn.close()
