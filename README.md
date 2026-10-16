# EdgeBoard AI

**ESP32-S3 + OV3660 Edge Capture + Local OCR + Optional Local LLM**

EdgeBoard AI is an end-to-end smart whiteboard and presentation capture system. The ESP32-S3 edge device performs real-time quality, stability, and change assessment to avoid transmitting redundant frames. A local Python backend receives valid JPEG frames, performs perspective rectification and enhancement, extracts text via Tesseract OCR, parses structured elements, and optionally formats study notes with a local Ollama model.

---

## Features

- **Smart Edge Filtering**: Frame stability analysis, quality checks (brightness, sharpness), and meaningful-change detection directly on the ESP32-S3 microcontroller.
- **Efficient Network Usage**: Transmits only stable, high-quality, changed frames over local Wi-Fi.
- **Automated Image Rectification**: 4-point perspective warp and OpenCV image enhancements (CLAHE, denoising, adaptive thresholding).
- **Local-First OCR**: Offline text extraction using Tesseract OCR with multi-variant confidence scoring.
- **Optional Local LLM Summarization**: Lecture-level study note generation via Ollama (e.g. `llama3.2:3b`) with zero cloud dependencies; OCR processing remains per capture.
- **Interactive Web Dashboard**: Real-time monitoring, live snapshots, capture history, and manual reprocessing controls.
- **Lecture-Level Digital Notes**: Start/end a lecture, group its captures automatically, combine OCR text in order, and generate one set of study notes with an optional local Ollama model.
- **RESTful Ingestion API**: Lightweight HTTP endpoints for device telemetry and image retrieval.

---

## Architecture

```text
Whiteboard / Presentation Surface
       │
       ▼
OV3660 Camera Sensor
       │
       ▼
ESP32-S3 Microcontroller
  ├─ Brightness & Sharpness Validation
  ├─ Board Visibility Heuristic
  ├─ Consecutive-Frame Stability Score
  └─ Change Detection vs Last Accepted Frame
       │ (HTTP POST with Telemetry Headers)
       ▼
Flask Backend Server (Local PC)
  ├─ SQLite Metadata Storage (`edgeboard.db`)
  ├─ Perspective Quad Warp & Crop
  ├─ CLAHE & Multi-Threshold Enhancement
  ├─ Tesseract OCR Pipeline
  └─ Optional Ollama Note Summarization
       │
       ▼
Web Dashboard (Browser Interface)
```

---

## Repository Structure

```text
EdgeAI/
├── backend/
│   ├── server.py             # Flask application & REST endpoints
│   ├── db.py                 # SQLite database layer
│   ├── config.py             # Application configuration & paths
│   ├── requirements.txt      # Python dependencies
│   ├── test_pipeline.py      # Local verification suite
│   ├── ai/
│   │   ├── __init__.py
│   │   └── pipeline.py       # Preprocessing, OCR & LLM pipeline
│   ├── templates/
│   │   └── index.html        # Web dashboard template
│   └── static/
│       └── style.css         # Dashboard styling
│
├── firmware/
│   └── esp32_camera/
│       └── esp32_camera.ino  # ESP32-S3 Arduino firmware
│
├── docs/
│   ├── architecture.md       # Comprehensive system architecture
│   ├── api.md                # REST API documentation
│   ├── setup.md              # Installation & setup guide
│   └── images/               # Documentation assets
│
├── scripts/
│   └── run_server.bat        # Server launcher script (Windows)
│
├── .gitignore                # Production gitignore
├── README.md                 # Project documentation
├── LICENSE                   # Project license
└── .env.example              # Environment variables template
```

---

## Installation & Setup

### 1. Backend Server Setup

Ensure Python 3.10+ and [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) are installed.

```powershell
# Navigate to backend directory
cd backend

# Create and activate virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install required dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` in the root or `backend` folder and adjust configurations as needed:

```ini
EDGEBOARD_HOST=0.0.0.0
EDGEBOARD_PORT=5000
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
ENABLE_OLLAMA=0
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

### 3. Firmware Configuration

1. Open `firmware/esp32_camera/esp32_camera.ino` in Arduino IDE.
2. Select board **ESP32S3 Dev Module** with **OPI PSRAM** enabled.
3. Update your Wi-Fi SSID, password, and the backend server IP address:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   const char* LAPTOP_SERVER = "http://YOUR_SERVER_IP:5000/upload";
   ```
4. Flash the sketch to your ESP32-S3 module.

---

## Running the Backend

Start the server using Python:

```powershell
cd backend
python server.py
```

Or launch using the script:

```powershell
.\scripts\run_server.bat
```

Open the dashboard in your web browser:
```text
http://127.0.0.1:5000
```

---

## Lecture-Level Digital Notes

The lecture workflow is intentionally simple:

1. In the dashboard, enter a lecture title and optionally a subject, then click **Start Lecture**.
2. As the ESP32 uploads captures, the backend continues its existing image preprocessing and Tesseract OCR pipeline. Each capture is automatically linked to the active lecture in SQLite.
3. Click **End Lecture** when teaching is finished. Wait for the capture processing to settle, then open the lecture and choose **Generate Digital Notes**.
4. The backend reads the lecture's non-empty OCR results in capture order and builds a single source context. Short lectures are sent to Ollama in one request; longer lectures are split into manageable sections and combined in a final synthesis request.
5. The generated summary and notes are saved to SQLite, so they remain available from the lecture history and can be regenerated later.

### Enable local LLM note generation

Ollama is optional. To generate rewritten, topic-wise notes locally:

1. Install and start Ollama on the same computer as the Flask backend.
2. Download a model, for example `ollama pull llama3.2:3b`.
3. Set `ENABLE_OLLAMA=1`, `OLLAMA_URL=http://127.0.0.1:11434`, and `OLLAMA_MODEL=llama3.2:3b` in the environment used to start Flask.
4. Restart the backend. The dashboard will indicate whether notes came from Ollama or the offline fallback.

If Ollama is disabled or cannot be reached, the application preserves the OCR text in readable notes rather than pretending that AI generation succeeded. Check equations and ambiguous handwriting against the source captures because OCR and LLM output can contain mistakes.

### Interview explanation

**Why store each capture separately?** It keeps the original OCR result traceable to its image and lets us retry OCR without losing other captures.

**Why aggregate at lecture end?** A single whiteboard image usually contains only part of the explanation. Combining the text in capture order gives the model context across the lecture and avoids treating every image as a separate topic.

**Why use SQLite and Ollama?** SQLite is sufficient for a local single-user prototype and is easy to inspect. Ollama allows note generation on the same computer without sending lecture content to a cloud API.

**What are the limitations?** Notes depend on OCR quality, the model's context capacity, and available local compute. The pipeline flags ambiguous OCR in the prompt, uses chunking for long lectures, and keeps an offline fallback when the model is unavailable.

## ESP32 Upload Flow

1. The ESP32 camera samples the whiteboard periodically (default every 1.0s).
2. It evaluates frame quality (brightness and sharpness) and checks for physical obstructions.
3. Once the board remains stable for the required duration (`1500ms`), it computes the change score against the last accepted state.
4. If a meaningful delta is detected, a full-resolution JPEG is uploaded to `POST /upload` with telemetry metadata headers (`X-Change-Score`, `X-Board-Visibility`, `X-Sharpness`, `X-Stability-Score`).
5. The backend accepts the payload, records metadata in SQLite, and invokes the OCR processing worker.

---

## OCR Pipeline Overview

1. **ROI Cropping**: Extracts the whiteboard area based on configured bounding coordinates.
2. **Perspective Transform**: Automatically locates board corners and performs a 4-point perspective warp.
3. **Enhancement**: Applies noise reduction, CLAHE contrast equalization, sharpening, and multiple binarization variants (Otsu, Adaptive Gaussian).
4. **Tesseract OCR**: Extracts text from each variant and selects the result with the highest confidence.
5. **Structuring**: Identifies formulas, equations, list items, and key headings.
6. **LLM Synthesis (Optional)**: If Ollama is active, prompts a local model to structure clean lecture/study notes.

---

## Documentation

- [System Architecture](docs/architecture.md)
- [REST API Reference](docs/api.md)
- [Step-by-Step Setup Guide](docs/setup.md)
- [Lecture Notes Interview Guide](docs/lecture-notes-interview-guide.md)

---

## Contributors

<!-- Organization contributors section -->
Contributions are welcome! Please feel free to submit issues and pull requests.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
