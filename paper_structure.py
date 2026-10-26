import os
import json
import requests
from pathlib import Path
from config import STRUCTURE_AGENT_ID, STRUCTURE_CONFIG_ID, UPSTAGE_API_KEY, SOLAR_MODEL

PARSE_URL = "https://api.upstage.ai/v1/document-ai/document-parse"
CHAT_URL = "https://api.upstage.ai/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {UPSTAGE_API_KEY}"
}

STRUCTURE_PROMPT = """
You are analyzing academic papers to create a reusable reference profile for downstream generative writing.

Read the parsed paper and produce a concise but structured analysis of the paper's document organization and writing style.

Focus on:
- overall document type and likely venue/style
- title style and length
- abstract structure and tone
- section hierarchy and ordering
- how introduction, related work, method, experiments, results, discussion, and conclusion are organized
- paragraph style and level of formality
- how figures and tables are used and referenced
- citation and reference-list style
- any recurring rhetorical patterns useful for using this paper as a writing reference

Output in Korean with clear section headings. Do not extract every factual detail from the paper. Focus on structure and style patterns that another LLM could imitate or use as reference.
"""

CHECKLIST_PROMPT = """
Based on the parsed paper and the previous analysis, produce a reusable checklist in Korean for referencing this paper's structure and writing style when prompting another generative LLM.

Return a practical checklist with short bullet points under these headings:
- 문서 개요
- 섹션 구성 규칙
- 초록 작성 방식
- 방법/실험/결과 서술 방식
- 표/그림 사용 규칙
- 인용/참고문헌 규칙
- 그대로 따라하면 안 되는 점

Make the checklist generic enough to reuse for similar papers, but grounded in the current paper's observed style. Do not output JSON.
"""

def parse_pdf(pdf_path: str) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {pdf_path}")

    print(f"[*] Upstage Document Parse 요청 중: {path.name}...")
    with open(path, "rb") as f:
        files = {"document": f}
        data = {
            "model": "document-parse",
            "ocr": "auto",
            "output_formats": '["text"]'
        }
        response = requests.post(PARSE_URL, headers=HEADERS, files=files, data=data, timeout=120)
        response.raise_for_status()
        result = response.json()

    # Document Parse 응답에서 텍스트 추출 (dict인 경우 text 또는 markdown 추출)
    if "content" in result:
        content_val = result["content"]
        if isinstance(content_val, dict):
            return content_val.get("text") or content_val.get("markdown") or ""
        return str(content_val)

    if "text" in result:
        return result["text"]

    return json.dumps(result, ensure_ascii=False)

def run_chat(prompt: str, content: str) -> str:
    payload = {
        "model": SOLAR_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content}
        ],
        "temperature": 0.2
    }
    response = requests.post(CHAT_URL, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=120)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]

def analyze_paper(pdf_path: str) -> dict:
    parsed_text = parse_pdf(pdf_path)
    print(f"[*] 문서 파싱 완료 ({len(parsed_text):,}자). 구조 프로파일 분석 중...")
    structure_profile = run_chat(STRUCTURE_PROMPT, parsed_text)
    
    print(f"[*] 스타일 체크리스트 생성 중...")
    checklist = run_chat(
        CHECKLIST_PROMPT,
        f"[논문 원문]\n{parsed_text}\n\n[이전 분석 결과]\n{structure_profile}"
    )
    return {
        "file": pdf_path,
        "paper_structure_profile": structure_profile,
        "paper_style_checklist": checklist
    }

if __name__ == "__main__":
    pdf_files = [
        r"C:\Users\user\Desktop\LLMops\research_revies.pdf",
        r"C:\Users\user\Desktop\LLMops\AIComps2026_NPU_Benchmarking_1.1v.pdf"
    ]

    all_results = []
    for pdf in pdf_files:
        if Path(pdf).exists():
            print(f"\n==================================================")
            print(f"[*] 분석 시작: {pdf}")
            print(f"==================================================")
            result = analyze_paper(pdf)
            all_results.append(result)
        else:
            print(f"[!] 파일을 찾을 수 없어 건너뜁니다: {pdf}")

    output_path = Path(__file__).resolve().parent / "paper_structure_analysis.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n[+] 분석 완료! 결과 저장: {output_path}")
