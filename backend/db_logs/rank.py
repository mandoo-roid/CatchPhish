# -*- coding: utf-8 -*-
"""rank.py (A 11/24): 자유 훈련 순위표. 한 사람(게임 번호) 한 줄, 최고 점수만 남긴다.

하는 일: 점수를 받으면 그 사람의 최고 점수보다 높을 때만 바꾼다. 위에서부터 몇 명을 돌려준다.
이유: 전시 때 "1등 기록 깨기" 경품 (A 11/24). 한 사람이 여러 판 해도 순위표가 그 사람으로 가득 차지 않게.
참고: 게임 기록(game_logs)과 다른 표(rankings)다. 연결 방법은 game_log.py와 같다.
      제작팀 기록은 이 표에 넣지 않고 서버 코드(api/index.py)의 TEAM_RECORD로 둔다. 지워지거나 덮이지 않게.
수정 (A 11/24, 작품 보안 점검 막기): 별명은 처음 정한 것으로 고정한다 (이미 있는 사람은 새 별명을 받지 않음).
      시작표(rank_tokens)는 한 번만 쓸 수 있게 기록한다. 같은 시작표로 점수를 여러 번 내는 공격을 막으려고.
수정 (A 11/25): 점수가 같으면 정확도가 높은 사람이 위 (그다음 먼저 낸 사람). 정확도 칸(acc, 천분율)을 더하면서 새 표 rankings_v2를 쓴다.
      예전 표 rankings는 지우지 않고 둔다 (11/24 막기 전 공격 기록이 남아 있는 증거).
"""
import os
import sqlite3
from datetime import datetime, timezone

try:
    import psycopg
except ImportError:
    psycopg = None

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rankings_v2 (
    player  TEXT PRIMARY KEY,
    nick    TEXT NOT NULL,
    score   INTEGER NOT NULL,
    acc     INTEGER NOT NULL,
    updated TEXT NOT NULL
)
"""


TOKEN_SQL = """
CREATE TABLE IF NOT EXISTS rank_tokens (
    nonce   TEXT PRIMARY KEY,
    used_at TEXT NOT NULL
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


def submit(player: str, nick: str, score: int, acc: int) -> dict:
    """점수를 낸다. acc는 정확도 천분율(0~1000). (점수, 정확도)가 이 사람 최고보다 높을 때만 바꾼다.
    돌려주는 것: {"best": 최고 점수, "best_acc": 그때 정확도, "improved": 이번에 올랐는지, "nick": 고정된 별명}"""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        cur.execute(f"SELECT score, acc, nick FROM rankings_v2 WHERE player = {ph}", (player,))
        row = cur.fetchone()
        if row:
            nick = row[2]   # 수정 (A 11/24): 이미 있는 사람은 처음 정한 별명을 그대로 쓴다 (별명 고정)
        improved = row is None or (score, acc) > (row[0], row[1])
        if improved:
            cur.execute(
                f"INSERT INTO rankings_v2 (player, nick, score, acc, updated) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}) "
                "ON CONFLICT (player) DO UPDATE SET score = excluded.score, acc = excluded.acc, updated = excluded.updated",
                (player, nick, score, acc, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        best = (score, acc) if improved else (row[0], row[1])
        return {"best": best[0], "best_acc": best[1], "improved": improved, "nick": nick}
    finally:
        conn.close()


def top(n: int = 10) -> list:
    """높은 점수부터 n명. 점수가 같으면 정확도가 높은 사람, 그것도 같으면 먼저 낸 사람이 위."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        conn.commit()
        cur.execute(f"SELECT player, nick, score, acc FROM rankings_v2 ORDER BY score DESC, acc DESC, updated ASC LIMIT {ph}", (n,))
        return [{"player": p, "nick": k, "score": s, "acc": a} for p, k, s, a in cur.fetchall()]
    finally:
        conn.close()
def nick_of(player: str):
    """이 사람이 이미 정한 별명. 없으면 None."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        conn.commit()
        cur.execute(f"SELECT nick FROM rankings_v2 WHERE player = {ph}", (player,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def other_nicks(player: str) -> list:
    """다른 사람들이 쓰는 별명 목록 (별명 중복 검사용)."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        conn.commit()
        cur.execute(f"SELECT nick FROM rankings_v2 WHERE player <> {ph}", (player,))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def claim_token(nonce: str) -> bool:
    """시작표를 처음 쓰면 True, 이미 쓴 시작표면 False."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(TOKEN_SQL)
        cur.execute(f"INSERT INTO rank_tokens (nonce, used_at) VALUES ({ph}, {ph}) ON CONFLICT (nonce) DO NOTHING",
                    (nonce, datetime.now(timezone.utc).isoformat()))
        ok = cur.rowcount == 1
        conn.commit()
        return ok
    finally:
        conn.close()


# ── 제작팀 기록 (A 11/25): 관리자 회사 코드로 결과 화면에서 바로 올린다 ──
TEAM_SQL = """
CREATE TABLE IF NOT EXISTS team_record (
    id      INTEGER PRIMARY KEY,
    score   INTEGER NOT NULL,
    acc     INTEGER NOT NULL,
    updated TEXT NOT NULL
)
"""


def get_team():
    """DB에 올린 제작팀 기록 (점수, 정확도 천분율). 없으면 None."""
    conn, _ = _connect()
    try:
        cur = conn.cursor()
        cur.execute(TEAM_SQL)
        conn.commit()
        cur.execute("SELECT score, acc FROM team_record WHERE id = 1")
        row = cur.fetchone()
        return (row[0], row[1]) if row else None
    finally:
        conn.close()


def set_team(score: int, acc: int) -> None:
    """제작팀 기록을 바꾼다 (높은지 확인은 부르는 쪽에서)."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(TEAM_SQL)
        cur.execute(f"INSERT INTO team_record (id, score, acc, updated) VALUES (1, {ph}, {ph}, {ph}) "
                    "ON CONFLICT (id) DO UPDATE SET score = excluded.score, acc = excluded.acc, updated = excluded.updated",
                    (score, acc, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()
