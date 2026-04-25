from __future__ import annotations

from pathlib import Path


def classify_system(text: str, image_path: str = "") -> str:
    blob = f"{text}\n{Path(image_path).name}".lower()

    sap_terms = [
        "sap",
        "transaction",
        "company code",
        "posting",
        "vendor",
        "purchase order",
        "document number",
        "fiori",
        "me23n",
        "fb60",
        "miro",
        "va01",
        "t-code",
        "business partner",
    ]
    excel_terms = [
        "excel",
        "workbook",
        "worksheet",
        "pivot",
        "cell",
        "column",
        ".xlsx",
        "spreadsheet",
        "formula",
        "sheet1",
        "power query",
    ]
    email_terms = ["outlook", "gmail", "inbox", "subject", "reply", "forward", "cc:", "bcc:", "sent items", "new email"]
    collaboration_terms = ["slack", "channel", "threads", "huddle", "workspace", "teams", "chat", "meeting"]
    browser_terms = ["chrome", "edge", "firefox", "http", "www.", ".com", "browser", "address bar", "url", "web app"]
    pdf_terms = ["pdf", "adobe", "page 1 of", "acrobat"]
    file_terms = ["file explorer", "downloads", "documents", "this pc", "onedrive", "folder", "filename"]

    scores = {
        "SAP": sum(term in blob for term in sap_terms),
        "Excel": sum(term in blob for term in excel_terms),
        "Email": sum(term in blob for term in email_terms),
        "Slack/Teams": sum(term in blob for term in collaboration_terms),
        "Browser": sum(term in blob for term in browser_terms),
        "PDF": sum(term in blob for term in pdf_terms),
        "File Explorer": sum(term in blob for term in file_terms),
    }
    best_system, best_score = max(scores.items(), key=lambda item: item[1])
    return best_system if best_score > 0 else "Other"


def classify_events(events: list[dict]) -> list[dict]:
    return [
        {**event, "system": classify_system(event.get("clean_text") or event.get("raw_text", ""), event.get("path", ""))}
        for event in events
    ]
