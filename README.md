# Vena — hand vein detection studio

Vena is a local web app that demonstrates **dorsal hand-vein analysis**. Upload a photograph (PNG, JPG, BMP) or pick a sample. The UI streams every preprocess and feature-extraction stage as the research code runs, then overlays **endpoints** (green) and **bifurcations** (red) on the original hand.

This is a demonstration of the computer-vision pipeline in this repository, **not** a clinical or identity-verification system.

The same process write-up is interactive in the app: **About** (`#about`) is a clickable explorer, and **Studio** shows Why / How / Parameters / What to look for for the stage you are viewing.

## Slide deck

`Vena.pptx` is a 15-slide talk that walks the same sixteen stages. Its look follows the studio UI: warm cream paper, forest green, terracotta for veins, serif headings, rounded cards, and a 16-segment pipeline strip in the footer that tracks the current stage.

| Token | Hex | Used for |
| --- | --- | --- |
| Cream | `#EEECE4` | Slide background |
| Card | `#FBF8F1` | Cards, pills, image frames |
| Forest | `#235A44` | Eyebrows, logo, completed stages |
| Forest deep | `#17392B` | Dark slides |
| Terracotta | `#B5543C` | Vein mask, current stage, accents |
| Ink | `#1C1A17` | Body text |

Headings use Cambria (Georgia is a fine substitute) and body text uses Calibri, so the deck opens cleanly without extra font installs.

## Run the studio

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

| Place | What it is |
| --- | --- |
| Studio (`#studio`) | Upload or choose a sample; step through live frames |
| About (`#about` or `#about/clahe`) | Interactive guide for every stage |
| NIR invert toggle | Use when veins appear *brighter* than skin |

## How the system is wired

1. The browser `POST`s the image to `/api/analyze` (or `/api/analyze-sample`).
2. `pipeline.py` runs the same functions as `preprocess.py` and `features.py`, and **yields one NDJSON event per stage** (the image as a data URL, plus a short caption).
3. After thinning, it classifies landmarks and emits a `features` event (coordinates + counts) and a final overlay.
4. The UI draws each frame as it arrives, then lets you replay, compare, and read the guide for that step.

```
upload
  → hand interior ROI (exclude the silhouette band)
  → grayscale (or invert + gray)
  → median 15×15
  → CLAHE
  → median 15×15
  → adaptive Gaussian threshold (inside the ROI only)
  → morphological close + open (7×7)
  → drop blobs < 500 px
  → drop border-touching + contour-hugging components
  → tighter border pass (margin 1)
  → morphological close + open (5×5)
  → skeletonize
  → prune spurs ≤ 8 px
  → endpoints + bifurcations (merge radius 8)
  → overlay on the original
```

Polarity throughout: **dark pixels are veins** (binary value 0 / `< 128`). NIR invert exists so bright-on-dark captures can be flipped into that convention.

---

## Processes in detail

### 01 — Original capture

**Why.** Later overlays are only meaningful against the real photograph. Rings, straps, and blown highlights that look like vessels will show up here first.

**How.** The file is decoded as BGR. If the long side exceeds **1400 px**, it is downscaled with `cv2.INTER_AREA`. Nothing else is changed.

**Look for.** A dorsal hand filling the frame, with veins visible as darker (or NIR-bright) lines. Motion blur and clipped silhouettes become junk in the mask.

---

### 02 — Hand interior ROI

**Why.** Adaptive threshold loves the high-contrast edge where the fist meets the background. That contour often does **not** touch the image frame, so “remove border-touching components” leaves it — and skeletonization traces the **outline of the hand** instead of the veins. Veins live a margin inside the palm.

**How.** Otsu-segment the original grayscale, flip polarity so the image center is the hand, keep the largest filled blob, then take a distance transform. Pixels closer to the background than **max(16, 4.5% of the shorter side)** are treated as the silhouette band and forced to “not a vein” (intensity 255) before thresholding. After the binary mask is built, any leftover component whose *mean* distance to the background is still small is deleted.

**Look for.** In Studio, the gold rim is ignored on purpose; the green-tinted interior is the search region. The fist outline should not appear in the overlay.

---

### 03 — Grayscale / NIR invert

**Why.** Vessel signal is intensity, not hue. Color casts fool a local threshold. Some NIR setups render veins *brighter* than skin; the rest of the pipeline assumes *darker* veins, so those frames are inverted first.

**How.**

- Default: `cv2.cvtColor(..., COLOR_BGR2GRAY)` (`preprocess.to_grayscale`).
- NIR invert: `bitwise_not` on the color image, then grayscale (`inversionPreProcess.invert_and_grayscale`). Enable with the **NIR invert** toggle in Studio.

**Look for.** A monochrome hand whose vessels are dark grooves. If they still look like glowing ridges, invert and re-run.

---

### 04 — Median filter (15×15)

**Why.** Adaptive thresholding is local: a pore or speckle becomes a fake blob. A mean/Gaussian blur would also smear thin veins. A **median** replaces each pixel with the middle intensity in its window, so isolated spikes vanish and a consistent dark line survives.

**How.** `cv2.medianBlur` with **ksize = 15** (`apply_median_filter`). The window is large because typical captures make dorsal veins several pixels across.

**Look for.** Waxy skin, pores gone, vein trunks still traceable.

---

### 05 — CLAHE enhancement

**Why.** A fist is unevenly lit (bright knuckles, dark wrist). Global histogram stretch saturates highlights and still hides veins in shadow. **CLAHE** equalizes many small tiles and **clips** contrast so noise is not amplified without bound.

**How.** `cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))` applied to the median-filtered gray image (`apply_clahe`). Contrast above the clip limit is redistributed.

**Look for.** Faint branches popping. Extra texture is expected — that is why the next step exists.

---

### 06 — Second median pass (15×15)

**Why.** Equalization raises the contrast of leftover grain. Thresholding that grain turns it into salt-and-pepper that later pretends to be endpoints.

**How.** The same `apply_median_filter` (ksize 15) on the CLAHE output. Same algorithm, applied *after* enhancement on purpose.

**Look for.** The CLAHE image, quieter. Veins remain; the speckled field should look flatter.

---

### 07 — Adaptive threshold

**Why.** One global cutoff cannot serve a lit knuckle and a shaded wrist. Each pixel is compared to a **Gaussian-weighted local mean**.

**How.** `cv2.adaptiveThreshold` with `ADAPTIVE_THRESH_GAUSSIAN_C`, `THRESH_BINARY`, **blockSize = 29**, **C = 2**, maxval 255. `THRESH_BINARY` writes 255 when the pixel is *brighter* than local T, else 0. Dark veins therefore become **0 on white**. Downstream code treats `< 128` as vein.

**Look for.** Harsh black strokes on white: real veins plus outline, pores, and speckle. Cleanup follows.

---

### 08 — Morphological smooth

**Why.** Thresholding breaks a vein wherever contrast dips, and leaves isolated black dots. Morphology on the inverted mask (veins as white) can close gaps and open away salt noise.

**How.** Invert → **7×7 ellipse** `MORPH_CLOSE` (dilate then erode) → `MORPH_OPEN` (erode then dilate) → invert back (`smooth_binary`, kernel_size=7).

**Look for.** Slightly thicker, more continuous strokes. Isolated pepper dots gone.

---

### 09 — Blob filter

**Why.** Small dark islands remain (rings, moles, dust). They are not vascular and would spawn false endpoints after thinning.

**How.** Invert (veins white). `connectedComponentsWithStats` (8-connectivity). Drop any component with **area < 500**. Invert back (`remove_small_blobs`).

**Look for.** Tiny specks gone. Long traces and usually the hand silhouette remain.

---

### 10 — Vein mask (border + silhouette)

**Why.** The high-contrast edge where the hand meets the background is a thick dark loop. If it stays, skeletonization traces the **palm outline** instead of interior veins.

**How.** Invert, label, reject any component whose bounding box lies within **3 px** of the frame border (`remove_border_touching_components`, `border_margin=3`). Invert back.

**Look for.** Outer contour gone. Remaining black strokes on the interior of the palm.

---

### 11 — Outline isolation (feature pass)

**Why.** Feature extraction always runs its own border pass with a **tighter 1 px** margin (`features.py`), in case a thin rim survived the 3 px preprocess pass. The studio shows that extra pass as its own frame.

**How.** Same connected-component border test, `border_margin=1`.

**Look for.** Usually almost identical to the vein mask; any leftover rim should disappear.

---

### 12 — Skeleton prep

**Why.** Thinning is brittle: a two-pixel bump becomes a false spur. A slightly gentler smooth (**5×5** vs 7×7) rounds bumps without merging neighboring veins.

**How.** Close then open with a 5×5 ellipse (`features.smooth_binary`, matching `extract_feature_points(smooth_kernel=5)`).

**Look for.** Rounder edges. The mask is still thick — not a hairline yet.

---

### 13 — Skeletonization

**Why.** A thick mask has thousands of pixels; you cannot define “the” endpoint of a 12-pixel-wide blob. Thinning collapses each vessel to its **medial axis**. After this, a neighbor count of 1 vs 3+ is geometric.

**How.** Pixels `< 128` are foreground. `skimage.morphology.skeletonize` returns a boolean array (`get_skeleton`). The UI draws it as dark lines on paper (slightly dilated for display only).

**Look for.** Hairline traces along the veins, plus short noisy twigs — those are pruned next.

---

### 14 — Spur pruning

**Why.** Threshold noise creates short branches that are not anatomical. They inflate bifurcation counts.

**How.** From every endpoint (one neighbor), walk along the unique next skeleton pixel for at most **8** steps (`max_spur_length=8`). If the walk hits a junction (two or more other neighbors), **erase the path**. If it dies in empty space, leave it — it may be a real termination (`prune_spurs`).

**Look for.** The same centerlines with little barbs gone. Long vessels and real forks remain.

---

### 15 — Feature landmarks

**Why.** A vein signature is often a graph: where vessels **end** and where they **split**. Those points are more stable than a raw mask under small pose changes. Merging nearby detections stops one anatomical fork from appearing as a cluster of red dots.

**How.**

1. A 3×3 kernel counts the 8-neighbors of every skeleton pixel (center excluded).
2. **n == 1** → endpoint (green). **n ≥ 3** → bifurcation (red).
3. `merge_nearby_points` paints detections, dilates with an **8×8** kernel, connected-components the blobs, and replaces each blob by the centroid of the original points (`cluster_radius=8`).

**Look for.** Green tips, red Y-junctions, sitting on the skeleton. A red dot in empty skin means the mask was still noisy.

---

### 16 — Vein overlay

**Why.** A clean skeleton on a blank canvas can still be wrong (it may have traced a bracelet). Compositing onto the photograph is the sanity check.

**How.** Vein-mask pixels (`< 128`) are blended toward clay-red (**62% tint / 38% photo**). Endpoints are green filled circles, bifurcations red, both with a white rim. Radius scales with image size (~0.7% of the shorter side, at least 5 px). In Studio, **Compare with original** slider-wipes between the raw frame and this overlay.

**Look for.** Red traces following visible veins — not the palm outline or a watch strap. Markers on those traces.

---

## Project layout

```
app.py                 FastAPI server (upload, samples, static UI)
pipeline.py            Collects every stage as images + landmark lists
preprocess.py          Grayscale / CLAHE / threshold / cleanup
inversionPreProcess.py Invert-then-gray path for bright NIR veins
features.py            Skeleton, spur prune, endpoints, bifurcations
capture.py             CLI image loader (sample file or webcam)
live.py                Optional live stream from a Raspberry Pi
web/                   Studio + About UI
web/guide.js           Shared process text (About explorer + Studio tabs)
data/sample_veins/     Built-in captures in the sidebar
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/samples` | List files in `data/sample_veins/` |
| `POST` | `/api/analyze` | Multipart `file` + `invert` — NDJSON stream of stages |
| `POST` | `/api/analyze-sample` | Form `name` + `invert` — same stream for a built-in file |

Each stream emits `meta`, then `step` events (image as a data URL), then `features` (coordinates and counts), then `done`.