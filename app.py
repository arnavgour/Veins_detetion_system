"""Local demo server for the hand-vein analysis UI."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from pipeline import iter_analysis

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "data" / "sample_veins"
WEB_DIR = ROOT / "web"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Vena", description="Hand vein analysis studio")


def _decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode that image.")
    return img


def _stream(frame: np.ndarray, invert: bool, filename: str) -> StreamingResponse:
    def generate():
        try:
            for event in iter_analysis(frame, invert=invert, filename=filename):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 — surface pipeline errors to the UI
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/samples")
def list_samples():
    if not SAMPLES_DIR.exists():
        return []
    samples = []
    for path in sorted(SAMPLES_DIR.iterdir()):
        if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file():
            samples.append(
                {
                    "id": path.name,
                    "name": path.stem.replace("_", " "),
                    "url": f"/samples/{path.name}",
                }
            )
    return samples


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    invert: bool = Form(False),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image is larger than 20 MB.")
    frame = _decode_image(data)
    return _stream(frame, invert=invert, filename=file.filename or "upload")


@app.post("/api/analyze-sample")
async def analyze_sample(
    name: str = Form(...),
    invert: bool = Form(False),
):
    path = (SAMPLES_DIR / Path(name).name).resolve()
    if not path.is_file() or path.parent != SAMPLES_DIR.resolve():
        raise HTTPException(status_code=404, detail="Sample not found.")
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported sample type.")
    data = path.read_bytes()
    frame = _decode_image(data)
    return _stream(frame, invert=invert, filename=path.name)


app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
