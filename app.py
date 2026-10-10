"""Local demo server for the hand-vein analysis UI."""

from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from pipeline import collect_features, iter_analysis
import store

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "data" / "sample_veins"
WEB_DIR = ROOT / "web"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_seed_lock = threading.Lock()
_seeding = False


def _decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode that image.")
    return img


def _persist_features(filename: str, source: str, invert: bool, features: dict) -> int | None:
    try:
        return store.save_analysis(
            filename=filename,
            source=source,
            invert=invert,
            features=features,
        )
    except Exception as exc:  # noqa: BLE001 — keep the stream alive if SQLite fails
        print(f"Could not store features for {filename}: {exc}")
        return None


def _stream(frame: np.ndarray, invert: bool, filename: str, source: str) -> StreamingResponse:
    def generate():
        try:
            saved = False
            for event in iter_analysis(frame, invert=invert, filename=filename):
                if event.get("type") == "features" and not saved:
                    analysis_id = _persist_features(filename, source, invert, event)
                    if analysis_id is not None:
                        event = {**event, "analysis_id": analysis_id}
                    saved = True
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 — surface pipeline errors to the UI
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


def _seed_sample_features() -> None:
    global _seeding
    with _seed_lock:
        if not SAMPLES_DIR.exists():
            return
        pending = [
            path
            for path in sorted(SAMPLES_DIR.iterdir())
            if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file() and not store.has_sample(path.name)
        ]
        if not pending:
            return
        _seeding = True
        try:
            for path in pending:
                if store.has_sample(path.name):
                    continue
                print(f"Seeding sample features: {path.name}")
                try:
                    frame = _decode_image(path.read_bytes())
                    features = collect_features(frame, invert=False, filename=path.name)
                    store.save_analysis(
                        filename=path.name,
                        source="sample",
                        invert=False,
                        features=features,
                    )
                except Exception as exc:  # noqa: BLE001 — keep seeding remaining samples
                    print(f"Skipped sample {path.name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — seeding must not crash the server
            print(f"Sample feature seed failed: {exc}")
        finally:
            _seeding = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init_db()
    threading.Thread(target=_seed_sample_features, name="seed-features", daemon=True).start()
    yield


app = FastAPI(title="Vena", description="Hand vein analysis studio", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True, "seeding": _seeding}


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


@app.get("/api/features")
def list_features():
    return {"analyses": store.list_analyses(), "seeding": _seeding}


@app.get("/api/features/{analysis_id}")
def get_features(analysis_id: int):
    payload = store.get_analysis(analysis_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return payload


@app.delete("/api/features/{analysis_id}")
def delete_features(analysis_id: int):
    if not store.delete_analysis(analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return {"ok": True}


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
    return _stream(frame, invert=invert, filename=file.filename or "upload", source="upload")


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
    return _stream(frame, invert=invert, filename=path.name, source="sample")


app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
