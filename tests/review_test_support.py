"""Explicit model-confirmation fixture; this does not judge semantic correctness."""


def confirmed_findings(packet, schema):
    facts = {f["id"]: f for f in packet["facts"]}
    rows = {}
    for key, finding in packet["findings"].items():
        ids = schema["properties"]["findings"]["properties"][key]["properties"]["evidence_id"]["enum"]
        evidence_id = next((i for i in ids if i != "none"), "none")
        quote = ""
        if evidence_id != "none":
            fact = facts[evidence_id]
            for source in fact.get("sources", []):
                source = packet.get("source_elements", {}).get(source.get("source_ref"), source)
                if source.get("quote"):
                    quote = source["quote"]
                    break
            if not quote:
                quote = fact["statement"]
        rows[key] = {"decision": "body_error", "violation_type": "contradiction" if evidence_id != "none" else "unsupported_claim",
            "draft_quote": next(iter(finding["draft_paragraphs"].values()))["text"],
            "evidence_id": evidence_id, "source_quote": quote, "reason": finding["original_issue"]["reason"]}
    return {"findings": rows}
