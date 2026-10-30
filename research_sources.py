"""Source index preserving native Parse responses, with automatic re-read of empty regions."""

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from document_parse import artifact_directory, parse_document, write_json
from paper_outline import element_key, element_text

VERSION = "research-sources-v2"


def blank_pages(parsed):
    return sorted({e["page"] for e in parsed["elements"]
                   if not element_text(e) and e.get("category") not in ("page_footer", "page_header")
                   and e.get("coordinates")})


def load_sources(pdf, base_dir, progress=None):
    pdf, base_dir = Path(pdf), Path(base_dir)
    root = artifact_directory(pdf, base_dir / "draft_history/parse-api-v1")
    parsed = parse_document(pdf, root)
    folder = root / VERSION
    records = {element_key(e): {"element_id": element_key(e), "page": e["page"],
               "text": element_text(e), "category": e["category"], "coordinates": e.get("coordinates", []),
               "origin": "standard_parse"} for e in parsed["elements"] if element_text(e)}
    pages = blank_pages(parsed)
    images = {}
    if pages:
        import pymupdf
        image_dir = folder / "repair-images"
        image_dir.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(pdf) as document:
            for page in pages:
                image = image_dir / f"page-{page:04}.png"
                if not image.exists():
                    document[page - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(str(image))
                images[page] = image
        def repair(page):
            if progress:
                progress(f"빈 원문 영역 재분석: {page}쪽")
            document = parse_document(images[page], folder / "repair-responses" / f"page-{page:04}",
                                      mode="enhanced", ocr="force")
            return page, document
        with ThreadPoolExecutor(max_workers=3) as pool:
            for page, document in pool.map(repair, pages):
                for element in document["elements"]:
                    text = element_text(element)
                    if text:
                        key = f"p{page}:enh:e{element['id']}"
                        records[key] = {"element_id": key, "page": page, "text": text,
                            "category": element["category"], "coordinates": element.get("coordinates", []),
                            "origin": "enhanced_page_image", "image_sha256": hashlib.sha256(images[page].read_bytes()).hexdigest()}
    result = {"version": VERSION, "source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
              "elements": list(records.values()), "repaired_pages": pages,
              "empty_standard_elements": sum(not element_text(e) for e in parsed["elements"]), "run_dir": str(folder)}
    write_json(folder / "source-elements.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    result = load_sources(args.pdf, Path(__file__).resolve().parent, lambda message: print(message, flush=True))
    print({"elements": len(result["elements"]), "repaired_pages": result["repaired_pages"]})
