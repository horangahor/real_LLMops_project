"""Snapshot all local workflow artifacts and prepare byte-verified caches on another PC."""

import argparse
import hashlib
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST = "cache-snapshot.json"
VERSION = "workspace-cache-v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relocate(value, old, new):
    """Replace only rooted workspace paths, preserving Windows extended prefixes."""
    if isinstance(value, dict):
        return {key: relocate(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [relocate(item, old, new) for item in value]
    if not isinstance(value, str):
        return value
    extended = "\\\\?\\" if value.startswith("\\\\?\\") else ""
    normalized = value[len(extended):].replace("\\", "/")
    prefix = str(old).replace("\\", "/").rstrip("/")
    if normalized != prefix and not normalized.startswith(prefix + "/"):
        return value
    # The canonical origin keeps its original separator style for old hashes.
    separator = "\\" if "\\" in str(new) else "/"
    target = str(new).replace("\\", separator).replace("/", separator).rstrip(separator)
    suffix = normalized[len(prefix):].replace("/", separator)
    return extended + target + suffix


@lru_cache(maxsize=1)
def cache_origin():
    path = BASE / MANIFEST
    if not path.is_file():
        return str(BASE)
    record = json.loads(path.read_bytes())
    return record.get("cache_identity_workspace", record["original_workspace"])


def canonical_cache_value(value):
    """Keep existing cache/checkpoint identities when the checkout path changes."""
    origin = cache_origin()
    return value if origin == str(BASE) else relocate(value, str(BASE), origin)


def snapshot(base=BASE):
    base = Path(base).resolve()
    records, timestamps = [], {}
    previous = json.loads((base / MANIFEST).read_bytes()) if (base / MANIFEST).is_file() else {}
    for parent, directories, names in os.walk(base / "draft_history"):
        directories.sort()
        for name in sorted(names):
            path = Path(parent) / name
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"스냅샷 도중 변경된 파일: {path}")
            records.append({"path": path.relative_to(base).as_posix(), "size": len(data), "sha256": sha(data)})
            timestamps[path] = (after.st_size, after.st_mtime_ns)
    for path, expected in timestamps.items():
        actual = path.stat()
        if (actual.st_size, actual.st_mtime_ns) != expected:
            raise RuntimeError(f"스냅샷 도중 변경된 파일: {path}")
    payload = {"version": VERSION, "original_workspace": str(base),
               "cache_identity_workspace": previous.get("cache_identity_workspace", previous.get("original_workspace", str(base))),
               "files": records}
    (base / MANIFEST).write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode())
    return {"files": len(records), "bytes": sum(r["size"] for r in records)}


def prepare(base=BASE, *, verify_only=False):
    base = Path(base).resolve()
    manifest = json.loads((base / MANIFEST).read_bytes())
    if manifest.get("version") != VERSION:
        raise ValueError("지원하지 않는 캐시 스냅샷입니다.")
    origin = manifest["original_workspace"]
    files, desired = {}, {}
    for record in manifest["files"]:
        relative = Path(record["path"])
        if (relative.is_absolute() or ".." in relative.parts or "\\" in record["path"]
                or ":" in record["path"] or not relative.parts or relative.parts[0] != "draft_history"):
            raise ValueError("스냅샷 경로가 draft_history를 벗어났습니다.")
        target = base / relative
        if target.resolve().is_relative_to((base / "draft_history").resolve()) is False:
            raise ValueError("스냅샷 경로가 draft_history를 벗어났습니다.")
        data = target.read_bytes()
        # A second prepare is a no-op. Locally resumed/edited files are never
        # silently overwritten by the original Git snapshot.
        files[record["path"]] = (target, data, record)
        immutable = (target.name in ("parse-response.json", "parse-failed-response.json")
                     or target.name.endswith(".native.json"))
        changed = data
        if origin != str(base) and target.suffix == ".json" and not immutable:
            value = json.loads(data)
            rebased = relocate(value, origin, str(base))
            if rebased != value:
                changed = (json.dumps(rebased, ensure_ascii=False, indent=2) + ("\n" if data.endswith(b"\n") else "")).encode()
        desired[record["path"]] = changed
    # Raw-file references (e.g. latest.json's review checksum) must follow
    # relocated derived JSON. Payload fingerprints retain the canonical origin.
    for _ in range(8):
        updates = {record["sha256"]: sha(desired[name]) for name, (_, _, record) in files.items()
                   if record["sha256"] != sha(desired[name])}
        if not updates:
            break
        did_change = False
        def replace_hashes(value):
            if isinstance(value, dict):
                return {key: replace_hashes(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace_hashes(item) for item in value]
            return updates.get(value, value) if isinstance(value, str) else value
        for name, (path, _, _) in files.items():
            if path.suffix != ".json" or path.name.endswith(".native.json") or path.name in ("parse-response.json", "parse-failed-response.json"):
                continue
            value = json.loads(desired[name])
            updated = replace_hashes(value)
            if updated != value:
                desired[name] = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode()
                did_change = True
        if not did_change:
            break
    else:
        raise ValueError("순환하는 파일 해시 연결을 안전하게 이관할 수 없습니다.")
    state_path = base / ".cache-workspace.json"
    state = json.loads(state_path.read_bytes()) if state_path.is_file() else {}
    known = state.get("relocated_files", {}) if state.get("snapshot_sha256") == sha((base / MANIFEST).read_bytes()) else {}
    for name, (_, current, record) in files.items():
        if sha(current) != record["sha256"] and known.get(name) != sha(current):
            raise ValueError(f"로컬 변경을 덮어쓰지 않습니다: {name}")
    changed_count = sum(current != desired[name] for name, (_, current, _) in files.items())
    if not verify_only:
        from document_parse import write_json
        local_state = {"snapshot_sha256": sha((base / MANIFEST).read_bytes()), "workspace": str(base),
                       "status": "preparing", "relocated_files": {name: sha(data) for name, data in desired.items()}}
        write_json(state_path, local_state)
        for name, (path, current, _) in files.items():
            if current != desired[name]:
                # All records were validated before the first write.
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(desired[name])
                os.replace(temporary, path)
        write_json(state_path, {**local_state, "status": "complete"})
    return {"files": len(files), "relocated_files": changed_count, "verified": True,
            "needs_prepare": bool(changed_count) if verify_only else False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "prepare", "verify"))
    args = parser.parse_args()
    result = snapshot() if args.command == "snapshot" else prepare(verify_only=args.command == "verify")
    print(json.dumps(result, ensure_ascii=False))
