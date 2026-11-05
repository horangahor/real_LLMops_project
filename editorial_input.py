"""Measure editorial requests directly and keep repair feedback separate from prose."""

import copy
import re

from drafting_budget import compact_packet, request_bytes, request_limit


def fits_editorial_request(system, packet, schema):
    # Repair feedback no longer contains a second full candidate body.
    # Other writing/review packers retain their existing conservative margin.
    return request_bytes(system, compact_packet(packet), schema) <= request_limit()


def repair_request(packet, error, instruction):
    feedback = {key: copy.deepcopy(value) for key, value in error.items() if key != "response"}
    reason = error.get("reason", "")
    affected = []
    for rows in packet["source_parts"].values():
        for units in rows.values():
            for unit in units:
                if any(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(key) + r"(?![A-Za-z0-9_-])", reason)
                       for key in (unit["id"], unit["paragraph_id"])):
                    affected.append(unit["id"])
    if affected:
        feedback["affected_spans"] = affected
    return {**packet, "invalid_response": feedback, "repair_instruction": instruction}
