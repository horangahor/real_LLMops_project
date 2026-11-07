"""Local web UI: python -m uvicorn web_api:app --host 127.0.0.1 --port 8000."""
import copy
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from web_workspace import Workspace

BASE = Path(__file__).resolve().parent
ORIGINS = {f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 8000)}
MODE = Literal["requirements", "comprehensive"]


class JobRequest(BaseModel):
    action: Literal["requirements", "extract", "plan", "draft", "section", "recover", "duplicates", "instruction", "limited", "resume"]
    source_id: str = ""
    mode: MODE = "requirements"
    target_chars: int = Field(default=30000, ge=0, le=1000000)
    pending_id: str = ""
    instruction: str = Field(default="", max_length=50000)
    run_id: str = ""
    section_id: str = ""


def create_app(base=BASE):
    workspace = Workspace(base)
    app = FastAPI(title="Research Studio", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.workspace = workspace
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGINS), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("origin") not in ORIGINS | {None}:
            return JSONResponse({"detail": "로컬 UI에서만 요청할 수 있습니다."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid_request(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing_field(request, error):
        return JSONResponse({"detail": "필요한 항목이 없습니다: " + str(error)}, status_code=400)

    @app.get("/api/bootstrap")
    def bootstrap():
        from config import UPSTAGE_API_KEY
        errors = []
        try:
            reference = workspace.reference()
        except (ValueError, OSError) as error:
            reference = {"profiles": []}
            errors.append(str(error))
        try:
            latest = workspace.latest()
        except (ValueError, OSError) as error:
            latest = None
            errors.append(str(error))
        with workspace.lock:
            jobs = sorted(workspace.jobs.values(), key=lambda j: j["created_at"], reverse=True)[:20]
            return dict(sources=workspace.sources(), reference=reference, latest=latest, runs=workspace.runs(),
                        jobs=copy.deepcopy(jobs), api_configured=bool(UPSTAGE_API_KEY), errors=errors)

    @app.post("/api/sources")
    async def upload(file: UploadFile = File(...)):
        contents = bytearray()
        while chunk := await file.read(1024 * 1024):
            contents.extend(chunk)
            if len(contents) > 200 * 1024 * 1024:
                raise HTTPException(413, "PDF 파일은 200MB 이하여야 합니다.")
        return workspace.upload(bytes(contents), file.filename or "research.pdf")

    @app.get("/api/sources/{source_id}")
    def source_pdf(source_id: str):
        return FileResponse(workspace.source(source_id), media_type="application/pdf")

    @app.post("/api/jobs", status_code=202)
    def start(body: JobRequest):
        return workspace.start(body.model_dump())

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        with workspace.lock:
            if job_id not in workspace.jobs:
                raise HTTPException(404, "작업을 찾을 수 없습니다.")
            return copy.deepcopy(workspace.jobs[job_id])

    @app.get("/api/jobs/{job_id}/result")
    def result(job_id: str):
        if job_id not in workspace.jobs:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        from requirement_intervention import read_json
        return read_json(workspace.history / job_id / "result.json", {})

    @app.post("/api/evidence/load")
    def evidence_load(source_id: str, mode: MODE):
        package = workspace.load_evidence(source_id, mode)
        pending, _ = workspace.pending(source_id, mode)
        from evidence_requirements import load_requirements
        return dict(summary=workspace.evidence_summary(source_id, mode) if package else None, pending=pending,
                    requirements=load_requirements(workspace.base, workspace.reference()))

    @app.get("/api/evidence/facts")
    def facts(source_id: str, mode: MODE, q: str = "", offset: int = 0, limit: int = 40, writing_only: bool = False):
        package = workspace.package(source_id, mode)
        writing = set(package.get("writing_fact_ids", []))
        items = [f for f in package.get("items", []) if (not writing_only or f["id"] in writing)
                 and q.casefold() in (f["id"] + " " + f.get("statement", "")).casefold()]
        return dict(total=len(items), items=[{key: f.get(key) for key in ("id", "statement", "support", "claim_status", "source_origin")}
                    | {"writing": f["id"] in writing, "pages": sorted({s.get("page", 0) for s in f.get("sources", [])})}
                    for f in items[max(0, offset):max(0, offset) + min(100, max(1, limit))]])

    @app.get("/api/evidence/facts/{fact_id}")
    def fact(fact_id: str, source_id: str, mode: MODE):
        return workspace.fact_detail(source_id, mode, fact_id)

    @app.post("/api/evidence/review")
    def review(body: dict, source_id: str, mode: MODE):
        return workspace.review(source_id, mode, body)

    @app.get("/api/evidence/download")
    def evidence_download(source_id: str, mode: MODE):
        return Response(json.dumps(workspace.package(source_id, mode), ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="evidence.json"'})

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        return workspace.run(run_id)

    @app.get("/api/runs/{run_id}/sections/{section_id}")
    def section_result(run_id: str, section_id: str):
        return workspace.section_result(run_id, section_id)

    @app.get("/api/runs/{run_id}/latex")
    def paper_latex(run_id: str, view: Literal["stored", "display"] = "stored"):
        content = workspace.latex_export(run_id, display=view == "display")
        return Response(content, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="paper-{run_id.split(":")[-1]}-overleaf.zip"'})

    @app.get("/api/runs/{run_id}/sections/{section_id}/latex")
    def section_latex(run_id: str, section_id: str):
        content = workspace.latex_export(run_id, section_id)
        return Response(content, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="section-{section_id}-overleaf.zip"'})

    @app.get("/api/runs/{run_id}/download/{artifact}")
    def download(run_id: str, artifact: str):
        if artifact not in ("draft.md", "plan.json", "review.json", "review-warnings.json", "metrics.json", "sections.json", "research.json"):
            raise HTTPException(404, "지원하지 않는 산출물입니다.")
        path = workspace.run_folder(run_id) / artifact
        if not path.is_file():
            raise HTTPException(404, "아직 생성되지 않은 산출물입니다.")
        return FileResponse(path, filename=artifact)

    # One command serves the built UI and API on the same local origin.
    dist = workspace.base / "frontend/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
