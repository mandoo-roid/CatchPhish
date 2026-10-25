# -*- coding: utf-8 -*-
"""ledger.py (C): 장부(해시체인 기록)를 DB에 저장하고 불러온다.

- DATABASE_URL 환경변수가 있으면 진짜 DB(Neon Postgres)를 쓴다. (Vercel)
- 없으면 연습용 SQLite 파일을 쓴다. (Colab, 내 컴퓨터)
- DB 주소·비밀번호는 코드에 절대 적지 않는다. os.environ에서만 꺼낸다.
"""
import json
import os
import sqlite3

from hashchain import build_entry, canonical

try:  # Postgres용 도구 (requirements.txt에 psycopg 추가 필요, 없으면 SQLite만 가능)
    import psycopg
    _PG_INTEGRITY = (psycopg.IntegrityError,)
except ImportError:
    psycopg = None
    _PG_INTEGRITY = ()

_INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + _PG_INTEGRITY
MAX_RETRY = 8

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS ledger (
    seq        BIGINT PRIMARY KEY,
    prev_hash  TEXT NOT NULL,
    record     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    hash       TEXT NOT NULL UNIQUE
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


def _ensure_table(conn):
    cur = conn.cursor()
    cur.execute(CREATE_SQL)
    conn.commit()


def _last_entry(cur, ph):
    cur.execute("SELECT seq, prev_hash, record, created_at, hash FROM ledger ORDER BY seq DESC LIMIT 1")
    row = cur.fetchone()
    return None if row is None else _row_to_entry(row)


def _row_to_entry(row):
    seq, prev_hash, record_text, created_at, h = row
    return {"seq": int(seq), "prev_hash": prev_hash, "record": json.loads(record_text),
            "created_at": created_at, "hash": h}


def append_record(record: dict) -> dict:
    """마지막 기록을 읽고 build_entry로 새 기록을 만들어 저장한 뒤, 저장된 entry를 돌려준다."""
    conn, ph = _connect()
    try:
        _ensure_table(conn)
        for _ in range(MAX_RETRY):
            cur = conn.cursor()
            prev = _last_entry(cur, ph)
            entry = build_entry(prev, record)
            try:
                cur.execute(
                    f"INSERT INTO ledger (seq, prev_hash, record, created_at, hash) "
                    f"VALUES ({ph},{ph},{ph},{ph},{ph})",
                    (entry["seq"], entry["prev_hash"], canonical(record),
                     entry["created_at"], entry["hash"]))
                conn.commit()
                return entry
            except _INTEGRITY_ERRORS:
                conn.rollback()  # 동시에 같은 seq가 들어옴 → 다시 읽고 재시도
        raise RuntimeError("장부 저장이 계속 충돌해서 실패했습니다.")
    finally:
        conn.close()


def load_entries() -> list:
    """모든 기록을 seq 순서대로 돌려준다. (verify_chain과 통계 계산에 씀)"""
    conn, _ = _connect()
    try:
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT seq, prev_hash, record, created_at, hash FROM ledger ORDER BY seq")
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()
