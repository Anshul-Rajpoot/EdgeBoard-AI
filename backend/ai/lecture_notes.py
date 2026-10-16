"""Lecture-level note generation using ordered OCR text and optional local Ollama."""
from __future__ import annotations

import re

import requests

from config import ENABLE_OLLAMA, OLLAMA_MODEL, OLLAMA_URL

MAX_CHUNK_CHARS = 9000


def _split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split long notes near line boundaries so the model context stays manageable."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    chunks = []
    current = []
    current_size = 0
    for line in lines:
        # Very long OCR lines are split rather than discarded.
        while len(line) > max_chars:
            piece, line = line[:max_chars], line[max_chars:]
            if current:
                chunks.append("\n".join(current))
                current, current_size = [], 0
            chunks.append(piece)
        extra = len(line) + (1 if current else 0)
        if current and current_size + extra > max_chars:
            chunks.append("\n".join(current))
            current, current_size = [], 0
        current.append(line)
        current_size += len(line) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _ollama_generate(prompt: str, timeout: int = 180) -> str:
    response = requests.post(
        f"{OLLAMA_URL.rstrip('/')}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    return (response.json().get("response") or "").strip()


def _fallback_notes(title: str, subject: str, chunks: list[str]) -> tuple[str, str]:
    """Readable offline output when Ollama is disabled or unavailable."""
    source = "\n\n".join(chunks).strip()
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    equations = [line for line in lines if re.search(r"[=<>]|\b(sin|cos|tan|log|ln)\b|\^|[∫√π]", line, re.I)]
    summary = f"Notes prepared from {len(chunks)} captured text section(s). Review the extracted content below; AI rewriting was not used."
    parts = [f"# {title or 'Lecture Notes'}"]
    if subject:
        parts.append(f"**Subject:** {subject}")
    parts += ["", "## Extracted lecture content", source or "No readable text was extracted."]
    if equations:
        parts += ["", "## Equations detected", *[f"- {line}" for line in equations]]
    parts += ["", "## Review reminder", "OCR can misread handwriting and symbols. Check equations and unclear words against the original captures."]
    return summary, "\n".join(parts)


def generate_lecture_notes(title: str, subject: str, capture_sections: list[dict]) -> dict:
    """Generate one coherent set of notes from ordered capture OCR records.

    Each capture section is expected to contain ``frame_id``, ``filename`` and ``text``.
    When the lecture is long, each chunk is condensed first and then combined in a final pass.
    """
    usable = [item for item in capture_sections if (item.get("text") or "").strip()]
    if not usable:
        raise ValueError("There is no readable OCR text for this lecture yet. Wait for captures to finish processing.")

    ordered_text = []
    for index, item in enumerate(usable, start=1):
        ordered_text.append(
            f"[Capture {index} | Frame {item.get('frame_id', '?')} | {item.get('filename', 'capture')}]\n"
            f"{(item.get('text') or '').strip()}"
        )
    combined = "\n\n".join(ordered_text)
    chunks = _split_into_chunks(combined)

    if not ENABLE_OLLAMA:
        summary, notes = _fallback_notes(title, subject, chunks)
        return {"summary": summary, "notes": notes, "source_count": len(usable), "mode": "offline_fallback"}

    try:
        if len(chunks) == 1:
            context = chunks[0]
        else:
            # Condense each part first, then synthesize the parts into one set of notes.
            condensed = []
            for index, chunk in enumerate(chunks, start=1):
                prompt = (
                    "You are helping prepare accurate student lecture notes. Summarize only the information "
                    "in this section. Keep definitions, technical terms, examples, and equations exactly where possible. "
                    "Do not add facts that are not in the source. Mark unclear OCR as [unclear].\n\n"
                    f"Lecture: {title}\nSubject: {subject or 'Not specified'}\nSection {index} of {len(chunks)}:\n{chunk}"
                )
                condensed.append(f"Section {index}:\n" + _ollama_generate(prompt))
            context = "\n\n".join(condensed)

        prompt = (
            "You create clear, student-friendly digital notes from whiteboard lecture OCR. "
            "Use simple language that a student can explain in an interview or exam. "
            "Combine repeated ideas and connect concepts only when the source supports the connection. "
            "Do not invent missing definitions, facts, examples, or equations. Preserve equations and symbols "
            "as faithfully as possible. If OCR is ambiguous, write [check original capture]. "
            "Use Markdown headings and bullets. Return exactly these main sections: "
            "Lecture Summary, Topic-wise Notes, Important Equations / Terms, Quick Revision. "
            "Quick Revision should contain a short set of points based only on the supplied source.\n\n"
            f"Lecture title: {title}\nSubject: {subject or 'Not specified'}\n"
            f"Number of source captures: {len(usable)}\n\nSOURCE CONTEXT (capture order preserved):\n{context}"
        )
        notes = _ollama_generate(prompt)
        if not notes:
            raise RuntimeError("The local model returned an empty response.")
        summary_match = re.search(
            r"(?:^|\n)#+\s*Lecture Summary\s*\n(.*?)(?=\n#+\s|$)",
            notes,
            re.IGNORECASE | re.DOTALL,
        )
        summary = summary_match.group(1).strip() if summary_match else notes[:1200].strip()
        if len(summary) > 1200:
            summary = summary[:1197].rsplit(" ", 1)[0] + "…"
        return {"summary": summary, "notes": notes, "source_count": len(usable), "mode": "ollama"}
    except Exception as exc:
        summary, notes = _fallback_notes(title, subject, chunks)
        return {
            "summary": summary,
            "notes": notes,
            "source_count": len(usable),
            "mode": "offline_fallback",
            "warning": f"Ollama note generation was unavailable: {exc}",
        }
