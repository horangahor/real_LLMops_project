"""Local React adapter. The existing orchestrator owns every research workflow."""
import copy
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from document_parse import write_json
from paper_draft_agent import PaperDraftOrchestrator, load_paper_structure
from requirement_intervention import RequirementInterruption, read_json


def now():
    return datetime.now(timezone.utc).isoformat()


class Workspace:
    def __init__(self, base):
        self.base = Path(base).resolve()
        self.history = self.base / "draft_history/web-ui"
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paper-web")
        self.jobs = {}
        self.evidence = {}
        self.active = None
        # A restart never silently resends an external API request.
        if self.history.exists():
            for path in sorted(self.history.glob("*/job.json")):
                job = read_json(path)
                if job["status"] in ("running", "queued"):
                    job.update(status="interrupted", message="서비스가 재시작되었습니다. 같은 요청으로 재개할 수 있습니다.")
                self.jobs[job["id"]] = job

    def inside(self, path, root=None):
        # Windows extended-length paths and ordinary paths name the same files.
        # Compare in one representation without changing cached source records.
        def ordinary(value):
            value = str(value)
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
            return Path(value).resolve()
        path = ordinary(path)
        if not path.is_relative_to(ordinary(root or self.base)):
            raise ValueError("프로젝트 경로 밖의 파일에는 접근할 수 없습니다.")
        return path

    def sources(self):
        rows = []
        manifest = read_json(self.history / "uploads.json", {})
        for folder, kind in ((self.base / "input", "local"), (self.base / "draft_history/uploads", "upload")):
            for path in sorted(folder.glob("*")):
                if path.is_file() and path.suffix.lower() == ".pdf" and path.resolve().is_relative_to(folder.resolve()):
                    relative = path.relative_to(self.base).as_posix()
                    rows.append(dict(id=hashlib.sha256(relative.encode()).hexdigest()[:24],
                                     name=manifest.get(path.name, path.name), kind=kind,
                                     size=path.stat().st_size, relative=relative))
        return rows

    def source(self, source_id):
        row = next((r for r in self.sources() if r["id"] == source_id), None)
        if not row:
            raise ValueError("연구 PDF를 선택해주세요.")
        return self.inside(self.base / row["relative"])

    def upload(self, contents, name):
        if not contents.startswith(b"%PDF-"):
            raise ValueError("PDF 파일만 업로드할 수 있습니다.")
        digest = hashlib.sha256(contents).hexdigest()
        folder = self.base / "draft_history/uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (digest + ".pdf")
        with self.lock:
            if not path.exists():
                path.write_bytes(contents)
            manifest = read_json(self.history / "uploads.json", {})
            manifest[path.name] = Path(name.replace("\\", "/")).name
            write_json(self.history / "uploads.json", manifest)
        return next(row for row in self.sources() if row["relative"] == path.relative_to(self.base).as_posix())

    def reference(self):
        path = next((self.base / name for name in ("paper_structure.json", "paper_structure_analysis.json")
                     if (self.base / name).exists()), None)
        return load_paper_structure(path) if path else {"profiles": []}

    def idle(self):
        if self.active:
            raise ValueError("실행 중인 작업이 있습니다. 완료 후 다시 시도해주세요.")

    def save_job(self, job):
        write_json(self.history / job["id"] / "job.json", job)

    def update(self, job_id, **changes):
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes, updated_at=now())
            self.save_job(job)

    def start(self, request):
        # Convert public IDs to paths here; never accept client-supplied pipeline kwargs.
        action = request["action"]
        if action not in ("requirements", "extract", "plan", "draft", "section", "recover", "duplicates", "instruction", "limited", "resume"):
            raise ValueError("지원하지 않는 작업입니다.")
        if request["mode"] not in ("requirements", "comprehensive"):
            raise ValueError("근거 수집 방식을 확인해주세요.")
        if action != "requirements":
            self.source(request["source_id"])
        if action in ("recover", "duplicates") and request["mode"] != "comprehensive":
            raise ValueError("전체 수집 모드에서만 수행할 수 있습니다.")
        if action == "section":
            self.section_inputs(request)
        with self.lock:
            self.idle()
            job_id = uuid.uuid4().hex
            job = dict(id=job_id, status="queued", progress=0, message="작업 준비 중", request=request,
                       created_at=now(), updated_at=now(), events=[])
            self.jobs[job_id] = job
            self.active = job_id
            self.save_job(job)
            self.pool.submit(self._work, job_id)
            return copy.deepcopy(job)

    def pipeline_request(self, request):
        return dict(research_pdf_path=str(self.source(request["source_id"])) if request["action"] != "requirements" else None,
                    evidence_mode=request["mode"], planning_mode="adaptive", project_id="generic",
                    requirements_only=request["action"] == "requirements", extract_only=request["action"] == "extract",
                    plan_only=request["action"] == "plan", writing_target_chars=request["target_chars"])

    def _work(self, job_id):
        request = self.jobs[job_id]["request"]
        pipeline = None
        def progress(percent, message):
            with self.lock:
                events = self.jobs[job_id]["events"][-99:] + [dict(at=now(), message=message, progress=percent)]
                self.update(job_id, progress=max(0, min(100, percent)), message=message, events=events)
        try:
            self.update(job_id, status="running")
            action = request["action"]
            if action == "section":
                from planned_paper import PlannedPaper
                from section_drafting import run_saved_section
                folder = self.section_inputs(request)
                result = run_saved_section(PlannedPaper(self.base), folder, request["section_id"], progress)
            elif action in ("instruction", "limited", "resume"):
                from requirement_intervention import accept_limited_instruction, submit_instruction
                pending, pipeline = self.pending(request["source_id"], request["mode"])
                if not pending or pending["id"] != request.get("pending_id"):
                    raise ValueError("대기 질문이 변경되었습니다. 저장 근거를 다시 불러와주세요.")
                if action != "resume":
                    text = request.get("instruction", "").strip()
                    if action == "limited":
                        accept_limited_instruction(pending["run_dir"], pending["id"], text or "현재 질문은 기존 정보의 한계 안에서 진행합니다.")
                    else:
                        from planned_paper import PlannedPaper
                        submit_instruction(PlannedPaper(self.base), pending["run_dir"], pending["id"], text)
                elif pending["status"] != "instruction_saved":
                    raise ValueError("먼저 질문에 대한 지시 또는 임시 승인을 저장해주세요.")
                # Retain the interrupted job's exact original parameters and cache identity.
                allowed = {"research_pdf_path", "results_json_path", "structure_json_path", "planning_mode", "project_id",
                           "plan_only", "output_dir", "extract_only", "evidence_mode", "research_scope", "requirements_only", "writing_target_chars"}
                if set(pipeline) - allowed:
                    raise ValueError("저장된 재개 요청의 형식이 잘못됐습니다.")
                for key in ("research_pdf_path", "results_json_path", "structure_json_path", "output_dir"):
                    if pipeline.get(key):
                        self.inside(pipeline[key])
                pipeline.setdefault("writing_target_chars", 0)
            elif action in ("recover", "duplicates"):
                from planned_paper import PlannedPaper
                from research_extract_v3 import run_unconfirmed_recovery, run_semantic_duplicate_review
                package = self._load_evidence(request["source_id"], request["mode"])
                if not package:
                    raise ValueError("완료된 저장 근거가 없습니다. 먼저 근거를 추출해주세요.")
                progress(5, "저장 근거 복구·중복 검토 중")
                (run_unconfirmed_recovery if action == "recover" else run_semantic_duplicate_review)(package, PlannedPaper(self.base))
                result = dict(evidence_extraction=package, run_dir=package["run_dir"])
            else:
                pipeline = self.pipeline_request(request)
            if pipeline is not None:
                result = PaperDraftOrchestrator().run_pipeline(**pipeline, progress_callback=progress)
            package = result.get("evidence_extraction")
            with self.lock:
                if package:
                    self.evidence[(request["source_id"], request["mode"])] = package
            # Full raw API payloads remain in their existing workflow folders.
            visible = result if action == "section" else {key: result.get(key) for key in (
                "draft_markdown", "plan", "run_dir", "writing_length", "evidence_requirements") if result.get(key) is not None}
            write_json(self.history / job_id / "result.json", visible)
            self.update(job_id, status="completed", progress=100, message="작업을 완료하고 결과를 저장했습니다.", run_dir=result.get("run_dir"))
        except RequirementInterruption as error:
            write_json(Path(error.pending["run_dir"]) / "interrupted-request.json", pipeline)
            self.update(job_id, status="awaiting_input", message=str(error), pending=error.pending)
        except Exception as error:
            self.update(job_id, status="failed", message=str(error))
        finally:
            with self.lock:
                self.active = None

    def pending(self, source_id, mode):
        if mode != "requirements":
            return None, None
        from evidence_requirements import load_requirements
        from requirement_intervention import restore_pending
        requirements = load_requirements(self.base, self.reference())
        restored = restore_pending(self.base, self.source(source_id), requirements) if requirements else None
        return restored or (None, None)

    def _load_evidence(self, source_id, mode):
        pdf = self.source(source_id)
        if mode == "requirements":
            from evidence_requirements import load_requirements
            from requirement_extraction import load_saved_requirement_evidence
            requirements = load_requirements(self.base, self.reference())
            package = load_saved_requirement_evidence(pdf, self.base, requirements) if requirements else None
        else:
            from research_extract_v3 import load_saved_evidence
            package = load_saved_evidence(pdf, self.base)
        if package:
            self.inside(package["run_dir"], self.base / "draft_history")
            if package.get("source_archive_path"):
                self.inside(package["source_archive_path"], self.base / "draft_history")
            self.evidence[(source_id, mode)] = package
        return package

    def load_evidence(self, source_id, mode):
        with self.lock:
            self.idle()
            return self._load_evidence(source_id, mode)

    def package(self, source_id, mode):
        package = self.evidence.get((source_id, mode))
        if package is None:
            raise ValueError("저장된 연구 근거를 먼저 불러와주세요.")
        return package

    def evidence_summary(self, source_id, mode):
        package = self.package(source_id, mode)
        return {key: package.get(key) for key in ("version", "run_dir", "source", "diagnostics", "completion", "requirements",
                  "requirement_coverage", "requirement_applicability", "semantic_duplicate_review", "human_duplicate_decisions",
                  "human_evidence_exclusions", "human_gate_decisions", "writing_fact_ids")} | {"total": len(package.get("items", []))}

    def fact_detail(self, source_id, mode, fact_id):
        from research_extract_v3 import contextual_source_packet, human_fact_review_id, measurement_review_id
        package = self.package(source_id, mode)
        fact = next((f for f in package.get("items", []) if f["id"] == fact_id), None)
        if not fact:
            raise ValueError("근거를 찾을 수 없습니다.")
        elements = []
        if package.get("source_archive_path"):
            path = self.inside(package["source_archive_path"], self.base / "draft_history")
            archive = read_json(path, {})
            records = {e["element_id"]: e for e in archive.get("elements", [])}
            elements = contextual_source_packet(records, [s["element_id"] for s in fact.get("sources", []) if s["element_id"] in records])
        return dict(fact=fact, context=elements, review_id=human_fact_review_id(fact),
                    measurement_ids=[measurement_review_id(fact_id, m, i) for i, m in enumerate(fact.get("rejected_measurements", []))])

    def review(self, source_id, mode, body):
        if mode != "comprehensive":
            raise ValueError("질문 기준 근거는 질문별 사용자 지시에서 처리해주세요.")
        import research_extract_v3 as evidence
        with self.lock:
            self.idle()
            package = self.package(source_id, mode)
            action = body["action"]
            if action in ("approve_fact", "approve_measurement") and body.get("confirmed") is not True:
                raise ValueError("원문 확인 및 승인 체크가 필요합니다.")
            if action == "approve_fact":
                evidence.approve_human_fact(package, body["fact_id"], body["review_id"], body["value"])
            elif action == "approve_measurement":
                evidence.approve_rejected_measurement(package, body["fact_id"], body["review_id"], body["value"])
            elif action == "exclude":
                evidence.set_human_evidence_exclusion(package, body.get("target_type", "fact"), body["fact_id"],
                    body.get("target_id", body["fact_id"]), body.get("reason", ""), body.get("reason_detail", ""),
                    original_measurement=body.get("original_measurement"), excluded=body.get("excluded", True))
            elif action == "gate":
                evidence.accept_gate_item(package, body["item"], body.get("reason", ""))
            elif action == "duplicate":
                evidence.resolve_semantic_duplicate_group(package, body["group_id"], body["decision"], body.get("keep_fact_id"))
            else:
                raise ValueError("지원하지 않는 검토 작업입니다.")
            return self.evidence_summary(source_id, mode)

    def run_folder(self, run_id):
        parts = run_id.split(":")
        if len(parts) != 2 or any(not p or not all(c.isalnum() or c in "_-" for c in p) for p in parts):
            raise ValueError("실행 ID가 잘못됐습니다.")
        path = self.inside(self.base / "draft_history/planned" / parts[0] / parts[1], self.base / "draft_history/planned")
        if not path.is_dir():
            raise ValueError("실행 결과를 찾을 수 없습니다.")
        return path

    def section_inputs(self, request):
        from section_drafting import load_section_inputs
        folder = self.run_folder(request.get("run_id", ""))
        _, research, _, _, _ = load_section_inputs(folder, request.get("section_id", ""))
        digest = hashlib.sha256(self.source(request["source_id"]).read_bytes()).hexdigest()
        if research.get("source", {}).get("sha256") != digest:
            raise ValueError("이 계획에 연결된 연구 PDF를 선택해주세요. 다른 자료의 절은 생성하지 않습니다.")
        mode = "requirements" if research.get("evidence_requirements") else "comprehensive"
        if request["mode"] != mode:
            raise ValueError("이 작성 계획의 근거 수집 모드(" + mode + ")를 선택해주세요.")
        return folder

    def section_result(self, run_id, section_id):
        from paper_plan import IDENTIFIER
        if not IDENTIFIER.fullmatch(section_id):
            raise ValueError("절 ID가 잘못됐습니다.")
        folder = self.run_folder(run_id)
        plan = read_json(folder / "plan.json", {})
        if section_id not in plan.get("generation_order", []):
            raise ValueError("작성 계획에 없는 절입니다.")
        value = read_json(folder / "section-runs" / section_id / "result.json")
        if value is None:
            raise ValueError("이 절의 개별 생성 결과가 없습니다. ‘이 절만 생성·재개’를 실행해주세요.")
        from planned_paper import fingerprint
        if value.get("plan_fingerprint") != fingerprint(plan):
            raise ValueError("절 생성 이후 작성 계획이 바뀌었습니다. 같은 절을 다시 생성·재개해주세요.")
        return value

    def latex_export(self, run_id, section_id=None, *, display=False):
        from latex_export import project_zip, paragraph_sources
        folder = self.run_folder(run_id)
        if section_id is not None:
            value = self.section_result(run_id, section_id)
            markdown = value["draft_markdown"]
            title = read_json(folder / "plan.json", {}).get("title")
            provenance = value.get("provenance", [])
            source = value.get("source", {})
            scope = "section"
        else:
            value = self.run(run_id)
            if display:
                latest = self.latest()
                if latest and latest["id"] == run_id:
                    value = latest
            markdown = value.get("draft_markdown", "")
            if not markdown.strip():
                raise ValueError("완성된 전체 초안이 없습니다. 초안 또는 절을 먼저 생성해주세요.")
            research = read_json(folder / "research.json", {})
            provenance = paragraph_sources(read_json(folder / "sections.json", {}).get("final", {}), research)
            title = (value.get("plan") or {}).get("title")
            source = research.get("source", {})
            scope = "paper"
        return project_zip(markdown, title=title, provenance=provenance, metadata={
            "run_id": run_id, "scope": scope, "section_id": section_id, "source": source})

    def runs(self):
        root = self.base / "draft_history/planned"
        folders = sorted((p for p in root.glob("*/*") if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        rows = []
        for path in folders[:40]:
            files = [name for name in ("draft.md", "plan.json", "review.json", "review-warnings.json", "metrics.json", "sections.json", "research.json") if (path / name).is_file()]
            if files:
                rows.append(dict(id=path.parent.name + ":" + path.name, name=path.name, project=path.parent.name,
                                 updated_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), files=files))
        return rows

    def run(self, run_id):
        folder = self.run_folder(run_id)
        metrics = read_json(folder / "metrics.json", {})
        return dict(id=run_id, run_dir=str(folder), plan=read_json(folder / "plan.json"), metrics=metrics,
                    draft_markdown=(folder / "draft.md").read_text(encoding="utf-8") if (folder / "draft.md").exists() else "",
                    writing_length=metrics.get("writing_length"))

    def latest(self):
        from planned_paper import load_latest
        pointer = read_json(self.base / "draft_history/planned/latest.json")
        if not pointer:
            return None
        latest = load_latest(self.base, refresh_layout=True)
        folder = self.inside(pointer["run_dir"], self.base / "draft_history/planned")
        return dict(id=folder.parent.name + ":" + folder.name, run_dir=str(folder), plan=latest["plan"],
                    draft_markdown=latest["draft_markdown"], layout_refreshed=latest.get("layout_refreshed", False),
                    metrics=read_json(folder / "metrics.json", {}))
