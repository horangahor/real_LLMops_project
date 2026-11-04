import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import workspace_cache
from workspace_cache import MANIFEST, prepare, relocate, sha, snapshot


class WorkspaceCacheTests(unittest.TestCase):
    def setup_cache(self, base):
        folder = base / "draft_history/planned/generic/run"
        folder.mkdir(parents=True)
        body = {"run_dir": str(folder), "text": "Keep 12ms", "limits": "single observation"}
        digest = sha(json.dumps(body, ensure_ascii=False, sort_keys=True).encode())
        (folder / "approved.json").write_text(json.dumps({"sha256": digest, "value": body}), encoding="utf-8")
        native = (json.dumps({"native_path": str(folder), "elements": []}) + "\r\n").encode()
        (folder / "parse-response.json").write_bytes(native)
        (folder / "parse-manifest.json").write_text(json.dumps({"response_sha256": sha(native)}), encoding="utf-8")
        (folder / "draft.md").write_bytes(b"completed draft\r\n")
        (folder / "plan.json").write_text(json.dumps({"path": str(folder)}), encoding="utf-8")
        (folder / "review.json").write_text(json.dumps({"report": str(folder)}), encoding="utf-8")
        (base / "draft_history/planned/latest.json").write_text(json.dumps({"run_dir": str(folder),
            "draft_sha256": sha((folder / "draft.md").read_bytes()), "plan_sha256": sha((folder / "plan.json").read_bytes()),
            "review_sha256": sha((folder / "review.json").read_bytes())}), encoding="utf-8")
        return folder, digest, native

    def test_relocation_preserves_prefix_boundaries_and_extended_windows_paths(self):
        old, new = r"C:\Users\old\repo", r"D:\work\repo"
        data = {"path": old + r"\draft_history\run", "extended": "\\\\?\\" + old + r"\draft_history\run",
                "not_path": "text " + old, "sibling": old + "-other/file"}
        moved = relocate(data, old, new)
        self.assertEqual(moved["extended"], "\\\\?\\" + new + r"\draft_history\run")
        self.assertEqual(moved["not_path"], data["not_path"])
        self.assertEqual(moved["sibling"], data["sibling"])
        self.assertEqual(relocate(moved, new, old), data)

    def test_other_checkout_keeps_payload_identities_native_bytes_and_latest_file_hashes(self):
        with TemporaryDirectory() as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            folder, digest, native = self.setup_cache(old)
            snapshot(old)
            shutil.copytree(old, new)
            result = prepare(new)
            self.assertTrue(result["relocated_files"])
            target = new / folder.relative_to(old)
            payload = json.loads((target / "approved.json").read_bytes())
            self.assertEqual(payload["value"]["run_dir"], str(target))
            with patch.object(workspace_cache, "BASE", new), patch.object(workspace_cache, "cache_origin", return_value=str(old)):
                from planned_paper import fingerprint, load_latest
                self.assertEqual(fingerprint(payload["value"]), digest)
                self.assertEqual(load_latest(new)["draft_markdown"], "completed draft\n")
            self.assertEqual((target / "parse-response.json").read_bytes(), native)
            self.assertEqual(json.loads((target / "parse-manifest.json").read_bytes())["response_sha256"], sha(native))
            before = {p.relative_to(new).as_posix(): sha(p.read_bytes()) for p in (new / "draft_history").rglob("*") if p.is_file()}
            self.assertEqual(prepare(new)["relocated_files"], 0)
            self.assertEqual(before, {p.relative_to(new).as_posix(): sha(p.read_bytes()) for p in (new / "draft_history").rglob("*") if p.is_file()})

    def test_tampering_is_rejected_before_any_artifact_is_overwritten(self):
        with TemporaryDirectory() as tmp:
            old, new = Path(tmp) / "old", Path(tmp) / "new"
            self.setup_cache(old)
            snapshot(old)
            shutil.copytree(old, new)
            target = new / "draft_history/planned/generic/run/approved.json"
            target.write_text('{"local": "do not overwrite"}', encoding="utf-8")
            before = {p: p.read_bytes() for p in (new / "draft_history").rglob("*") if p.is_file()}
            with self.assertRaisesRegex(ValueError, "로컬 변경"):
                prepare(new)
            self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_same_checkout_verify_never_changes_files(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            folder, _, _ = self.setup_cache(base)
            snapshot(base)
            before = (folder / "approved.json").read_bytes()
            self.assertEqual(prepare(base, verify_only=True)["relocated_files"], 0)
            self.assertEqual((folder / "approved.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
