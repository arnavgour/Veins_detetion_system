import cv2
import matplotlib.pyplot as plt
from capture import capture_image
import numpy as np

def to_grayscale(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

def apply_median_filter(gray_img, ksize=15):
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
    median = apply_median_filter(gray)
    clahe_img = apply_clahe(median)
    median2 = apply_median_filter(clahe_img)
    thresholded = apply_adaptive_threshold(median2)
    smooth = smooth_binary(thresholded)
    cleaned = remove_small_blobs(smooth)
    veins = remove_border_touching_components(cleaned)

    if show_steps:
        stages = [
            ("Grayscale", gray),
            ("Median Filter", median),
            ("CLAHE", clahe_img),
            ("Median Filter 2", median2),
            ("Adaptive Threshold", thresholded),
            ("Smooth", smooth),
            ("Blob Filtered", cleaned),
            ("Skeleton Removal", veins),
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