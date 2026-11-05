import ctypes
import errno
import json
import os
import unittest
from ctypes import wintypes
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

import document_parse
from document_parse import JsonWriteError, filesystem_path, write_json
from planned_paper import PlannedPaper, request_json


def response(content='{"ok":true}', status=200):
    return Mock(status_code=status, json=lambda: {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                                "usage": {"completion_tokens": 10}})


class JsonStorageTests(unittest.TestCase):
    def test_transient_replace_lock_retries_same_complete_file_and_preserves_old_destination(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            write_json(path, {"old": True})
            replace = os.replace
            attempts = []
            def locked(source, destination):
                attempts.append(source)
                self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8")), {"new": True})
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
                    raise PermissionError(errno.EACCES, "temporarily locked")
                return replace(source, destination)
            with patch("document_parse.os.replace", side_effect=locked), patch("document_parse.time.sleep") as sleep:
                write_json(path, {"new": True})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(len(set(attempts)), 1)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_persistent_lock_keeps_complete_temporary_json_and_old_destination(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            write_json(path, {"old": True})
            with patch("document_parse.os.replace", side_effect=PermissionError(errno.EACCES, "locked")) as replace, \
                    patch("document_parse.time.sleep"):
                with self.assertRaises(JsonWriteError) as caught:
                    write_json(path, {"new": True})
            self.assertEqual(replace.call_count, 5)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
            self.assertEqual(json.loads(caught.exception.temporary_path.read_text(encoding="utf-8")), {"new": True})
            self.assertIn(str(caught.exception.temporary_path), str(caught.exception))

    def test_non_lock_error_is_not_retried_and_does_not_discard_temporary_data(self):
        with TemporaryDirectory() as tmp, patch("document_parse.os.replace", side_effect=OSError(errno.ENOSPC, "full")) as replace, \
                patch("document_parse.time.sleep") as sleep:
            with self.assertRaises(JsonWriteError) as caught:
                write_json(Path(tmp) / "state.json", {"received": True})
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()
            self.assertEqual(json.loads(caught.exception.temporary_path.read_text(encoding="utf-8")), {"received": True})

    def test_serialization_error_does_not_modify_existing_file_or_leave_partial_temp(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            write_json(path, {"old": True})
            with self.assertRaises(TypeError):
                write_json(path, {"not_json": object()})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_audit_lock_does_not_lose_native_response_or_trigger_another_api_call(self):
        replace = os.replace
        def audit_locked(source, destination):
            if str(destination).endswith(".native.request.json"):
                raise PermissionError(errno.EACCES, "audit locked")
            return replace(source, destination)
        with TemporaryDirectory() as tmp, patch("document_parse.os.replace", side_effect=audit_locked), \
                patch("document_parse.time.sleep"), patch("planned_paper.requests.post", return_value=response()) as post, \
                self.assertLogs("document_parse", level="WARNING") as logs:
            engine = PlannedPaper(tmp, api_key="test-key")
            self.assertEqual(engine.call(Path(tmp), "review", "system", {}, {}), {"ok": True})
            self.assertEqual(engine.call(Path(tmp), "review", "system", {}, {}), {"ok": True})
            self.assertEqual(post.call_count, 1)
            native = list((Path(tmp) / "responses").glob("*.native.json"))
            self.assertEqual(len(native), 1)
            self.assertEqual(json.loads(native[0].read_text(encoding="utf-8"))["choices"][0]["message"]["content"], '{"ok":true}')
            self.assertTrue(list((Path(tmp) / "responses").glob("*.tmp")))
            self.assertNotIn("test-key", "\n".join(logs.output))

    def test_native_write_failure_preserves_response_and_stops_without_success_cache_or_api_retry(self):
        replace = os.replace
        def native_locked(source, destination):
            if str(destination).endswith(".native.json"):
                raise PermissionError(errno.EACCES, "native locked")
            return replace(source, destination)
        with TemporaryDirectory() as tmp, patch("document_parse.os.replace", side_effect=native_locked), \
                patch("document_parse.time.sleep"), patch("planned_paper.requests.post", return_value=response()) as post:
            with self.assertRaises(JsonWriteError) as caught:
                PlannedPaper(tmp, api_key="test-key").call(Path(tmp), "review", "system", {}, {})
            self.assertEqual(post.call_count, 1)
            saved = json.loads(caught.exception.temporary_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["choices"][0]["message"]["content"], '{"ok":true}')
            self.assertFalse(any("request_fingerprint" in json.loads(p.read_text(encoding="utf-8")) for p in (Path(tmp) / "responses").glob("*.json")))

    def test_real_response_is_saved_before_success_audit_update(self):
        write = document_parse.write_json
        def check_order(path, value):
            if str(path).endswith(".request.json") and value["attempts"][-1].get("http_status") == 200:
                native = Path(path).with_name(Path(path).name.replace(".request.json", ".json"))
                self.assertTrue(native.is_file())
            return write(path, value)
        with TemporaryDirectory() as tmp, patch("document_parse.write_json", side_effect=check_order), \
                patch("planned_paper.requests.post", return_value=response()):
            self.assertEqual(request_json("system", {}, {}, Path(tmp) / "review.native.json", "test-key"), {"ok": True})

    def test_diagnostic_save_failure_does_not_mask_original_network_timeout(self):
        with TemporaryDirectory() as tmp, patch("document_parse.os.replace", side_effect=PermissionError(errno.EACCES, "locked")), \
                patch("document_parse.time.sleep"), patch("planned_paper.requests.post", side_effect=requests.ReadTimeout()) as post, \
                self.assertLogs("document_parse", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "ReadTimeout.*전송 시도 2회"):
                request_json("system", {}, {}, Path(tmp) / "review.native.json", "test-key")
            self.assertEqual(post.call_count, 2)
            self.assertTrue(list(Path(tmp).glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "Windows file sharing semantics")
    def test_windows_handle_without_delete_sharing_reproduces_access_denial_without_data_loss(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            write_json(path, {"old": True})
            handle = kernel.CreateFileW(str(filesystem_path(path)), 0x80000000, 0x3, None, 3, 0, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            try:
                with patch("document_parse.time.sleep"), self.assertRaises(JsonWriteError) as caught:
                    write_json(path, {"new": True})
                self.assertIn(caught.exception.original_error.winerror, (5, 32, 33))
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
                self.assertEqual(json.loads(caught.exception.temporary_path.read_text(encoding="utf-8")), {"new": True})
            finally:
                kernel.CloseHandle(handle)
            os.replace(caught.exception.temporary_path, filesystem_path(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})


if __name__ == "__main__":
    unittest.main()
