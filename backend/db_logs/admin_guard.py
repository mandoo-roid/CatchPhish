# -*- coding: utf-8 -*-
"""admin_guard.py (A 11/24): 관리자 회사 코드를 여러 번 틀리면 잠시 막는다.

하는 일: 접속한 곳(IP)마다 틀린 횟수를 세서, 5번 틀리면 10분 잠근다. 다시 잠길 때마다 20분, 40분으로 늘어난다 (최대 하루).
        잠긴 동안은 맞는 코드를 넣어도 들어갈 수 없다. 맞게 들어가면 기록을 지워 처음으로 돌아간다.
이유: 작품 보안 점검 (11/20 막기 전 공격). 틀린 코드를 끝없이 다시 시도할 수 있어서, 코드를 하나씩 맞혀 보는 공격(무차별 대입)이 가능했다.
참고: Vercel은 요청마다 서버가 새로 뜰 수 있어 횟수를 메모리에 두면 사라진다. 그래서 DB 표(admin_attempts)에 둔다.
      연결 방법은 game_log.py와 같다 (DATABASE_URL이 있으면 PostgreSQL, 없으면 SQLite 파일).
      IP는 그대로 저장하지 않고 지문(HMAC-SHA256, 열쇠 HASH_SECRET)으로 바꿔 저장한다. 개인정보를 남기지 않으려고.
      IP를 바꿔 가며 시도하는 공격은 이 장치로 막지 않는다. 회사 코드를 길고 짐작할 수 없게 두는 것으로 막는다.
      사이트 전체 잠금은 일부러 넣지 않았다. 누군가 일부러 계속 틀리면 관리자도 못 들어가게 되는 공격(서비스 거부)에 쓰일 수 있어서.
"""
import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timedelta, timezone

try:
    import psycopg
except ImportError:
    psycopg = None

MAX_FAILS = 5                       # 이만큼 틀리면 잠근다
FIRST_LOCK = timedelta(minutes=10)  # 첫 잠금 시간. 다시 잠길 때마다 두 배
MAX_LOCK = timedelta(hours=24)      # 잠금 시간 최대

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS admin_attempts (
    ip_key       TEXT PRIMARY KEY,
    fails        INTEGER NOT NULL,
    lock_level   INTEGER NOT NULL,
    locked_until TEXT
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


def _ip_key(ip: str) -> str:
    # 하는 일: IP를 지문으로 바꾼다. 같은 IP는 늘 같은 지문이 되지만, 지문으로 IP를 되찾을 수는 없다
    key = os.environ.get("HASH_SECRET", "")
    return hmac.new(key.encode(), (ip or "unknown").encode(), hashlib.sha256).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _read(cur, ph, k):
    cur.execute(CREATE_SQL)
    cur.execute(f"SELECT fails, lock_level, locked_until FROM admin_attempts WHERE ip_key = {ph}", (k,))
    return cur.fetchone()


def locked_seconds(ip: str) -> int:
    """잠겨 있으면 남은 초, 아니면 0."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        row = _read(cur, ph, _ip_key(ip))
        conn.commit()
        if row and row[2]:
            left = (datetime.fromisoformat(row[2]) - _now()).total_seconds()
            if left > 0:
                return int(left) + 1
        return 0
    finally:
        conn.close()


def record_fail(ip: str) -> int:
    """틀린 시도를 하나 센다. 이번에 잠겼으면 잠긴 초, 아니면 0."""
    k = _ip_key(ip)
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        row = _read(cur, ph, k)
        fails, level = (row[0], row[1]) if row else (0, 0)
        fails += 1
        until, locked = None, 0
        if fails >= MAX_FAILS:
            # 다시 잠길 때마다 두 배: 10분, 20분, 40분 ... 최대 하루
            dur = min(FIRST_LOCK * (2 ** level), MAX_LOCK)
            until = (_now() + dur).isoformat()
            locked = int(dur.total_seconds())
            fails, level = 0, level + 1
        cur.execute(
            f"INSERT INTO admin_attempts (ip_key, fails, lock_level, locked_until) VALUES ({ph}, {ph}, {ph}, {ph}) "
            "ON CONFLICT (ip_key) DO UPDATE SET fails = excluded.fails, lock_level = excluded.lock_level, "
            "locked_until = excluded.locked_until",
            (k, fails, level, until))
        conn.commit()
        return locked
    finally:
        conn.close()


def record_success(ip: str) -> None:
    """맞게 들어가면 기록을 지워 처음으로 돌아간다."""
    conn, ph = _connect()
    try:
        cur = conn.cursor()
        cur.execute(CREATE_SQL)
        cur.execute(f"DELETE FROM admin_attempts WHERE ip_key = {ph}", (_ip_key(ip),))
        conn.commit()
    finally:
        conn.close()
