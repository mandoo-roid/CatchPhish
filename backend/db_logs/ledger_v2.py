# -*- coding: utf-8 -*-
"""ledger_v2.py (C): ledger.py 보완판. 사이트에는 아직 연결되지 않은 새 파일이다.

ledger.py와 달라진 점
1) hashchain_v2를 쓴다 (HMAC, head 검사).
2) 표를 하나 더 둔다: ledger_head (마지막 번호·마지막 지문·도장). 기록을 저장할 때 같은 트랜잭션에서 같이 갱신한다.
3) load_head(), verify_ledger()가 새로 생겼다.
나머지(5칸, record는 TEXT, created_at은 글자, 충돌 시 최대 8번 재시도)는 그대로다.
append_record, load_entries의 이름·입력·출력도 그대로다.
"""
import json
import os
import sqlite3

from hashchain_v2 import build_entry, build_head, canonical, verify_chain

try:
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
CREATE_HEAD_SQL = """
CREATE TABLE IF NOT EXISTS ledger_head (
    id        INTEGER PRIMARY KEY,
    last_seq  BIGINT NOT NULL,
    last_hash TEXT NOT NULL,
    head_mac  TEXT NOT NULL
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


def _ensure_tables(conn):
    cur = conn.cursor()
    cur.execute(CREATE_SQL)
    cur.execute(CREATE_HEAD_SQL)
    conn.commit()


def _row_to_entry(row):
    seq, prev_hash, record_text, created_at, h = row
    return {"seq": int(seq), "prev_hash": prev_hash, "record": json.loads(record_text),
            "created_at": created_at, "hash": h}


def _last_entry(cur):
    cur.execute("SELECT seq, prev_hash, record, created_at, hash FROM ledger ORDER BY seq DESC LIMIT 1")
    row = cur.fetchone()
    return None if row is None else _row_to_entry(row)


def append_record(record: dict) -> dict:
    """기록 저장 + head 갱신을 한 번에(같은 트랜잭션) 한다. 저장된 entry를 돌려준다."""
    conn, ph = _connect()
    try:
        _ensure_tables(conn)
        for _ in range(MAX_RETRY):
            cur = conn.cursor()
            prev = _last_entry(cur)
            entry = build_entry(prev, record)
            head = build_head(entry)
            try:
                cur.execute(
                    f"INSERT INTO ledger (seq, prev_hash, record, created_at, hash) "
                    f"VALUES ({ph},{ph},{ph},{ph},{ph})",
                    (entry["seq"], entry["prev_hash"], canonical(record),
                     entry["created_at"], entry["hash"]))
                cur.execute(
                    f"INSERT INTO ledger_head (id, last_seq, last_hash, head_mac) "
                    f"VALUES (1,{ph},{ph},{ph}) "
                    f"ON CONFLICT (id) DO UPDATE SET last_seq=excluded.last_seq, "
                    f"last_hash=excluded.last_hash, head_mac=excluded.head_mac",
                    (head["last_seq"], head["last_hash"], head["head_mac"]))
                conn.commit()
                return entry
            except _INTEGRITY_ERRORS:
                conn.rollback()
        raise RuntimeError("장부 저장이 계속 충돌해서 실패했습니다.")
    finally:
        conn.close()


def load_entries() -> list:
    """모든 기록을 seq 순서대로 돌려준다. (예전과 같음)"""
    conn, _ = _connect()
    try:
        _ensure_tables(conn)
        cur = conn.cursor()
        cur.execute("SELECT seq, prev_hash, record, created_at, hash FROM ledger ORDER BY seq")
        return [_row_to_entry(r) for r in cur.fetchall()]
    finally:
        conn.close()


def load_head():
    """head 한 줄을 dict로 돌려준다. 없으면 None."""
    conn, _ = _connect()
    try:
        _ensure_tables(conn)
        cur = conn.cursor()
        cur.execute("SELECT last_seq, last_hash, head_mac FROM ledger_head WHERE id=1")
        row = cur.fetchone()
        return None if row is None else {"last_seq": int(row[0]), "last_hash": row[1], "head_mac": row[2]}
    finally:
        conn.close()


def verify_ledger() -> dict:
    """A가 /api/admin/verify에서 부르는 한 줄짜리 검사. head를 먼저 읽고 기록을 읽는다."""
    head = load_head()
    return verify_chain(load_entries(), head)
