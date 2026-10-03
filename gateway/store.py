"""Local SQLite transaction: business state and audit events commit together.
Not a distributed transaction with a CRM or payment provider; no such call exists here.
"""
import contextlib, copy, json, os, sqlite3
from . import audit, data

def path():
    return os.environ.get("GATEWAY_STATE", "state.sqlite3")

@contextlib.contextmanager
def transaction():
    db = sqlite3.connect(path(), timeout=10)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        state = json.loads(row[0]) if row else {"accounts": copy.deepcopy(data.ACCOUNTS), "pending": {}, "approved_quotes": {}, "deposit_requests": []}
        records = [json.loads(r[0]) for r in db.execute("SELECT body FROM events ORDER BY seq")]
        if not audit.verify_records(records)[0]:
            raise ValueError("audit chain invalid")
        yield db, state
        db.execute("INSERT OR REPLACE INTO state VALUES (1, ?)", (json.dumps(state, sort_keys=True, allow_nan=False),))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

def append(db, event):
    row = db.execute("SELECT seq, body FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    seq = row[0]+1 if row else 1
    previous = json.loads(row[1])["hash"] if row else audit.GENESIS
    rec = audit.record(previous, event)
    db.execute("INSERT INTO events VALUES (?, ?)", (seq, json.dumps(rec, sort_keys=True, allow_nan=False)))
    return rec

def records():
    with transaction() as (db, _):
        return [json.loads(r[0]) for r in db.execute("SELECT body FROM events ORDER BY seq")]

def export(destination):
    """Offline snapshot export. Export failure does not undo already committed actions."""
    rows = records()
    with open(destination, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True)+"\n")
    return {"count": len(rows), "hash": rows[-1]["hash"] if rows else audit.GENESIS}
