"""Collect every preprocess and feature-extraction stage for the demo UI."""

from __future__ import annotations

import base64
import time

import cv2
import numpy as np

from features import (
    classify_points,
    get_skeleton,
    merge_nearby_points,
    prune_spurs,
    remove_border_touching_components as features_remove_border,
    smooth_binary as features_smooth,
)
from inversionPreProcess import invert_and_grayscale
from preprocess import (
    apply_adaptive_threshold,
    apply_clahe,
    apply_median_filter,
    clip_skeleton_to_interior,
    hand_interior_mask,
    remove_small_blobs,
    render_hand_roi,
    segment_hand,
    smooth_binary,
    suppress_hand_outline,
    to_grayscale,
)

MAX_SIDE = 1400


def maybe_resize(img: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img
    scale = max_side / longest
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def encode_image(img: np.ndarray, fmt: str = "jpg") -> str:
    """Return a data-URL for a BGR or grayscale OpenCV image."""
    if fmt == "jpg":
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        mime = "image/jpeg"
    else:
        ok, buf = cv2.imencode(".png", img, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])
        mime = "image/png"
    if not ok:
        raise ValueError("Failed to encode image")
    return f"data:{mime};base64,{base64.b64encode(buf).decode('ascii')}"


def _to_bgr(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def _paper_canvas(shape, color=(241, 246, 248)) -> np.ndarray:
    h, w = shape[:2]
    return np.full((h, w, 3), color, dtype=np.uint8)


def _render_binary(binary: np.ndarray) -> np.ndarray:
    """Keep dark veins on a warm white field."""
    return binary if binary.ndim == 2 else cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)


def _render_skeleton(skeleton: np.ndarray) -> np.ndarray:
    canvas = _paper_canvas(skeleton.shape)
    thick = cv2.dilate(skeleton.astype(np.uint8) * 255, np.ones((2, 2), np.uint8))
    canvas[thick > 0] = (48, 46, 44)
    return canvas


def _marker_radius(shape) -> int:
    return max(5, int(min(shape[:2]) * 0.007))


def _draw_landmarks(canvas: np.ndarray, endpoints, branch_points) -> np.ndarray:
    vis = canvas.copy()
    r = _marker_radius(vis.shape)
    for y, x in endpoints:
        cv2.circle(vis, (int(x), int(y)), r, (80, 168, 64), -1)
        cv2.circle(vis, (int(x), int(y)), r, (255, 255, 255), 1)
    for y, x in branch_points:
        cv2.circle(vis, (int(x), int(y)), r, (56, 62, 214), -1)
        cv2.circle(vis, (int(x), int(y)), r, (255, 255, 255), 1)
    return vis


def _overlay(original_bgr: np.ndarray, vein_mask: np.ndarray, endpoints, branch_points) -> np.ndarray:
    base = _to_bgr(original_bgr).astype(np.float32)
    color = np.array([52, 86, 196], dtype=np.float32)
    tinted = base.copy()
    tinted[vein_mask] = tinted[vein_mask] * 0.38 + color * 0.62
    out = np.clip(tinted, 0, 255).astype(np.uint8)
    return _draw_landmarks(out, endpoints, branch_points)


def _step(step_id, title, description, group, img, fmt="jpg"):
    return {
        "type": "step",
        "id": step_id,
        "title": title,
        "description": description,
        "group": group,
        "image": encode_image(img, fmt),
    }


def iter_analysis(frame: np.ndarray, invert: bool = False, filename: str = "upload"):
    """Yield NDJSON-ready events as each pipeline stage completes."""
    started = time.perf_counter()
    frame = maybe_resize(frame)
    h, w = frame.shape[:2]
    yield {
        "type": "meta",
        "filename": filename,
        "width": w,
        "height": h,
        "invert": invert,
    }

    yield _step(
        "original",
        "Original capture",
        "The uploaded dorsal-hand image as received. Later stages hang vein geometry back onto this frame.",
        "capture",
        frame,
        "jpg",
    )

    native_gray = to_grayscale(frame)
    hand = segment_hand(native_gray)
    interior, dist = hand_interior_mask(hand)
    yield _step(
        "hand",
        "Hand interior ROI",
        "The palm is segmented and a gold band along the silhouette is excluded. Vein pixels in that band are deleted after thresholding so the hand outline cannot be mistaken for a vessel.",
        "capture",
        render_hand_roi(frame, hand, interior),
        "jpg",
    )

    if invert:
        gray = invert_and_grayscale(frame)
        yield _step(
            "gray",
            "Invert + grayscale",
            "Colors are inverted so bright NIR veins become dark, then reduced to a single intensity channel.",
            "enhance",
            gray,
            "jpg",
        )
    else:
        gray = native_gray
        yield _step(
            "gray",
            "Grayscale",
            "Color is discarded so contrast is driven only by intensity — the signal that veins actually live in.",
            "enhance",
            gray,
            "jpg",
        )

    median = apply_median_filter(gray)
    yield _step(
        "median",
        "Median filter",
        "A wide median blur knocks out sensor grain and pores while keeping the elongated vein edges intact.",
        "enhance",
        median,
        "jpg",
    )

    clahe_img = apply_clahe(median)
    yield _step(
        "clahe",
        "CLAHE enhancement",
        "Contrast Limited Adaptive Histogram Equalization lifts faint subcutaneous veins without blowing out skin.",
        "enhance",
        clahe_img,
        "jpg",
    )

    median2 = apply_median_filter(clahe_img)
    yield _step(
        "median2",
        "Second median pass",
        "CLAHE amplifies leftover grain, so a second median pass calms the field before thresholding.",
        "enhance",
        median2,
        "jpg",
    )

    thresholded = apply_adaptive_threshold(median2)
    yield _step(
        "threshold",
        "Adaptive threshold",
        "Local Gaussian thresholding turns darker-than-neighborhood pixels into a binary vein hypothesis. The hand outline often appears here; it is stripped in the vein-mask stage.",
        "segment",
        _render_binary(thresholded),
        "png",
    )

    smooth = smooth_binary(thresholded)
    yield _step(
        "smooth",
        "Morphological smooth",
        "Closing then opening with an elliptical kernel bridges small gaps and erases speckle in the mask.",
        "segment",
        _render_binary(smooth),
        "png",
    )

    cleaned = remove_small_blobs(smooth)
    yield _step(
        "blobs",
        "Blob filter",
        "Connected components smaller than the area cutoff are dropped so pores and noise never become veins.",
        "segment",
        _render_binary(cleaned),
        "png",
    )

    veins = suppress_hand_outline(cleaned, interior, dist)
    yield _step(
        "mask",
        "Vein mask",
        "Every pixel in the silhouette band is forced to not-a-vein, then leftover border and contour-hugging blobs are dropped so only interior vasculature remains.",
        "segment",
        _render_binary(veins),
        "png",
    )

    outlined = features_remove_border(veins)
    yield _step(
        "outline",
        "Outline isolation",
        "A tighter border pass (used by feature extraction) removes any remaining silhouette still clinging to the mask.",
        "extract",
        _render_binary(outlined),
        "png",
    )

    skel_src = features_smooth(outlined, kernel_size=5)
    yield _step(
        "skel_prep",
        "Skeleton prep",
        "A lighter morphological smooth prepares a clean foreground for 1-pixel thinning.",
        "extract",
        _render_binary(skel_src),
        "png",
    )

    skeleton = clip_skeleton_to_interior(get_skeleton(skel_src), dist)
    yield _step(
        "skeleton",
        "Skeletonization",
        "The vein mask is thinned to a centerline graph, then any centerline still hugging the hand contour is clipped away.",
        "extract",
        _render_skeleton(skeleton),
        "png",
    )

    pruned = clip_skeleton_to_interior(prune_spurs(skeleton, max_spur_length=8), dist)
    yield _step(
        "pruned",
        "Spur pruning",
        "Short dead-end twigs (false spurs from noisy borders) are walked back and erased from the graph.",
        "extract",
        _render_skeleton(pruned),
        "png",
    )

    endpoints, branch_points = classify_points(pruned)
    endpoints = merge_nearby_points(endpoints, pruned.shape, cluster_radius=8)
    branch_points = merge_nearby_points(branch_points, pruned.shape, cluster_radius=8)

    atlas = _draw_landmarks(_render_skeleton(pruned), endpoints, branch_points)
    yield _step(
        "landmarks",
        "Feature landmarks",
        "Pixels with one neighbor are endpoints (green). Pixels with three or more are bifurcations (red). Nearby detections are merged.",
        "extract",
        atlas,
        "png",
    )

    vein_mask = veins < 128
    overlay = _overlay(frame, vein_mask, endpoints, branch_points)
    yield _step(
        "overlay",
        "Vein overlay",
        "The extracted mask and landmarks are composited onto the original photograph so you can judge anatomical fit.",
        "extract",
        overlay,
        "jpg",
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    yield {
        "type": "features",
        "endpoints": [{"x": int(x), "y": int(y)} for y, x in endpoints],
        "branches": [{"x": int(x), "y": int(y)} for y, x in branch_points],
        "metrics": {
            "endpoints": len(endpoints),
            "branches": len(branch_points),
            "skeleton_pixels": int(pruned.sum()),
            "vein_pixels": int(vein_mask.sum()),
            "width": w,
            "height": h,
            "elapsed_ms": elapsed_ms,
        },
        "original": encode_image(frame, "jpg"),
        "overlay": encode_image(overlay, "jpg"),
    }
    yield {"type": "done", "elapsed_ms": elapsed_ms}
