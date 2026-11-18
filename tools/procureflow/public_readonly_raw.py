"""Persist bounded public read-only response bytes for independent SHA256 verification."""
import hashlib
import json
from pathlib import Path

MAX_RAW_BYTES = 262144

def retain_public_json(payload, content_type, outdir, index):
    """Only JSON; never infer record success from transport status or empty arrays."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ("application/json", "text/json") and not mime.endswith("+json"):
        return {"raw_saved": False, "raw_skip_reason": "NON_JSON"}
    if not payload or len(payload) > MAX_RAW_BYTES:
        return {"raw_saved": False, "raw_skip_reason": "EMPTY_OR_OVERSIZE"}
    try:
        json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return {"raw_saved": False, "raw_skip_reason": "INVALID_JSON"}
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"public-readonly-{index:02d}-{digest[:16]}.json"
    target = Path(outdir) / relative
    target.write_bytes(payload)
    return {"raw_saved": True, "raw_path": relative, "raw_sha256": digest,
            "raw_bytes": len(payload), "raw_verified": hashlib.sha256(target.read_bytes()).hexdigest() == digest}
