"""Document Parse API client with source-bound, inspectable local artifacts."""

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import UPSTAGE_API_KEY

PARSE_URL = "https://api.upstage.ai/v1/document-digitization"
DEFAULT_MODEL = "document-parse-260930"


def filesystem_path(path):
    """Use Win32 extended paths without requiring the machine-wide long-path setting."""
    path = Path(path)
    if os.name != "nt":
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


class JsonWriteError(OSError):
    """A complete JSON is recoverable even when its destination stays locked."""

    def __init__(self, destination, temporary_path, cause):
        self.destination = destination
        self.temporary_path = temporary_path
        self.original_error = cause
        super().__init__(cause.errno, f"JSON 파일 교체에 실패했습니다. 임시 데이터는 보존했습니다: {temporary_path}. 원인: {cause}", str(destination))


def write_json(path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path = filesystem_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    # Windows scanners/editors may briefly hold a handle that denies replace.
    # Retry the same complete temporary file; never truncate the destination.
    delays = (.1, .2, .4, .8)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(temporary, path)
            return
        except OSError as error:
            transient = isinstance(error, PermissionError) or getattr(error, "winerror", None) in (5, 32, 33)
            if not transient or attempt == len(delays):
                raise JsonWriteError(path, temporary, error) from error
            time.sleep(delays[attempt])


def write_json_optional(path, value):
    """Failure to save diagnostics must not interrupt the work being recorded."""
    try:
        write_json(path, value)
        return True
    except OSError as error:
        logging.getLogger(__name__).warning("보조 기록을 저장하지 못했습니다: %s", error)
        return False


def validate_parse(document):
    if not isinstance(document, dict) or not isinstance(document.get("elements"), list) or not document["elements"]:
        raise ValueError("Document Parse의 elements가 비어 있거나 형식이 잘못됐습니다.")
    seen = set()
    for element in document["elements"]:
        if not isinstance(element, dict):
            raise ValueError("Document Parse 요소가 객체가 아닙니다.")
        page, identifier = element.get("page"), element.get("id")
        if type(page) is not int or page < 1 or type(identifier) not in (str, int):
            raise ValueError("Document Parse 요소의 페이지·ID가 잘못됐습니다.")
        key = (page, str(identifier))
        if key in seen or not isinstance(element.get("content"), dict):
            raise ValueError("Document Parse 요소 ID가 중복되거나 content가 잘못됐습니다.")
        seen.add(key)
    return document


def artifact_directory(pdf, root, *, model=DEFAULT_MODEL, mode="standard", ocr="auto"):
    pdf = Path(pdf)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    settings = hashlib.sha256(json.dumps([model, mode, ocr]).encode()).hexdigest()[:8]
    return Path(root) / f"{pdf.stem}-{digest[:12]}-{settings}"


def parse_document(pdf, artifact_dir, *, model=DEFAULT_MODEL, mode="standard", ocr="auto", force=False):
    """Return the full native response. A matching completed cache avoids another API call."""
    pdf, artifact_dir = Path(pdf), Path(artifact_dir)
    if not pdf.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {pdf.name}")
    if mode not in ("standard", "enhanced", "auto") or ocr not in ("auto", "force"):
        raise ValueError("지원하지 않는 Parse mode 또는 OCR 설정입니다.")
    settings = {"model": model, "mode": mode, "ocr": ocr,
                "output_formats": '["text", "html", "markdown"]', "coordinates": "true"}
    identity = {"source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "request_settings": settings}
    raw_path, manifest_path = artifact_dir / "parse-response.json", artifact_dir / "parse-manifest.json"
    if raw_path.is_file() and manifest_path.is_file() and not force:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("Parse 캐시의 원본 또는 설정이 다릅니다. 새 실행 폴더를 사용하세요.")
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != manifest.get("response_sha256"):
            raise ValueError("Parse 원본 캐시가 변경되었습니다. 캐시를 확인하거나 --force-parse를 사용하세요.")
        return validate_parse(json.loads(raw_path.read_text(encoding="utf-8")))
    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 필요합니다.")
    with pdf.open("rb") as source:
        response = requests.post(PARSE_URL, headers={"Authorization": f"Bearer {UPSTAGE_API_KEY}"},
                                 files={"document": source}, data=settings, timeout=180)
    try:
        body = response.json()
    except ValueError as error:
        raise RuntimeError(f"Document Parse가 JSON이 아닌 응답을 반환했습니다 (HTTP {response.status_code}).") from error
    if response.status_code != 200:
        write_json(artifact_dir / "parse-failed-response.json", body)
        raise RuntimeError(f"Document Parse 요청 실패 (HTTP {response.status_code}).")
    try:
        validate_parse(body)
    except ValueError:
        failed = artifact_dir / "parse-failed-response.json"
        write_json(failed, body)
        write_json(artifact_dir / "parse-failed-manifest.json", {**identity, "response_sha256": hashlib.sha256(failed.read_bytes()).hexdigest(), "http_status": response.status_code})
        raise
    write_json(raw_path, body)
    write_json(manifest_path, {**identity, "source_file": pdf.name, "endpoint": PARSE_URL,
                              "returned_model": body.get("model"),
                              "response_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                              "saved_at_utc": datetime.now(timezone.utc).isoformat()})
    return body
