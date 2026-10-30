"""Check the frozen package in the actual Streamlit UI without making model calls."""

import hashlib
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import requests
from streamlit.testing.v1 import AppTest
from document_parse import write_json


def main():
    prediction = HERE / "evidence.json"
    package = json.loads(prediction.read_text(encoding="utf-8"))
    result = {"draft_markdown": "", "evidence_extraction": package}
    with patch.object(requests, "post", side_effect=AssertionError("Network disabled")), \
            patch("paper_draft_agent.PaperDraftOrchestrator.run_pipeline", return_value=result) as gateway:
        app = AppTest.from_file(str(BASE / "streamlit_app.py"), default_timeout=30).run()
        assert not app.exception
        previous_draft = app.session_state["full_paper_draft"]
        next(b for b in app.button if b.label == "연구 근거만 추출하기").click().run()
        assert not app.exception
        assert gateway.call_count == 1 and gateway.call_args.kwargs["extract_only"] is True
        assert gateway.call_args.kwargs["planning_mode"] == "adaptive"
        assert Path(gateway.call_args.kwargs["research_pdf_path"]).is_file()
        assert app.session_state["full_paper_draft"] == previous_draft
        assert app.session_state["research_evidence_extraction"] == package
        assert any("원문 대조:" in item.value for item in app.markdown)
        if not package["completion"]["ready_for_drafting"]:
            assert any("본문 생성을 보류" in item.value for item in app.warning)
        last_page = max(1, math.ceil(len(package["items"]) / 25))
        next(s for s in app.selectbox if s.label == "목록 페이지").set_value(last_page).run()
        assert not app.exception
        last_id = package["items"][(last_page - 1) * 25]["id"]
        assert any(last_id in item.value for item in app.markdown)
        kind = next(f["kind"] for f in package["items"] if f["kind"] == "limitation")
        next(s for s in app.selectbox if s.label == "근거 유형").set_value(kind).run()
        status = next(f["claim_status"] for f in package["items"] if f["kind"] == kind)
        next(s for s in app.selectbox if s.label == "주장 강도").set_value(status).run()
        assert not app.exception
        count = sum(f["kind"] == kind and f["claim_status"] == status for f in package["items"])
        assert any(f"필터 결과 {count}개" in item.value for item in app.caption)
        assert app.session_state["full_paper_draft"] == previous_draft
    write_json(HERE / "ui-validation.json", {
        "actual_candidate_package": len(package["items"]), "extract_button_calls_gateway": True,
        "pagination_last_page": last_page, "kind_and_claim_filters": "passed",
        "completion_and_gate_display": "passed", "previous_draft_preserved": True,
        "exceptions": 0, "network_disabled": True, "gateway_mocked_for_ui": True,
        "prediction_sha256": hashlib.sha256(prediction.read_bytes()).hexdigest(),
        "independent_quality_evaluation": False})
    print(json.dumps({"ui": "passed", "candidates": len(package["items"]), "pages": last_page}))


if __name__ == "__main__":
    main()
