"""Append-only, hash-chained audit log (JSON Lines).

Tamper-EVIDENT, not tamper-proof: anyone with write access can rewrite the whole file and
recompute hashes. A real deployment anchors the head hash outside the system (e.g. WORM storage
or a separate log service)."""
import hashlib, json, os, time

GENESIS = "0" * 64


def _digest(prev, body):
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def append(path, event):
    prev = GENESIS
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        if lines:
            prev = json.loads(lines[-1])["hash"]
    body = dict(event, ts=round(time.time(), 3), prev=prev)
    body["hash"] = _digest(prev, {k: v for k, v in body.items() if k != "hash"})
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(body, sort_keys=True) + "\n")
    return body["hash"]


def verify(path):
    """Return (ok, number_of_records, first_bad_line_or_None)."""
    prev = GENESIS
    n = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev") != prev or _digest(prev, body) != rec.get("hash"):
                return False, n, i
            prev = rec["hash"]
            n += 1
    return True, n, None
