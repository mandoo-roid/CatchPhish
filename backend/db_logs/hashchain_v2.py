# -*- coding: utf-8 -*-
"""hashchain_v2.py (C): hashchain.py 보완판. 사이트에는 아직 연결되지 않은 새 파일이다.

hashchain.py와 달라진 점 (함수 이름과 입력은 그대로)
1) 비밀 열쇠(HMAC): 환경 변수 HASH_SECRET이 있으면 지문을 HMAC-SHA256으로 계산한다.
   열쇠가 없으면 예전과 같은 SHA-256으로 계산한다 (Colab 시험용).
   열쇠 값은 코드·문서·단톡에 적지 않는다. Vercel 환경 변수에만 둔다.
2) 끝 기록 삭제 감지: 장부와 따로 저장한 head(마지막 번호·마지막 지문)와 맞춰 본다.
   verify_chain(entries, head)처럼 head를 넘길 때만 검사한다. 안 넘기면 예전처럼 동작한다.

주의: 지문 계산이 바뀌므로 열쇠를 켜는 순간 이전에 저장된 기록은 전부 "변조"로 나온다.
      그래서 A가 장부를 비울 때 같이 바꿔 끼운다.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64
_SKIP = object()  # verify_chain에서 head를 아예 안 넘겼다는 표시


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(text):
    """열쇠가 있으면 HMAC-SHA256, 없으면 SHA-256. 호출할 때마다 환경 변수를 읽는다."""
    data = text.encode("utf-8")
    key = os.environ.get("HASH_SECRET")
    if key:
        return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()
    return hashlib.sha256(data).hexdigest()


def compute_hash(seq, prev_hash, record, created_at):
    body = canonical({"seq": seq, "prev_hash": prev_hash,
                      "record": record, "created_at": created_at})
    return _digest(body)


def compute_head_mac(last_seq, last_hash):
    """head(마지막 번호·지문)에 찍는 도장. 장부 지문과 섞이지 않게 'head' 표시를 넣는다."""
    return _digest(canonical({"kind": "head", "last_seq": last_seq, "last_hash": last_hash}))


def build_entry(prev_entry, record):
    seq = 1 if prev_entry is None else prev_entry["seq"] + 1
    prev_hash = GENESIS_HASH if prev_entry is None else prev_entry["hash"]
    created_at = datetime.now(timezone.utc).isoformat()
    return {"seq": seq, "prev_hash": prev_hash, "record": record,
            "created_at": created_at,
            "hash": compute_hash(seq, prev_hash, record, created_at)}


def build_head(entry):
    """저장된 마지막 기록으로 head 한 줄을 만든다."""
    return {"last_seq": entry["seq"], "last_hash": entry["hash"],
            "head_mac": compute_head_mac(entry["seq"], entry["hash"])}


def _check_chain(entries):
    prev_hash = GENESIS_HASH
    for i, e in enumerate(entries, start=1):
        if e["seq"] != i:
            return {"ok": False, "broken_seq": i, "reason": "순번이 끊김 (기록 삭제·삽입 의심)"}
        if e["prev_hash"] != prev_hash:
            return {"ok": False, "broken_seq": i, "reason": "앞 기록의 지문이 안 맞음"}
        if compute_hash(e["seq"], e["prev_hash"], e["record"], e["created_at"]) != e["hash"]:
            return {"ok": False, "broken_seq": i, "reason": "기록 내용이 바뀜 (변조)"}
        prev_hash = e["hash"]
    return None


def verify_chain(entries, head=_SKIP):
    """장부 검사. head를 넘기면 '끝 기록 삭제'도 검사한다.

    head: ledger_v2.load_head()의 결과. 장부 기록이 있는데 head가 None이면 head 없음으로 본다.
    (head는 기록보다 먼저 읽어야 한다. 읽는 사이에 새 기록이 늘어난 건 정상으로 본다.)
    """
    bad = _check_chain(entries)
    if bad:
        return bad
    if head is _SKIP:
        return {"ok": True, "count": len(entries)}

    if head is None:
        if entries:
            return {"ok": False, "broken_seq": len(entries),
                    "reason": "마지막 기록 표시(head)가 없음 (삭제 의심)"}
        return {"ok": True, "count": 0}

    if not hmac.compare_digest(str(head.get("head_mac", "")),
                               compute_head_mac(head["last_seq"], head["last_hash"])):
        return {"ok": False, "broken_seq": head["last_seq"],
                "reason": "마지막 기록 표시(head)가 바뀜 (변조)"}
    n = head["last_seq"]
    if len(entries) < n:
        return {"ok": False, "broken_seq": len(entries) + 1,
                "reason": f"끝 기록이 삭제됨 (원래 {n}번까지 있었음)"}
    if entries[n - 1]["hash"] != head["last_hash"]:
        return {"ok": False, "broken_seq": n, "reason": "마지막 기록의 지문이 head와 안 맞음"}
    return {"ok": True, "count": len(entries)}
