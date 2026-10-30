"""Retain every source element and re-read suspicious numeric OCR without altering native text."""

import hashlib
import json
import re
import unicodedata
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from document_parse import DEFAULT_MODEL, parse_document, write_json
from paper_outline import element_text
from research_sources import load_sources


def suspicious_number_spacing(text):
    return bool(re.search(r"(?m)^\s*\d[ \t]+\d+(?:[.,]\d+)?\s*(?:ms|us|μs|s(?![A-Za-z])|회|개|%)", text))


def covered_fraction(rect, boxes):
    x0, y0, x1, y1 = rect
    area = max(0, x1 - x0) * max(0, y1 - y0)
    if not area:
        return 0
    clipped = [(max(x0, a), max(y0, b), min(x1, c), min(y1, d)) for a, b, c, d in boxes
               if min(x1, c) > max(x0, a) and min(y1, d) > max(y0, b)]
    xs = sorted({v for r in clipped for v in (r[0], r[2])})
    covered = 0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((b, d) for a, b, c, d in clipped if a < right and c > left)
        length, end = 0, float("-inf")
        for bottom, top in intervals:
            length += max(0, top - max(bottom, end))
            end = max(end, top)
        covered += (right - left) * length
    return covered / area


def add_physical_gaps(pdf, result, root):
    import pymupdf
    compact = lambda text: re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())
    inventory, gaps, full_pages = [], [], {}
    with pymupdf.open(pdf) as document:
        for page_no, page in enumerate(document, 1):
            originals = [e for e in result["elements"] if e["page"] == page_no]
            combined = compact("\n".join(e["text"] for e in originals))
            for block in page.get_text("blocks"):
                if len(block) > 6 and block[6] == 0 and len(compact(block[4])) >= 8 and compact(block[4]) not in combined:
                    result["elements"].append({"element_id": f"p{page_no}:pdf:b{block[5]}", "page": page_no,
                        "category": "paragraph", "text": block[4], "origin": "native_pdf_text", "coordinates": []})
            boxes = []
            for e in originals:
                if coordinates := e.get("coordinates"):
                    xs, ys = [p["x"] for p in coordinates], [p["y"] for p in coordinates]
                    boxes.append((min(xs) * page.rect.width, min(ys) * page.rect.height,
                                  max(xs) * page.rect.width, max(ys) * page.rect.height))
            for index, info in enumerate(page.get_image_info()):
                rect = pymupdf.Rect(info["bbox"])
                fraction = covered_fraction(tuple(rect), boxes)
                record = {"page": page_no, "image_index": index, "bbox": list(rect), "parse_area_coverage": fraction,
                          "state": "covered_region" if fraction >= 0.5 else "needs_image_read"}
                inventory.append(record)
                if fraction < 0.5 and rect.get_area() >= 100:
                    image = root / "image-gaps" / f"p{page_no:04}-i{index:03}.png"
                    image.parent.mkdir(parents=True, exist_ok=True)
                    if not image.exists():
                        page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=rect).save(str(image))
                    record.update(image_path=str(image), image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
                    gaps.append((record, image, page.rect.width, page.rect.height))
                    if page_no not in full_pages:
                        full = root / "image-gap-pages" / f"page-{page_no:04}.png"
                        full.parent.mkdir(parents=True, exist_ok=True)
                        if not full.is_file():
                            page.get_pixmap(matrix=pymupdf.Matrix(3, 3)).save(str(full))
                        full_pages[page_no] = full
                elif fraction < 0.5:
                    record["state"] = "small_image_retained_in_source_pdf"
    locks = {page: Lock() for page in full_pages}
    def read_gap(value):
        record, image, width, height = value
        print(f"Parse에 빠진 이미지 영역 판독: {record['page']}쪽 이미지{record['image_index']}", flush=True)
        response_dir = root / "image-gap-responses" / image.stem
        def known_empty():
            failed, manifest = response_dir / "parse-failed-response.json", response_dir / "parse-failed-manifest.json"
            if not failed.exists() or not manifest.exists():
                return False
            m = json.loads(manifest.read_text(encoding="utf-8"))
            return (m["source_sha256"] == record["image_sha256"] and m["request_settings"]["model"] == DEFAULT_MODEL
                    and m["response_sha256"] == hashlib.sha256(failed.read_bytes()).hexdigest()
                    and json.loads(failed.read_text(encoding="utf-8")).get("elements") == [])
        fallback = known_empty()
        for attempt in range(4):
            try:
                if fallback:
                    with locks[record["page"]]:
                        parsed = parse_document(full_pages[record["page"]], root / "image-gap-fullpage-responses" / full_pages[record["page"]].stem, mode="enhanced", ocr="force")
                else:
                    parsed = parse_document(image, response_dir, mode="enhanced", ocr="force")
                break
            except ValueError:
                if fallback or not known_empty():
                    raise
                fallback = True
            except RuntimeError as error:
                if "HTTP 429" not in str(error) or attempt == 3:
                    raise
                time.sleep(10 * 2 ** attempt)
        records = []
        for e in parsed["elements"]:
            if text := element_text(e):
                x0, y0, x1, y1 = record["bbox"]
                coordinates = e.get("coordinates", []) if fallback else [{"x": (x0 + point["x"] * (x1 - x0)) / width,
                                "y": (y0 + point["y"] * (y1 - y0)) / height} for point in e.get("coordinates", [])]
                records.append({"element_id": f"p{record['page']}:img{record['image_index']}:e{e['id']}",
                    "page": record["page"], "category": e["category"], "text": text, "origin": "pdf_image_gap_ocr",
                    "coordinates": coordinates, "image_sha256": record["image_sha256"]})
        matching = [e for e in records if e["coordinates"] and covered_fraction(record["bbox"],
                    [(min(p["x"] for p in e["coordinates"]) * width, min(p["y"] for p in e["coordinates"]) * height,
                      max(p["x"] for p in e["coordinates"]) * width, max(p["y"] for p in e["coordinates"]) * height)]) > 0]
        record.update(state="image_reprocessed" if matching else "unreadable_image", fullpage_fallback=fallback,
                      element_ids=[e["element_id"] for e in records])
        return records
    with ThreadPoolExecutor(max_workers=2) as pool:
        for records in pool.map(read_gap, gaps):
            result["elements"].extend(records)
    result["pdf_image_inventory"] = inventory


def load_complete_sources(pdf, base_dir):
    import pymupdf
    result = load_sources(pdf, base_dir)
    root = Path(result["run_dir"]).parent / "research-sources-v3"
    with pymupdf.open(pdf) as document:
        page_count = len(document)
        informative = {e["page"] for e in result["elements"] if e["category"] not in ("page_header", "page_footer")}
        pages = sorted(set(range(1, page_count + 1)) - informative |
                       {e["page"] for e in result["elements"] if suspicious_number_spacing(e["text"])})
        images = {}
        for page in pages:
            image = root / "images" / f"page-{page:04}.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            if not image.is_file():
                document[page - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(str(image))
            images[page] = image

    def repair(page):
        print(f"수치 OCR·누락 페이지 재확인: {page}쪽", flush=True)
        return page, parse_document(images[page], root / "responses" / f"page-{page:04}", mode="enhanced", ocr="force")

    with ThreadPoolExecutor(max_workers=3) as pool:
        for page, native in pool.map(repair, pages):
            for element in native["elements"]:
                if text := element_text(element):
                    result["elements"].append({"element_id": f"p{page}:review:e{element['id']}", "page": page,
                        "category": element["category"], "text": text, "origin": "enhanced_numeric_ocr_review",
                        "coordinates": element.get("coordinates", []),
                        "image_sha256": hashlib.sha256(images[page].read_bytes()).hexdigest()})
    result.update(version="research-sources-v3", page_count=page_count, numeric_ocr_review_pages=pages, run_dir=str(root))
    add_physical_gaps(pdf, result, root)
    # Preserve entire native responses too, including empty regions, HTML and original table markup.
    paths = [root.parent / "parse-response.json"]
    paths += sorted((root.parent / "research-sources-v2/repair-responses").glob("*/parse-response.json"))
    paths += sorted((root / "responses").glob("*/parse-response.json"))
    paths += sorted((root / "image-gap-responses").glob("*/parse-response.json"))
    paths += sorted((root / "image-gap-fullpage-responses").glob("*/parse-response.json"))
    result["native_documents"] = []
    for path in paths:
        native = json.loads(path.read_text(encoding="utf-8"))
        manifest = json.loads(path.with_name("parse-manifest.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest["response_sha256"]:
            raise ValueError("보존할 Parse 원본 응답의 해시가 다릅니다.")
        result["native_documents"].append({"path": str(path), "sha256": digest, "manifest": manifest, "response": native})
    write_json(root / "source-elements.json", result)
    return result
