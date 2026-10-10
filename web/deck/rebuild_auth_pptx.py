"""Rebuild Veins_Authentication.pptx as a step-by-step method deck."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

OUT = Path("/Users/arnav/Documents/Veins_Authentication.pptx")
REPO = Path(__file__).resolve().parents[2]
OURS = REPO / "web" / "deck" / "media"
THEIRS = Path("/tmp/vena_auth_media")

W, H = 13.333, 7.5
INK = RGBColor(0x1C, 0x1A, 0x17)
FOREST = RGBColor(0x23, 0x5A, 0x44)
CLAY = RGBColor(0xB5, 0x54, 0x3C)
MUTED = RGBColor(0x6B, 0x66, 0x5B)
CREAM = RGBColor(0xEE, 0xEC, 0xE4)
CARD = RGBColor(0xFB, 0xF8, 0xF1)
DARK = RGBColor(0x17, 0x39, 0x2B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SERIF = "Cambria"
SANS = "Calibri"


def emu(x):
    return Inches(x)


def set_run_font(run, name, size, color, bold=False, italic=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rPr, qn(tag))
        el.set("typeface", name)


def set_fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def rect(slide, x, y, w, h, color):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, emu(x), emu(y), emu(w), emu(h))
    set_fill(sh, color)
    return sh


def round_rect(slide, x, y, w, h, color, radius=0.08):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, emu(x), emu(y), emu(w), emu(h))
    try:
        sh.adjustments[0] = radius
    except Exception:
        pass
    set_fill(sh, color)
    return sh


def textbox(slide, x, y, w, h, text, *, size=16, font=SANS, color=INK,
            bold=False, italic=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, leading=1.1):
    box = slide.shapes.add_textbox(emu(x), emu(y), emu(w), emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = Inches(0.02)
    tf.margin_right = Inches(0.02)
    tf.margin_top = Inches(0)
    tf.margin_bottom = Inches(0)
    tf.anchor = anchor
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = leading
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        run = p.add_run()
        run.text = line
        set_run_font(run, font, size, color, bold, italic)
    return box


def blank(prs, color=CREAM):
    layouts = prs.slide_layouts
    layout = layouts[6] if len(layouts) > 6 else layouts[-1]
    slide = prs.slides.add_slide(layout)
    for sh in list(slide.placeholders):
        try:
            sh._element.getparent().remove(sh._element)
        except Exception:
            pass
    rect(slide, 0, 0, W, H, color)
    return slide


def crop_caption(im: Image.Image) -> Image.Image:
    im = im.convert("RGB")
    w, h = im.size
    return im.crop((0, 0, w, int(h * 0.90)))


def crop_to_content(im: Image.Image, pad: float = 0.05) -> Image.Image:
    import numpy as np

    im = im.convert("RGB")
    arr = np.asarray(im)
    gray = arr.mean(axis=2)
    if gray.mean() < 80:
        mask = gray > 28
    else:
        mask = (gray < 236) | (np.abs(arr[:, :, 0].astype(int) - arr[:, :, 1].astype(int)) > 12)
    ys, xs = np.where(mask)
    if len(xs) < 80:
        return im
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    pw = int((x1 - x0) * pad)
    ph = int((y1 - y0) * pad)
    x0, y0 = max(0, x0 - pw), max(0, y0 - ph)
    x1, y1 = min(im.size[0], x1 + pw), min(im.size[1], y1 + ph)
    return im.crop((x0, y0, x1, y1))


def picture_cover(slide, path, x, y, w, h, strip=False, trim=False):
    dpi = 180
    tw, th = max(2, int(w * dpi)), max(2, int(h * dpi))
    im = Image.open(path)
    if strip:
        im = crop_caption(im)
    else:
        im = im.convert("RGB")
    if trim:
        im = crop_to_content(im)
    iw, ih = im.size
    scale = max(tw / iw, th / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    im = im.crop((left, top, left + tw, top + th))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    slide.shapes.add_picture(buf, emu(x), emu(y), emu(w), emu(h))


def picture_fit(slide, path, x, y, w, h, strip=False):
    im = Image.open(path)
    if strip:
        im = crop_caption(im)
    else:
        im = im.convert("RGB")
    iw, ih = im.size
    ratio = iw / ih
    box = w / h
    if ratio > box:
        pw, ph = w, w / ratio
    else:
        ph, pw = h, h * ratio
    px = x + (w - pw) / 2
    py = y + (h - ph) / 2
    buf = BytesIO()
    im.save(buf, format="PNG")
    buf.seek(0)
    slide.shapes.add_picture(buf, emu(px), emu(py), emu(pw), emu(ph))


def pill(slide, x, y, w, h, label, fill=CARD, fg=FOREST):
    round_rect(slide, x, y, w, h, fill, radius=0.35)
    textbox(slide, x, y, w, h, label, size=11, color=fg, bold=True,
            align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def param_row(slide, x, y, items):
    width = 5.1 / max(1, len(items))
    for i, (k, v) in enumerate(items):
        xx = x + i * width
        textbox(slide, xx, y, width - 0.1, 0.22, k, size=11, color=FOREST, bold=True)
        textbox(slide, xx, y + 0.22, width - 0.1, 0.28, v, size=13, color=INK)


def step_slide(prs, num, title, how, params, image, *, strip=False, contain=False, dark=False):
    """One process. No section heading, no report footer, no progress bar."""
    slide = blank(prs, DARK if dark else CREAM)
    ink = WHITE if dark else INK
    muted = RGBColor(0xC8, 0xD4, 0xCC) if dark else MUTED
    forest = RGBColor(0x8F, 0xC4, 0xA8) if dark else FOREST

    textbox(slide, 0.55, 0.55, 5.2, 0.35, num, size=14, font=SANS, color=CLAY, bold=True)
    textbox(slide, 0.55, 0.95, 5.3, 1.15, title, size=28, font=SERIF, color=ink, leading=0.98)
    textbox(slide, 0.55, 2.25, 5.2, 2.4, how, size=16, font=SANS, color=muted, leading=1.22)
    if params:
        param_row(slide, 0.55, 5.0, params)

    frame_x, frame_y, frame_w, frame_h = 6.15, 0.4, 6.75, 6.7
    if dark:
        round_rect(slide, frame_x, frame_y, frame_w, frame_h, RGBColor(0x12, 0x28, 0x1F), radius=0.06)
    else:
        round_rect(slide, frame_x, frame_y, frame_w, frame_h, CARD, radius=0.06)
    picture_cover(
        slide, image,
        frame_x + 0.15, frame_y + 0.15, frame_w - 0.3, frame_h - 0.3,
        strip=strip, trim=contain,
    )
    return slide


def build():
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    # use a blank-ish layout
    if not prs.slide_layouts:
        raise RuntimeError("no layouts")

    nir = THEIRS / "image-8-1.png"
    enhanced = THEIRS / "image-8-2.png"
    thresh = THEIRS / "image-8-3.png"
    mask = THEIRS / "image-8-4.png"
    skeleton = THEIRS / "image-8-5.png"
    landmarks = THEIRS / "image-8-6.png"
    overlay = THEIRS / "image-1-1.png"
    roi = OURS / "hand.jpg"
    original = OURS / "original.jpg"

    # 1 Title — keep team, drop report footer
    s = blank(prs, CREAM)
    picture_cover(s, overlay, 7.15, 0, 6.183, H)
    rect(s, 0, 0, 7.35, H, CREAM)
    textbox(s, 0.6, 0.7, 6.4, 0.3, "ACADEMIC PROJECT  ·  2026", size=12, color=FOREST, bold=True)
    textbox(s, 0.58, 1.15, 6.5, 1.7, "UPI Payment\nAuthentication+", size=40, font=SERIF, color=INK, leading=0.95)
    textbox(s, 0.6, 3.05, 6.3, 0.45, "Vein pattern recognition and liveness detection", size=18, font=SERIF, color=FOREST)
    textbox(s, 0.6, 3.55, 6.2, 0.55, "How each processing step turns an NIR hand image into a matchable vein graph.", size=15, color=MUTED, leading=1.2)
    pill(s, 0.6, 4.3, 1.45, 0.36, "Vein match")
    pill(s, 2.15, 4.3, 1.65, 0.36, "Liveness check")
    pill(s, 3.90, 4.3, 1.55, 0.36, "Vein detection")
    textbox(s, 0.6, 5.0, 6.2, 0.25, "PROJECT TEAM", size=11, color=CLAY, bold=True)
    for i, (name, sid) in enumerate((
        ("Arnav Gour", "1705285"),
        ("Mudrika Bajaj", "1153857"),
        ("Aainaa Shrivastav", "1689885"),
    )):
        x = 0.6 + i * 2.15
        round_rect(s, x, 5.35, 2.05, 0.85, CARD, radius=0.12)
        textbox(s, x + 0.1, 5.45, 1.88, 0.38, name, size=12, bold=True)
        textbox(s, x + 0.1, 5.82, 1.88, 0.26, sid, size=12, color=MUTED)

    # 2 Why we process this way
    s = blank(prs)
    textbox(s, 0.6, 0.55, 12, 0.9, "Why this pipeline exists", size=32, font=SERIF)
    cards = [
        ("Under the skin", "Vein patterns are hard to copy from a photograph or a lifted print. The signal is intensity, not colour."),
        ("The outline is not a vein", "Adaptive threshold loves the fist edge. We search a margin inside the palm so the silhouette never becomes the graph."),
        ("A live hand pulses", "A printed vein map can look structural. A 0.7–4 Hz bandpass on the same NIR video asks whether blood is moving."),
    ]
    for i, (t, b) in enumerate(cards):
        x = 0.6 + i * 4.15
        round_rect(s, x, 1.85, 3.95, 4.5, CARD, radius=0.08)
        textbox(s, x + 0.3, 2.15, 3.35, 0.35, f"0{i+1}", size=14, color=CLAY, bold=True)
        textbox(s, x + 0.3, 2.6, 3.35, 1.1, t, size=22, font=SERIF)
        textbox(s, x + 0.3, 3.85, 3.35, 2.1, b, size=15, color=MUTED, leading=1.25)

    # 3 Map of every step we run
    s = blank(prs)
    textbox(s, 0.6, 0.45, 12, 0.7, "Every step we run", size=32, font=SERIF)
    textbox(s, 0.6, 1.15, 12, 0.4, "Same NIR stream. Image path and pulse path meet only at the decision.", size=16, color=MUTED)
    groups = [
        ("Capture", FOREST, ["01  NIR photograph", "02  Interior ROI", "03  Grayscale / invert"]),
        ("Enhance", FOREST, ["04  Median 5×5", "05  CLAHE", "06  Median again"]),
        ("Segment", CLAY, ["07  Adaptive threshold", "08  Close + open", "09  Drop small blobs", "10  Vein mask"]),
        ("Graph", CLAY, ["11  Skeletonize", "12  Prune spurs", "13  Endpoints / forks", "14  Overlay check"]),
        ("Decide", INK, ["15  Template match", "16  Pulse 0.7–4 Hz", "17  Weighted score"]),
    ]
    for i, (title, color, items) in enumerate(groups):
        x = 0.5 + i * 2.55
        rect(s, x, 1.8, 2.4, 0.07, color)
        textbox(s, x, 2.0, 2.4, 0.35, title.upper(), size=12, color=color, bold=True)
        for j, item in enumerate(items):
            textbox(s, x, 2.5 + j * 0.7, 2.4, 0.55, item, size=15, color=INK)

    # Process slides — no heading chrome, no footer
    step_slide(
        prs, "01", "NIR capture",
        "Raspberry Pi, NoIR camera and 850 nm LEDs. Hemoglobin absorbs near-infrared, so veins appear as dark grooves. If the long side is over 1400 px we downscale with area interpolation. Nothing else is changed.",
        [("Hardware", "Pi + NoIR + 850 nm"), ("Max long side", "1400 px")],
        nir, contain=True,
    )
    step_slide(
        prs, "02", "Hand interior",
        "Otsu-segment the palm, keep the largest filled blob, then a distance transform. Pixels closer to the background than about 5.5% of the short side (at least 20 px) are the gold silhouette band. That band is never scored as a vein.",
        [("Margin", "5.5% / min 20 px"), ("Method", "Distance transform")],
        roi, strip=True, contain=True,
    )
    step_slide(
        prs, "03", "Grayscale / invert",
        "Drop colour. The rest of the pipeline looks for darker-than-neighbourhood pixels. If this NIR capture renders veins brighter than skin, invert first (Studio: NIR invert), then convert to gray.",
        [("Default", "BGR → gray"), ("Bright veins", "bitwise_not, then gray")],
        original, strip=True, contain=True,
    )
    step_slide(
        prs, "04", "Median filter",
        "A 5×5 median replaces each pixel with the middle intensity in its window. Isolated pores and sensor spikes vanish. A consistent dark line through the window survives. Mean or Gaussian blur would smear the thin vessels.",
        [("Kernel", "5×5"), ("Why median", "Keeps edges")],
        nir, contain=True,
    )
    step_slide(
        prs, "05", "CLAHE",
        "Knuckles are bright, the wrist is darker. A global stretch would burn highlights and still hide veins in shadow. CLAHE equalizes 8×8 tiles and clips contrast at 2.0 so grain is not amplified without bound.",
        [("clipLimit", "2.0"), ("Tiles", "8×8")],
        enhanced, contain=True,
    )
    step_slide(
        prs, "06", "Second median",
        "CLAHE raises leftover grain. Thresholding that grain turns it into salt-and-pepper that later pretends to be endpoints. The same 5×5 median runs again, on purpose, after enhancement.",
        [("Kernel", "5×5"), ("When", "After CLAHE")],
        enhanced, contain=True,
    )
    step_slide(
        prs, "07", "Adaptive threshold",
        "Each pixel is compared to a Gaussian local mean minus C. Darker pixels become 0 (vein); brighter become 255. One global cutoff cannot serve a lit knuckle and a shaded wrist. C stays at 2 so thin branches are not erased.",
        [("Method", "Gaussian local"), ("blockSize", "29"), ("C", "2")],
        thresh, contain=True,
    )
    step_slide(
        prs, "08", "Morphology and blobs",
        "Invert so veins are white. Close then open with a 7×7 ellipse: close bridges gaps, open drops speckle. Then connected components — any island under 500 px is deleted. Invert back. Dark still means vein.",
        [("Kernel", "7×7 ellipse"), ("min area", "500 px")],
        mask, contain=True,
    )
    step_slide(
        prs, "09", "Vein mask",
        "Force the silhouette band to empty. Drop components that touch the frame (3 px, then a tighter 1 px pass). Drop leftover blobs whose mean distance to the background is still small. Only interior vasculature remains.",
        [("Border", "3 px, then 1 px"), ("Hug test", "mean distance")],
        mask, contain=True,
    )
    step_slide(
        prs, "10", "Skeleton",
        "Round the vessel walls (median, open, close) so jaggies cannot become fur. Then scikit-image skeletonize collapses each vessel to a 1-pixel medial axis. Walk 16–36 px from every dead-end; if you hit a fork, erase the twig.",
        [("Thinning", "skeletonize"), ("Spur length", "16–36 px")],
        skeleton, contain=True,
    )
    step_slide(
        prs, "11", "Endpoints and forks",
        "Count 8-neighbours on the skeleton. One neighbour is an endpoint (green). Three or more is a bifurcation (red). Nearby hits merge at 8 px so one anatomical fork is not a cluster of dots. This graph is the template we store.",
        [("Endpoint", "n = 1"), ("Bifurcation", "n ≥ 3"), ("Merge", "8 px")],
        landmarks, contain=True,
    )
    step_slide(
        prs, "12", "Overlay check",
        "Paint the vein mask in clay on the original photograph. Green ends, red forks. A clean skeleton on paper can still be a bracelet — fit is judged here. In Studio, wipe against the raw frame.",
        [("Tint", "62% clay"), ("Markers", "green / red")],
        overlay, contain=True,
    )
    step_slide(
        prs, "13", "Template match",
        "The enrolled record is this graph: skeleton plus the merged endpoints and bifurcations. A live capture is processed through the same steps, then compared with the stored template for a vein-matching confidence. Templates live in a local SQLite database.",
        [("Stored", "Skeleton + landmarks"), ("Store", "SQLite")],
        landmarks, contain=True,
    )

    # Liveness — no stock photo, keep it typographic
    s = blank(prs)
    textbox(s, 0.6, 0.55, 12, 0.35, "14", size=14, color=CLAY, bold=True)
    textbox(s, 0.6, 0.95, 12, 0.8, "Pulse liveness", size=32, font=SERIF)
    textbox(s, 0.6, 1.9, 12, 0.7, "Same NIR video. A printed vein map has structure. A live hand has a pulse.", size=18, color=MUTED)
    boxes = [
        ("Mean intensity", "Track average brightness in a palm ROI across frames."),
        ("Bandpass 0.7–4 Hz", "Keep heart-rate frequencies. Drop lighting flicker and motion drift."),
        ("Periodicity", "A repeating wave raises the liveness score. A flat line does not."),
    ]
    for i, (t, b) in enumerate(boxes):
        x = 0.6 + i * 4.15
        round_rect(s, x, 3.0, 3.95, 3.4, CARD, radius=0.08)
        textbox(s, x + 0.28, 3.25, 3.4, 0.3, f"0{i+1}", size=13, color=CLAY, bold=True)
        textbox(s, x + 0.28, 3.7, 3.4, 0.7, t, size=20, font=SERIF)
        textbox(s, x + 0.28, 4.55, 3.4, 1.5, b, size=15, color=MUTED, leading=1.25)

    s = blank(prs)
    textbox(s, 0.6, 0.55, 12, 0.35, "15", size=14, color=CLAY, bold=True)
    textbox(s, 0.6, 0.95, 12, 0.8, "Score fusion and decision", size=32, font=SERIF)
    textbox(s, 0.6, 1.9, 12.1, 0.8, "Vein confidence and liveness confidence are combined with a weighted sum, then compared with a threshold. Both must be satisfactory. A good vein map on a static print is rejected.", size=16, color=MUTED, leading=1.25)
    row = [
        ("Vein score", "Template similarity"),
        ("Liveness score", "Pulse periodicity"),
        ("Weighted sum", "α·vein + β·live"),
        ("Threshold", "Accept or reject"),
    ]
    for i, (t, b) in enumerate(row):
        x = 0.6 + i * 3.15
        round_rect(s, x, 3.1, 2.95, 2.6, CARD, radius=0.1)
        textbox(s, x + 0.22, 3.3, 2.5, 0.3, f"0{i+1}", size=13, color=CLAY, bold=True)
        textbox(s, x + 0.22, 3.75, 2.5, 0.7, t, size=20, font=SERIF)
        textbox(s, x + 0.22, 4.55, 2.5, 0.7, b, size=15, color=MUTED)
        if i < 3:
            textbox(s, x + 2.72, 4.05, 0.4, 0.4, "→", size=20, color=CLAY)

    # Close
    s = blank(prs, DARK)
    textbox(s, 0.6, 1.5, 12, 0.35, "UPI PAYMENT AUTHENTICATION+", size=13, color=CLAY, bold=True)
    textbox(s, 0.6, 2.0, 12, 1.4, "Every step.\nOne NIR stream.", size=40, font=SERIF, color=WHITE, leading=0.96)
    textbox(s, 0.6, 3.7, 12, 0.7, "Arnav Gour  ·  Mudrika Bajaj  ·  Shrivastav Aainaa Rajneesh", size=16, color=RGBColor(0xC8, 0xD4, 0xCC))
    textbox(s, 0.6, 4.4, 10, 0.4, "1705285     1153857     1689885", size=14, color=RGBColor(0x8F, 0xC4, 0xA8))

    prs.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
