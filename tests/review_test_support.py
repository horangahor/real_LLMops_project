"""Synthetic editorial responses; these do not judge semantic correctness."""


def editorial_reply(packet):
    if packet.get("output_mode") == "fixed_spans":
        parts = packet["source_parts"]
        if "editable_spans" in packet:
            parts = {sid: {key: [u for u in parts[sid][key] if u["id"] in ids]
                           for key, ids in rows.items()} for sid, rows in packet["editable_spans"].items()}
        return {"sections": {sid: {"parts": {key: {
            u["id"]: {"action": "keep", "text": "", "join_previous": False} for u in units}
            for key, units in rows.items()}} for sid, rows in parts.items()}}
    if packet.get("output_mode") == "fixed_slots":
        sections = {}
        for sid, parts in packet["source_parts"].items():
            sections[sid] = {"parts": {}}
            for key, units in parts.items():
                slots = sections[sid]["parts"][key] = {}
                for unit in units:
                    slots.setdefault(unit["paragraph_id"], {"join_previous": False, "spans": {}})["spans"][unit["id"]] = {"action": "keep", "text": ""}
        return {"sections": sections}
    sections = {}
    for sid, parts in packet["source_parts"].items():
        sections[sid] = {"parts": {}}
        for key, units in parts.items():
            paragraphs = {}
            for unit in units:
                paragraphs.setdefault(unit["paragraph_id"], {"segments": []})["segments"].append({
                    "text": unit["text"], "source_id": unit["id"]})
            sections[sid]["parts"][key] = list(paragraphs.values())
    return {"sections": sections}
