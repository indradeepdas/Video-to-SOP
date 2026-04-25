from __future__ import annotations

import re


NOISE_PATTERNS = [
    r"^\s*(file|edit|view|insert|format|tools|help|home|share|search)\s*$",
    r"^\s*\d{1,2}:\d{2}(\s?[AP]M)?\s*$",
    r"^\s*(zoom|page|tab|window|minimize|maximize|close)\s*$",
    r"^\s*(back|forward|refresh|bookmarks?)\s*$",
    r"^\s*[|_\-=]{2,}\s*$",
]

KEEP_KEYWORDS = {
    "sap",
    "invoice",
    "supplier",
    "vendor",
    "payment",
    "terms",
    "purchase",
    "order",
    "excel",
    "amount",
    "date",
    "posting",
    "company",
    "customer",
    "export",
    "filter",
    "status",
    "document",
    "workflow",
    "approval",
    "approved",
    "rejected",
    "pending",
    "gross",
    "net",
    "tax",
    "currency",
    "balance",
    "reconciliation",
    "download",
    "upload",
    "account",
    "general ledger",
    "cost center",
    "profit center",
    "material",
    "quantity",
    "delivery",
    "browser",
    "pdf",
    "teams",
    "outlook",
}


def clean_text(text: str, max_lines: int = 28) -> str:
    if not text:
        return ""

    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if len(line) < 3:
            continue
        lower = line.lower()
        if any(re.match(pattern, lower) for pattern in NOISE_PATTERNS):
            continue
        if lower in seen:
            continue
        seen.add(lower)

        has_business_term = any(keyword in lower for keyword in KEEP_KEYWORDS)
        if has_business_term or len(line) >= 7:
            lines.append(line)
        if len(lines) >= max_lines:
            break

    return "\n".join(lines)


def clean_ocr_results(events: list[dict]) -> list[dict]:
    cleaned = []
    for event in events:
        cleaned_text = clean_text(event.get("raw_text", ""))
        cleaned.append({**event, "clean_text": cleaned_text})
    return cleaned
