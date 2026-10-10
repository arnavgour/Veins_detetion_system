import cv2
import matplotlib.pyplot as plt
from capture import capture_image
import numpy as np

def to_grayscale(frame):
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def segment_hand(gray):
    """Largest filled region, polarity chosen so the image center is foreground."""
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    h, w = gray.shape
    center = bw[h // 5: 4 * h // 5, w // 5: 4 * w // 5]
    if np.mean(center) < 127:
        bw = cv2.bitwise_not(bw)

    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, close_k)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if num <= 1:
        return np.full_like(gray, 255)

    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    hand = np.zeros_like(bw)
    hand[labels == largest] = 255

    contours, _ = cv2.findContours(hand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(hand)
    if contours:
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        return filled
    return hand


def interior_margin_px(shape, frac=0.055, min_px=20):
    return max(min_px, int(min(shape[:2]) * frac))


def hand_interior_mask(hand_filled, margin=None):
    """Pixels at least `margin` from the silhouette *and* the image frame."""
    if margin is None:
        margin = interior_margin_px(hand_filled.shape)
    h, w = hand_filled.shape[:2]
    padded = np.zeros((h + 2, w + 2), dtype=np.uint8)
    padded[1:-1, 1:-1] = hand_filled
    dist = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
    interior = np.zeros_like(hand_filled)
    interior[dist >= margin] = 255
    return interior, dist


def restrict_to_interior(img, interior, fill=255):
    """Force pixels outside the hand interior to `fill` (255 = not-a-vein)."""
    if interior is None or int(np.count_nonzero(interior)) < 500:
        return img
    out = img.copy()
    out[interior == 0] = fill
    return out


def strip_silhouette_pixels(binary_img, dist, min_dist=None):
    if dist is None:
        return binary_img
    if min_dist is None:
        min_dist = interior_margin_px(binary_img.shape)
    if int(np.count_nonzero(dist >= min_dist)) < 500:
        return binary_img
    out = binary_img.copy()
    out[dist < min_dist] = 255
    return out


def clip_skeleton_to_interior(skeleton, dist, min_dist=None):
    if skeleton is None or dist is None:
        return skeleton
    if min_dist is None:
        min_dist = interior_margin_px(skeleton.shape, frac=0.062, min_px=22)
    out = skeleton.copy()
    out[dist < min_dist] = False
    return out


def remove_contour_hugging_components(binary_img, dist, min_mean_dist=None, max_near_frac=0.45):
    if dist is None:
        return binary_img
    if min_mean_dist is None:
        min_mean_dist = max(12, interior_margin_px(binary_img.shape, frac=0.04, min_px=12))

    inverted = cv2.bitwise_not(binary_img)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    keep = np.zeros_like(inverted)
    for label in range(1, num_labels):
        ys, xs = np.where(labels == label)
        if len(ys) == 0:
            continue
        d = dist[ys, xs]
        if float(np.mean(d)) < min_mean_dist:
            continue
        if float(np.mean(d < min_mean_dist)) > max_near_frac:
            continue
        keep[labels == label] = 255
    return cv2.bitwise_not(keep)


def suppress_hand_outline(binary_img, interior, dist):
    """Strip the silhouette band *before* border cleanup so interior veins survive."""
    veins = strip_silhouette_pixels(binary_img, dist)
    veins = restrict_to_interior(veins, interior, fill=255)
    veins = remove_border_touching_components(veins)
    veins = remove_contour_hugging_components(veins, dist)
    return veins


def render_hand_roi(frame, hand_filled, interior):
    """Debug / UI: gold band is the excluded silhouette, green tint is the vein search region."""
    vis = frame if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    vis = vis.astype(np.float32)
    band = (hand_filled > 0) & (interior == 0)
    vis[interior > 0] = vis[interior > 0] * 0.82 + np.array([90, 150, 70], dtype=np.float32) * 0.18
    vis[band] = vis[band] * 0.35 + np.array([40, 170, 220], dtype=np.float32) * 0.65
    return np.clip(vis, 0, 255).astype(np.uint8)

MEDIAN_KSIZE = 5


def apply_median_filter(gray_img, ksize=MEDIAN_KSIZE):
    return cv2.medianBlur(gray_img, ksize)

def apply_clahe(img, clip_limit=2.0, tile_grid_size=(8, 8)):
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(img)

def apply_adaptive_threshold(img, block_size=29, c=2):
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, c
    )


def shannon_entropy(img):
    if img.ndim > 2:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([img], [0], None, [256], [0, 256]).ravel()
    p = hist / max(float(hist.sum()), 1.0)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def threshold_loss_report(before, binary, interior=None):
    if before.ndim > 2:
        before = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    dark = binary < 128
    region = interior > 0 if interior is not None else np.ones(binary.shape, dtype=bool)
    dark_i = dark & region
    labeled = np.where(dark_i, 255, 0).astype(np.uint8)
    num, _, stats, _ = cv2.connectedComponentsWithStats(labeled, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if num > 1 else np.array([], dtype=np.int32)
    e_in = shannon_entropy(before)
    e_out = shannon_entropy(binary)
    palm = max(int(region.sum()), 1)
    return {
        "gray_levels_in": int(len(np.unique(before))),
        "gray_levels_out": 2,
        "entropy_in": round(e_in, 2),
        "entropy_out": round(e_out, 2),
        "entropy_drop_pct": round(100.0 * (1.0 - e_out / max(e_in, 1e-9)), 1),
        "dark_pct_frame": round(100.0 * float(dark.mean()), 1),
        "dark_pct_palm": round(100.0 * float(dark_i.sum()) / palm, 1),
        "components": int(max(num - 1, 0)),
        "median_blob_px": int(np.median(areas)) if len(areas) else 0,
        "blobs_ge_500": int((areas >= 500).sum()) if len(areas) else 0,
    }

def remove_small_blobs(binary_img, min_area=500):
    inverted = cv2.bitwise_not(binary_img)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        inverted, connectivity=8
    )

    cleaned_inverted = np.zeros_like(inverted)
    for label in range(1, num_labels):
        area = stats[label, cv2.CC_STAT_AREA]
        if area >= min_area:
            cleaned_inverted[labels == label] = 255

    cleaned = cv2.bitwise_not(cleaned_inverted)
    return cleaned

def remove_border_touching_components(binary_img, border_margin=3):
    inverted = cv2.bitwise_not(binary_img)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    h, w = inverted.shape

    cleaned_inverted = np.zeros_like(inverted)
    for label in range(1, num_labels):
        x, y, cw, ch, area = stats[label]
        touches_border = (
                x <= border_margin or y <= border_margin or
                x + cw >= w - border_margin or y + ch >= h - border_margin
        )
        if not touches_border:
            cleaned_inverted[labels == label] = 255

    return cv2.bitwise_not(cleaned_inverted)

def smooth_binary(binary_img, kernel_size=7):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    inverted = cv2.bitwise_not(binary_img)
    smoothed = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, kernel)
    smoothed = cv2.morphologyEx(smoothed, cv2.MORPH_OPEN, kernel)
    return cv2.bitwise_not(smoothed)

def preprocess_pipeline(frame, show_steps=True):
    gray = to_grayscale(frame)
    hand = segment_hand(gray)
    interior, dist = hand_interior_mask(hand)
    median = apply_median_filter(gray)
    clahe_img = apply_clahe(median)
    median2 = apply_median_filter(clahe_img)
    thresholded = apply_adaptive_threshold(median2)
    smooth = smooth_binary(thresholded)
    cleaned = remove_small_blobs(smooth)
    veins = suppress_hand_outline(cleaned, interior, dist)

    if show_steps:
        stages = [
            ("Grayscale", gray),
            ("Median Filter", median),
            ("CLAHE", clahe_img),
            ("Median Filter 2", median2),
            ("Adaptive Threshold", thresholded),
            ("Smooth", smooth),
            ("Blob Filtered", cleaned),
            # ("Skeleton Removal", veins),
        ]
        fig, axes = plt.subplots(1, len(stages), figsize=(24, 4))
        for ax, (title, img) in zip(axes, stages):
            ax.imshow(img, cmap="gray")
            ax.set_title(title, fontsize=10)
            ax.axis("off")
        plt.tight_layout()
        plt.show()

    return veins


if __name__ == "__main__":
    image = capture_image(source="sample")
    result = preprocess_pipeline(image)
    cv2.imwrite("data/output_thresholded.jpg", result)
    print("Saved final processed image to data/output_thresholded.jpg")