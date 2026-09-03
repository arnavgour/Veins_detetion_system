import cv2
import matplotlib.pyplot as plt
from capture import capture_image

def to_grayscale(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

def apply_median_filter(gray_img, ksize=5):
    return cv2.medianBlur(gray_img, ksize)

def apply_clahe(img, clip_limit=2.0, tile_grid_size=(8, 8)):
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(img)

def apply_adaptive_threshold(img, block_size=11, c=2):
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, c
    )

def preprocess_pipeline(frame, show_steps=True):
    gray = to_grayscale(frame)
    median = apply_median_filter(gray)
    clahe_img = apply_clahe(median)
    median2 = apply_median_filter(clahe_img)
    thresholded = apply_adaptive_threshold(median2)

    if show_steps:
        stages = [
            ("Grayscale", gray),
            ("Median Filter", median),
            ("CLAHE", clahe_img),
            ("Median Filter 2", median2),
            ("Adaptive Threshold", thresholded),
        ]
        fig, axes = plt.subplots(1, len(stages), figsize=(20, 4))
        for ax, (title, img) in zip(axes, stages):
            ax.imshow(img, cmap="gray")
            ax.set_title(title, fontsize=10)
            ax.axis("off")
        plt.tight_layout()
        plt.show()

    return thresholded


if __name__ == "__main__":
    image = capture_image(source="sample")
    result = preprocess_pipeline(image)
    cv2.imwrite("data/output_thresholded.jpg", result)
    print("Saved final processed image to data/output_thresholded.jpg")