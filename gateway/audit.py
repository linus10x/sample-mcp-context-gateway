"""Hash-chain verification. Tail removal needs a separately trusted count/head anchor.
An administrator can rewrite the database and recompute hashes; this is not tamper-proof.
"""
import hashlib, json, time
GENESIS = "0" * 64

def _digest(prev, body):
    return hashlib.sha256((prev+json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)).encode()).hexdigest()

def record(prev, event):
    body = dict(event, ts=round(time.time(), 3), prev=prev)
    return dict(body, hash=_digest(prev, body))

def verify_records(records, anchor=None):
    prev, n = GENESIS, 0
    try:
        for i, rec in enumerate(records, 1):
            if not isinstance(rec, dict):
                return False, n, i
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev") != prev or _digest(prev, body) != rec.get("hash"):
                return False, n, i
            prev, n = rec["hash"], n+1
    except (TypeError, ValueError):
        return False, n, n+1
    if anchor is not None and anchor != {"count": n, "hash": prev}:
        return False, n, n+1
    return True, n, None

def verify(path, anchor=None):
    try:
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return False, 0, 1
    return verify_records(rows, anchor)
