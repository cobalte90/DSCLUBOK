from __future__ import annotations

import json
from typing import Any

from .config import settings
from .utils import new_id, normalize_text


def export_payload(query: str, answer: dict[str, Any], export_format: str) -> dict[str, Any]:
    export_format = export_format.lower()
    warnings: list[str] = []
    if export_format == "json-ld":
        content = json.dumps({"@context": "https://schema.org", "@type": "ResearchProject", "name": "Science Knot export", "query": query, "result": answer}, ensure_ascii=False, indent=2)
        file_path = settings.export_dir / f"{new_id('export')}.jsonld"
        file_path.write_text(content, encoding="utf-8")
    elif export_format == "pdf":
        content = _markdown(query, answer)
        file_path = settings.export_dir / f"{new_id('export')}.pdf"
        pdf_bytes, warning = _basic_pdf(content)
        if warning:
            warnings.append(warning)
        file_path.write_bytes(pdf_bytes)
    else:
        content = _markdown(query, answer)
        file_path = settings.export_dir / f"{new_id('export')}.md"
        file_path.write_text(content, encoding="utf-8")
    return {"path": str(file_path), "content": content, "format": export_format, "warnings": warnings}


def _markdown(query: str, answer: dict[str, Any]) -> str:
    lines = [f"# Export for query: {query}", "", "## Summary", answer.get("summary", "")]
    if answer.get("sources"):
        lines += ["", "## Sources"]
        for source in answer["sources"]:
            lines.append(f"- {source.get('filename', source.get('document_id', 'unknown'))}")
    if answer.get("facts"):
        lines += ["", "## Facts"]
        for fact in answer["facts"]:
            lines.append(f"- {fact['subject']} {fact['predicate']} {fact['object_value']}")
    return "\n".join(lines)


def _basic_pdf(text: str) -> tuple[bytes, str | None]:
    lines = [normalize_text(line) for line in text.splitlines() if line.strip()]
    ascii_lines = [line.encode("ascii", "replace").decode("ascii")[:100] for line in lines[:35]]
    content_lines = ["BT", "/F1 11 Tf", "50 780 Td"]
    first = True
    for line in ascii_lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if first:
            content_lines.append(f"({escaped}) Tj")
            first = False
        else:
            content_lines.append(f"0 -14 Td ({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("ascii"))
    warning = "PDF export uses ASCII-safe fallback for non-Latin text in v1." if any("?" in line for line in ascii_lines) else None
    return bytes(pdf), warning
