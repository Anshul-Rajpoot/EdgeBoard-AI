# EdgeBoard AI: Lecture Notes Feature — Interview Guide

This guide explains the feature in plain language so you can describe the code without memorizing buzzwords.

## 30-second explanation

"The camera sends only useful whiteboard captures to my Flask backend. The backend preprocesses each image and extracts text with Tesseract. I added a lecture layer so all captures from one class are linked to the same lecture in SQLite. At the end of the class, the backend combines the extracted text in capture order and sends it to a local Ollama model to create topic-wise digital notes. I also added chunking for long lectures and a fallback that preserves the OCR text if the model is unavailable."

## What happens in the code?

1. **`backend/server.py` — API and workflow**
   - `POST /api/lectures` starts a lecture.
   - The existing `POST /upload` still accepts images from the ESP32 and starts background image processing.
   - `POST /api/lectures/<id>/end` marks the lecture as complete.
   - `POST /api/lectures/<id>/generate-notes` checks that processing has finished and requests notes for that lecture.

2. **`backend/db.py` — storage**
   - `lectures` stores the title, subject, start/end time, generated summary, notes and generation status.
   - `frames` still stores each image's OCR result and metadata. A new `lecture_id` links a capture to its lecture.
   - Keeping OCR text per frame means we can trace a sentence back to its source capture and rerun OCR if necessary.

3. **`backend/ai/lecture_notes.py` — context and LLM**
   - Reads non-empty OCR text in frame order.
   - Adds capture labels so the context stays traceable.
   - Sends a short lecture in one request. If it is too long, splits it into manageable sections, summarizes each section, then asks the model to combine those summaries.
   - The prompt asks the model to preserve equations and not invent missing facts. This reduces risk but cannot guarantee perfect output.
   - If Ollama is disabled or fails, the fallback returns readable source text and detected equations. It does not pretend that an LLM generated those notes.

4. **`backend/templates/index.html` and `backend/static/style.css` — dashboard**
   - Start/end lecture controls, lecture history, and a panel for generated notes.
   - The existing capture gallery and frame diagnostics remain available.

## Common interviewer questions

### Why not generate notes for every image separately?

A single capture may contain only one step in a larger explanation. Generating separately can repeat headings and miss connections. Combining OCR text at the end gives the model context across the class.

### Why keep both `lectures` and `frames` tables?

They represent different things. One lecture can contain many captures. The `frames` table keeps capture-level information; the `lectures` table keeps information that belongs to the whole class, such as the final notes.

### Why SQLite?

The project is a local prototype, so SQLite is easy to set up and does not need a separate database server. It is enough for lecture metadata, OCR text, and generated notes.

### Why Ollama?

It allows the model to run locally, so lecture text does not need to be sent to a hosted LLM API. The trade-off is that speed and quality depend on the computer and the selected model.

### Why split long lectures into chunks?

LLMs have a context limit. Sending a very long lecture in one request can exceed that limit or reduce quality. Chunking keeps each request manageable; a final synthesis step combines the section summaries.

### Does chunking mean the model cannot miss anything?

No. Summarizing sections can lose detail, and OCR can misread handwriting or mathematical symbols. We preserve the per-frame OCR text in SQLite and tell the model to flag uncertain text, but the notes should still be checked against the original captures.

### What if Ollama is not running?

The endpoint falls back to readable OCR-based notes and preserves the equations it can detect. The UI identifies the fallback mode. The user can start Ollama and regenerate the notes later.

### How would you improve it next?

I would add a review step for uncertain OCR, allow a user to edit the notes, export notes to PDF/Markdown, and test note quality on real lectures. Search across many lectures could be added later if the project needs it.

## Demo flow

1. Start the Flask backend and open `http://127.0.0.1:5000`.
2. Enter a lecture title and subject; click **Start Lecture**.
3. Let the ESP32 upload captures and wait for OCR status to settle.
4. Click **End Lecture**.
5. Open that lecture and click **Generate Digital Notes**.
6. Show the saved notes and explain that the original OCR text remains attached to each capture.

## Before the demo

- Confirm Tesseract is installed and detected by `/health`.
- For LLM rewriting, start Ollama and pull the configured model. Set `ENABLE_OLLAMA=1` in the environment before launching Flask.
- Use a short test lecture first and inspect the OCR text for equation errors.
- If no LLM is available, the feature still demonstrates lecture grouping, ordered aggregation, persistent notes, and its offline fallback.
