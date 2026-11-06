"""Split large prose requests into parts and source-preserving evidence batches."""

import copy
import re

from drafting_budget import (DraftingBudgetError, NO_CACHE, SOURCE_PROTOCOL, cached_response,
                             call_bounded, compact_packet, fits_request)
from draft_prose import (PROTOCOL, JoinedParagraphsError, prose_schema, render_generation,
                         render_parts, structured_system)
from paper_plan import object_schema

FRAGMENT = """\n현재 요청은 큰 작성·편집 단계의 일부다. 전체 목차는 outline에 있다.
지금 facts로 배정된 근거에 해당하는 내용만 완결된 짧은 문단으로 작성·수정한다.
다른 묶음의 내용을 추측해 채우거나 같은 서론·요약을 반복하지 않는다. 모든 주장은 현재 facts의 ID를 인용한다.
source_body는 편집할 원래 본문이다. 현재 facts에 속하는 내용만 이번 조각에 반영한다.
사용자 승인 범위와 조건·한계를 유지한다. parts.p0에 제목·표 없는 본문만 반환한다."""
REVISION = """\n이번 요청은 검토 후 수정이다. revision.previous_sections는 가장 최근 후보 본문이다.
분할 요청의 source_body가 있으면 그 문단을 수정하며, 지적과 무관한 기존 내용·인용을 보존한다.
fragment.operation=missing_evidence이면 이전 본문 전체를 다시 쓰지 않고 현재 facts에 해당하는 누락 내용만 보완한다.
이때 fragment.missing_evidence_ids의 내용을 조건·한계에 맞게 서술하고 실제 해당 문단에 연결한다. 이미 있는 내용의 반복은 피한다.
관측·해석·계획·인용된 조언을 구별하고 facts.limits의 단일 관측·미검증·기대 효과 등의 한계를 문장에 반영한다.
검토 통과를 위해 근거 ID만 붙이거나 추정·조언을 구현 결과·확정 원인으로 바꾸지 않는다."""


def scope_fragment_revision(packet):
    """Only the target paragraph and global findings may guide its rewrite."""
    fragment = packet.get("fragment", {})
    pid = fragment.get("paragraph_id")
    if not pid and fragment.get("operation") != "missing_evidence" and not packet.get("fragment_validation_error"):
        return packet
    result = copy.deepcopy(packet)
    feedback = result.get("revision")
    if feedback is not None:
        report = feedback.get("review", {})
        issues = []
        for issue in report.get("issues", []):
            if issue.get("paragraph_id") not in (None, "none", pid):
                continue
            row = copy.deepcopy(issue)
            if row.get("quote", "").strip() == result.get("source_body", "").strip():
                row.pop("quote", None)
            issues.append(row)
        # Derived warning/history fields can contain the same sibling quotes.
        # The original report stays on disk; only actionable scoped input goes out.
        checks = [{k: copy.deepcopy(v) for k, v in check.items() if k != "paragraph_quotes"}
                  for check in report.get("checks", [])]
        feedback["review"] = {"checks": checks, "issues": issues}
        feedback["scope"] = {"policy": "fragment-review-scope-v2", "paragraph_id": pid or "none",
                             "operation": fragment.get("operation", "generate")}
        feedback["fragment_instruction"] = (
            "현재 source_body와 현재 facts 범위만 작성·수정한다. 다른 문단의 인용문을 답으로 재출력하지 않는다. "
            "source_body에 다른 묶음의 내용이 함께 있어도 이번 출력은 현재 facts로 뒷받침되는 부분만 다룬다.")
    error = result.get("fragment_validation_error")
    if isinstance(error, dict):
        # The complete failed response is already retained in *-invalid-N.json.
        result["fragment_validation_error"] = {k: v for k, v in error.items() if k != "response"}
    return result


def call_structured(engine, folder, name, system, packet, schema, *, fragment=False):
    # Read completed old requests before sending a request with one citation rule.
    for base_system in dict.fromkeys((system, structured_system(system))):
        for old_system, old_packet in ((base_system, packet), (base_system + SOURCE_PROTOCOL, compact_packet(packet))):
            cached = cached_response(engine, folder, name, old_system, old_packet, schema)
            if cached is NO_CACHE:
                continue
            if fragment:
                try:
                    render_parts(cached, packet)
                except JoinedParagraphsError:
                    pass  # Keep the lossless paragraph-only format repair path.
                except (ValueError, KeyError, TypeError):
                    continue
            return cached
    request = scope_fragment_revision(packet) if fragment else packet
    if request != packet:
        from document_parse import write_json
        previous = packet.get("revision", {}).get("review", {}).get("issues", [])
        retained = request.get("revision", {}).get("review", {}).get("issues", [])
        write_json(folder / f"{name}-revision-input-scope.json", {
            "policy": "fragment-review-scope-v2", "fragment": request["fragment"],
            "previous_finding_paragraphs": [i.get("paragraph_id") for i in previous],
            "retained_finding_paragraphs": [i.get("paragraph_id") for i in retained],
            "source_body_unchanged": request.get("source_body") == packet.get("source_body"),
            "facts_unchanged": request.get("facts") == packet.get("facts"),
            "tables_unchanged": request.get("tables") == packet.get("tables"),
            "failed_body_resent": "response" in request.get("fragment_validation_error", {})})
    return call_bounded(engine, folder, name, structured_system(system), request, schema)


def cited_ids(text):
    return set(key for group in re.findall(r"\[근거:\s*([^\]]+)\]", text)
               for key in re.split(r"[,，;·\s]+", group.strip()) if key)


def evidence_groups(facts, tables, requirements=()):
    """Keep table comparisons and small explicit requirement pairs together."""
    indexed = {f["id"]: f for f in facts}
    parents = {key: key for key in indexed}
    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    for ids in ([t["evidence_ids"] for t in tables] +
                [i["evidence_ids"] for i in requirements if 1 < len(i["evidence_ids"]) <= 8]):
        keys = [key for key in ids if key in indexed]
        for key in keys[1:]:
            parents[find(key)] = find(keys[0])
    groups = {}
    for key, fact in indexed.items():
        groups.setdefault(find(key), []).append(fact)
    return list(groups.values())


def pack_groups(groups, make_packet, system, schema):
    batches, current = [], []
    for group in groups:
        if fits_request(system, make_packet(current + group), schema):
            current += group
            continue
        if current:
            batches.append(current)
            current = []
        if not fits_request(system, make_packet(group), schema):
            ids = [f["id"] for f in group]
            raise DraftingBudgetError(f"단일 근거·비교 묶음이 입력 예산을 넘습니다: {ids}. 원문을 자르지 않고 요청을 중단했습니다.")
        current = list(group)
    if current:
        batches.append(current)
    return batches


def slim_feedback(feedback, section_id, facts):
    if not feedback:
        return None
    ids = {f["id"] for f in facts}
    result = {}
    if "validation_error" in feedback:
        result["validation_error"] = feedback["validation_error"]
    if "repair_instruction" in feedback:
        result["repair_instruction"] = feedback["repair_instruction"]
    if "content_repair_instruction" in feedback:
        result["content_repair_instruction"] = feedback["content_repair_instruction"]
    if "evidence_link_gaps" in feedback:
        result["evidence_link_gaps"] = [copy.deepcopy(gap) for gap in feedback["evidence_link_gaps"] if gap["evidence_id"] in ids]
    report = feedback.get("review", {})
    result["review"] = {"checks": [
        {"item_id": c["item_id"], "verdict": c["verdict"],
         "evidence_ids": [key for key in c["evidence_ids"] if key in ids],
         **{field: [key for key in c[field] if key in ids] for field in
            ("missing_body_evidence_ids", "missing_review_evidence_ids") if field in c},
         **{field: copy.deepcopy(c[field]) for field in ("paragraph_ids", "model_verdict", "validation_note") if field in c}}
        for c in report.get("checks", []) if not c["evidence_ids"] or ids.intersection(
            c["evidence_ids"] + c.get("missing_body_evidence_ids", []) + c.get("missing_review_evidence_ids", []))],
        "issues": [{k: copy.deepcopy(v) for k, v in issue.items() if k != "paragraph_quotes"}
                   for issue in report.get("issues", []) if issue["section_id"] == section_id
                   and (not issue["evidence_ids"] or ids.intersection(issue["evidence_ids"]))]}
    return result


def compact_fragment_revision(request):
    """Scope oversized revision feedback without changing any source evidence."""
    result = copy.deepcopy(request)
    fragment = result["fragment"]
    pid = fragment.get("paragraph_id")
    source = result["source_body"].strip()
    feedback = result["revision"]
    issues = []
    for issue in feedback["review"]["issues"]:
        target = issue.get("paragraph_id")
        # Other paragraphs have their own tasks. A missing-evidence task adds
        # new prose, so it must not rewrite an existing paragraph's findings.
        if target not in (None, "none", pid):
            continue
        row = copy.deepcopy(issue)
        if row.get("quote", "").strip() == source:
            row.pop("quote", None)  # Exact text is already in source_body.
        issues.append(row)
    feedback["review"]["issues"] = issues
    feedback["scope"] = {"policy": "fragment-revision-context-v1",
                         "paragraph_id": pid or "none", "operation": fragment.get("operation", "generate")}
    return result


def _revision_windows(packet, sid, key, full):
    """Bind the latest candidate's exact windows to the review's paragraph IDs."""
    from planned_paper import compose_parts, index_paragraphs
    previous = packet.get("revision", {}).get("previous_sections", {}).get(sid)
    if previous is None:
        return None
    paragraphs = index_paragraphs({sid: compose_parts(previous, full)})
    # Repeated identical paragraphs are matched by occurrence, never by first text hit.
    locations = {}
    for part, text in previous["parts"].items():
        locations[part] = []
        for window in re.split(r"\n\s*\n", text):
            pid = next((pid for pid, row in paragraphs.items() if row["text"] == window.strip()), None)
            if pid is None:
                raise ValueError("수정 본문과 검토 문단의 연결이 일치하지 않습니다.")
            paragraphs.pop(pid)
            locations[part].append((pid, window))
    return locations[key]


def _needs_revision(pid, text, section_id, report, meta=None):
    from paragraph_revision import local_issues
    cited = cited_ids(text)
    for issue in local_issues(report, pid, text, meta or {}):
        if issue["section_id"] != section_id or issue["severity"] != "error":
            continue
        if issue.get("validation_code") == "required_content" or (
                not issue.get("paragraph_id") and issue.get("reason", "").startswith("필수 내용 ")):
            continue  # Missing IDs get their own source-bound task below.
        if issue.get("paragraph_id") == pid:
            return True
        if issue.get("paragraph_id") in (None, "none") and (
                not issue["evidence_ids"] or cited.intersection(issue["evidence_ids"])):
            return True
    for check in report.get("checks", []):
        if check["verdict"] in ("missing", "incorrect") and check.get("model_verdict") != "met":
            if pid in check.get("paragraph_ids", []) or (meta or {}).get("single_paragraph") and not check.get("paragraph_ids"):
                return True
    return False


def generation_fragments(system, packet, packets):
    """Build bounded requests without dropping source facts or splitting comparisons."""
    from paper_context import part_context
    outline = [{k: copy.deepcopy(p["section_plan"][k]) for k in ("id", "title", "role", "purpose")}
               for p in packets.values()]
    tasks = []
    for sid, full in packets.items():
        assignments = full.get("subsection_assignments", {"p0": {}})
        for key in assignments:
            scoped = part_context(full, key) if "subsection_assignments" in full else copy.deepcopy(full)
            schema = prose_schema(scoped)
            body = packet.get("child_parts", {}).get(key, "")
            if "sections" in packet:
                body = packet["sections"][sid]["parts"][key]
            revision_windows = _revision_windows(packet, sid, key, full)
            if revision_windows is not None:
                body = "\n\n".join(text for _, text in revision_windows)
            revision = packet.get("revision", {})
            report = revision.get("review", {})
            item_ids = {item["id"] for item in scoped["section_plan"]["required_items"]}
            report = {**report, "checks": [c for c in report.get("checks", []) if c["item_id"] in item_ids]}
            local_revision = {**revision, "review": report}
            facts = scoped["facts"]
            # Editors need the facts actually cited in the prose, plus the
            # explicitly required candidates needed to address review findings.
            def make(selected, source_body, paragraph_id=None, operation=None):
                ids = {f["id"] for f in selected}
                section = copy.deepcopy(scoped["section_plan"])
                section["evidence_ids"] = [f["id"] for f in selected]
                section["subsections"] = []
                section["required_items"] = [{**copy.deepcopy(i),
                    "evidence_ids": [key for key in i["evidence_ids"] if key in ids]}
                    for i in section["required_items"] if not i["evidence_ids"] or ids.intersection(i["evidence_ids"])]
                tables = [t for t in scoped["tables"] if set(t["evidence_ids"]) <= ids]
                section["table_ids"] = [t["id"] for t in tables]
                if "table_placements" in section:
                    section["table_placements"] = [p for p in section["table_placements"] if p["table_id"] in section["table_ids"]]
                request = {**{k: copy.deepcopy(v) for k, v in scoped.items()
                              if k not in ("revision", "child_parts", "sections", "section_packets")},
                    "section_plan": section, "facts": selected,
                    "tables": tables, "source_body": source_body, "outline": outline,
                    "subsection_headings": [], "workflow_stage": packet.get("workflow_stage"),
                    "fragment": {"section_id": sid, "part": key}}
                if operation is not None:
                    request["fragment"]["operation"] = operation
                if paragraph_id is not None:
                    request["fragment"]["paragraph_id"] = paragraph_id
                    request["fragment"]["whole_part_single_paragraph"] = len(revision_windows or []) == 1
                if operation == "missing_evidence":
                    request["fragment"]["missing_evidence_ids"] = [f["id"] for f in selected if f["id"] in missing]
                feedback = slim_feedback(local_revision, sid, selected) if revision else None
                if feedback:
                    request["revision"] = feedback
                if operation == "revise_paragraph":
                    from paragraph_revision import scope_request
                    request = scope_request(request)
                # Keep fitting requests unchanged so completed responses remain
                # reusable. Only oversized paragraph/gap revisions shed repeated
                # prose and findings belonging to independently revised windows.
                if (revision_windows is not None and feedback
                        and not fits_request(system + FRAGMENT + PROTOCOL, request, schema)):
                    request = compact_fragment_revision(request)
                return request
            windows = revision_windows if revision_windows is not None else [
                (None, text) for text in (re.split(r"\n\s*\n", body) if body else [""])]
            content_targets = {}
            if revision_windows is not None:
                for check in report.get("checks", []):
                    if check["verdict"] not in ("missing", "incorrect") or check.get("model_verdict") == "met":
                        continue
                    item = next(i for i in scoped["section_plan"]["required_items"] if i["id"] == check["item_id"])
                    target = next((pid for pid, _ in windows if pid in check.get("paragraph_ids", [])), None)
                    if target is None and len(windows) == 1:
                        target = windows[0][0]
                    if target is not None:
                        explicit_missing = check.get("missing_section_evidence_ids", check.get("missing_body_evidence_ids", []))
                        content_targets.setdefault(target, set()).update(explicit_missing)
            cited_before = set().union(*(cited_ids(text) for _, text in windows))
            for window_index, (pid, window) in enumerate(windows):
                if revision_windows is not None and pid not in content_targets and not _needs_revision(pid, window, sid, report, {**scoped.get("composition_policy", {}), "single_paragraph": len(windows) == 1}):
                    tasks.append((sid, key, f"revision-{window_index}-text", {"passthrough": window}, None))
                    continue
                selected = set(cited_ids(window)) if body else {f["id"] for f in facts}
                selected.update(content_targets.get(pid, set()))
                if revision_windows is not None:
                    for issue in report.get("issues", []):
                        if issue.get("paragraph_id") == pid and issue["severity"] == "error":
                            selected.update(key for key in issue["evidence_ids"] if key in scoped["section_plan"]["evidence_ids"])
                    if not selected:
                        selected = {f["id"] for f in facts}
                if body and not selected:
                    # Preserve connecting prose; the source and coherence
                    # reviewers still inspect uncited research claims later.
                    tasks.append((sid, key, f"{window_index}-text", {"passthrough": window}, None))
                    continue
                if body and window_index == 0 and revision_windows is None:
                    failed = {c["item_id"] for c in packet.get("revision", {}).get("review", {}).get("checks", [])
                              if c["verdict"] in ("missing", "incorrect")}
                    for item in scoped["section_plan"]["required_items"]:
                        if item["id"] in failed:
                            # Candidate context may help repair missing content,
                            # but is never a list that must all be cited.
                            selected.update(item["evidence_ids"])
                changed = True
                while changed:
                    before = set(selected)
                    for table in scoped["tables"]:
                        if selected.intersection(table["evidence_ids"]):
                            selected.update(table["evidence_ids"])
                    changed = before != selected
                if not selected <= {f["id"] for f in facts}:
                    raise ValueError("분할 편집 문단의 근거가 해당 소절 범위를 벗어났습니다.")
                groups = evidence_groups([f for f in facts if f["id"] in selected], scoped["tables"],
                                         scoped["section_plan"]["required_items"])
                make_window = lambda batch: make(batch, window,
                    paragraph_id=pid if revision_windows is not None else None,
                    operation="revise_paragraph" if revision_windows is not None else None)
                if revision_windows is not None:
                    from paragraph_revision import schema_for
                    request = make_window([f for f in facts if f["id"] in selected])
                    tasks.append((sid, key, f"{window_index}-0", request, schema_for(request)))
                    continue
                batches = pack_groups(groups, make_window, system + FRAGMENT + PROTOCOL, schema)
                if not batches:
                    raise DraftingBudgetError(f"{sid}/{key}에 작성할 근거가 없습니다.")
                for index, batch in enumerate(batches):
                    request = make_window(batch)
                    tasks.append((sid, key, f"{window_index}-{index}", request, prose_schema(request)))
            if revision_windows is not None:
                missing = {eid for check in report.get("checks", [])
                           for eid in check.get("missing_section_evidence_ids", []) if eid not in cited_before}
                for gap in packet.get("revision", {}).get("evidence_link_gaps", []):
                    if gap["evidence_id"] in scoped["section_plan"]["evidence_ids"] and gap["evidence_id"] not in cited_before:
                        missing.add(gap["evidence_id"])
                # Keep comparison groups intact, even when one side is already cited.
                groups = evidence_groups(facts, scoped["tables"], scoped["section_plan"]["required_items"])
                groups = [group for group in groups if missing.intersection(f["id"] for f in group)]
                def make_gap(batch):
                    return make(batch, "", operation="missing_evidence")
                for index, batch in enumerate(pack_groups(groups, make_gap, system + FRAGMENT + PROTOCOL, schema)):
                    request = make_gap(batch)
                    tasks.append((sid, key, f"missing-{index}", request, prose_schema(request)))
    from writing_length import allocate_fragment_targets
    return allocate_fragment_targets(tasks, packets)


def generate_bounded(engine, folder, name, system, packet, schema, packets, single, *, on_warning=None):
    """Generate valid prose; report exhausted content gaps separately from format errors."""
    from document_parse import write_json
    from planned_paper import parts_schema
    from writing_length import INSTRUCTION as LENGTH_INSTRUCTION
    if packet.get("writing_budget"):
        system += LENGTH_INSTRUCTION
    revising = bool(packet.get("revision", {}).get("previous_sections"))
    if revising:
        # Changed repair semantics must not replay an old whole-body rewrite.
        system += REVISION
    # Check both old request representations without making a legacy-format
    # network call. Invalid cached prose must not replay the original failure.
    for old_system, old_packet in ([] if revising else ((system, packet), (system + SOURCE_PROTOCOL, compact_packet(packet)))):
        cached = cached_response(engine, folder, name, old_system, old_packet, schema)
        if cached is not NO_CACHE:
            try:
                return render_generation(cached, packets, single)
            except (ValueError, KeyError, TypeError) as error:
                write_json(folder / f"{name}-legacy-rejected.json", {"validation_error": str(error)})
    structured_schema = (prose_schema(next(iter(packets.values()))) if single else
                         object_schema({"sections": object_schema({key: prose_schema(p) for key, p in packets.items()})}))
    if not revising and fits_request(system + PROTOCOL, packet, structured_schema):
        response = call_structured(engine, folder, name, system + PROTOCOL, packet, structured_schema)
        try:
            render_generation(response, packets, single)
        except JoinedParagraphsError:
            from prose_format_repair import repair_joined_paragraphs
            return repair_joined_paragraphs(engine, folder, name, response, packets, single)
        except (ValueError, KeyError, TypeError):
            pass  # Other format errors retain the existing outer repair path.
        return response
    tasks = generation_fragments(system, packet, packets)
    result = {key: {"parts": {}} for key in packets}
    manifest, warnings = [], []
    for sid, key, index, request, fragment_schema in tasks:
        if fragment_schema is None:
            result[sid]["parts"].setdefault(key, []).append(request["passthrough"])
            manifest.append({"section_id": sid, "part": key, "batch": index, "preserved_connecting_text": True})
            continue
        if request.get("fragment", {}).get("operation") == "revise_paragraph":
            from paragraph_revision import replace_paragraph, POLICY as REPLACEMENT_POLICY
            fragment_name = f"{name}-split-{sid}-{key}-{index}"
            body, warning = replace_paragraph(engine, folder, fragment_name, system, request)
            result[sid]["parts"].setdefault(key, []).append(body)
            if warning:
                warnings.append(warning)
            manifest.append({"section_id": sid, "part": key, "batch": index,
                "operation": "revise_paragraph", "paragraph_id": request["fragment"]["paragraph_id"],
                "evidence_ids": [f["id"] for f in request["facts"]], "replacement_policy": REPLACEMENT_POLICY,
                "paragraph_count": 1, "original_preserved": warning is not None})
            continue
        error, deferred_missing = None, []
        for repair in range(2):
            bounded_packet = request if error is None else {**request, "fragment_validation_error": error}
            fragment_name = f"{name}-split-{sid}-{key}-{index}" + ("-repair" if repair else "")
            legacy_schema = parts_schema(request)
            response = NO_CACHE
            if repair and error.get("validation_code") == "joined_paragraphs":
                from prose_format_repair import repair_joined_paragraphs
                response = repair_joined_paragraphs(engine, folder, fragment_name, error["response"],
                                                   {sid: request}, True)
            legacy_candidates = [] if response is not NO_CACHE else [
                (system + FRAGMENT, bounded_packet),
                (system + FRAGMENT + SOURCE_PROTOCOL, compact_packet(bounded_packet))]
            for old_system, old_packet in legacy_candidates:
                legacy = cached_response(engine, folder, fragment_name, old_system, old_packet, legacy_schema)
                if legacy is not NO_CACHE:
                    try:
                        response = render_parts(legacy, request)
                        break
                    except (ValueError, KeyError, TypeError):
                        pass
            if response is NO_CACHE:
                response = call_structured(engine, folder, fragment_name, system + FRAGMENT + PROTOCOL,
                                          bounded_packet, fragment_schema, fragment=True)
            try:
                body = render_parts(response, request)["parts"]["p0"]
                missing = set(request["fragment"].get("missing_evidence_ids", [])) - cited_ids(body)
                if missing:
                    # The prose and all actual citations have passed render_parts.
                    # Failure to include every requested fact is a content gap,
                    # not an invalid ID or broken paragraph. Preserve the same
                    # first error/repair packet so saved repair responses replay.
                    if repair == 1:
                        deferred_missing = sorted(missing)
                        write_json(folder / f"{name}-split-{sid}-{key}-{index}-content-warning.json", {
                            "missing_evidence_ids": deferred_missing, "response": response,
                            "status": "needs_attention", "attempts": repair + 1})
                        break
                    raise ValueError(f"누락 보완 응답에서 요청한 근거가 다시 빠졌습니다: {sorted(missing)}")
                break
            except (ValueError, KeyError, TypeError) as exc:
                error = {"error": str(exc), "response": response}
                if isinstance(exc, JoinedParagraphsError):
                    error["validation_code"] = "joined_paragraphs"
                write_json(folder / f"{name}-split-{sid}-{key}-{index}-invalid-{repair}.json", error)
        else:
            raise ValueError(f"분할 본문 {sid}/{key}/{index}이 보정 후에도 근거·구조 검증에 실패했습니다. "
                             f"원인: {error['error']} 상세: {folder / f'{name}-split-{sid}-{key}-{index}-invalid-1.json'}")
        result[sid]["parts"].setdefault(key, []).append(body)
        if deferred_missing:
            warnings.append({"section_id": sid, "part": key, "paragraph_id": "none",
                "severity": "warning", "original_severity": "error", "deferred": True,
                "validation_code": "fragment_missing_evidence", "review_stage": "generation_completion",
                "failure_owner": "writer", "evidence_ids": deferred_missing,
                "generation_request": name, "fragment_batch": index, "repair_attempts": 1})
        manifest.append({"section_id": sid, "part": key, "batch": index,
                         "evidence_ids": [f["id"] for f in request["facts"]],
                         "operation": request["fragment"].get("operation", "generate"),
                         "paragraph_id": request["fragment"].get("paragraph_id"),
                         **({"revision_scope": request["revision"]["scope"]}
                            if "scope" in request.get("revision", {}) else {}),
                         **({"deferred_missing_evidence_ids": deferred_missing} if deferred_missing else {})})
    for section in result.values():
        section["parts"] = {key: "\n\n".join(values) for key, values in section["parts"].items()}
    from content_review_completion import reconcile_generation_warnings
    warnings = reconcile_generation_warnings(warnings, result, packets)
    write_json(folder / f"{name}-split-manifest.json", {"tasks": manifest, "content_warnings": warnings})
    if on_warning is not None:
        for warning in warnings:
            on_warning(copy.deepcopy(warning))
    return result[next(iter(result))] if single else {"sections": result}
