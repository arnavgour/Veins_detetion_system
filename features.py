import cv2
import numpy as np
from skimage.morphology import skeletonize
from scipy.ndimage import label as cluster_label

def remove_border_touching_components(binary_img, border_margin=1):
    inverted = cv2.bitwise_not(binary_img)   # foreground -> white(255)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    h, w = inverted.shape

    cleaned_inverted = np.zeros_like(inverted)
    for lbl in range(1, num_labels):
        x, y, cw, ch, area = stats[lbl]
        touches_border = (
                x <= border_margin or y <= border_margin or
                x + cw >= w - border_margin or y + ch >= h - border_margin
        )
        if not touches_border:
            cleaned_inverted[labels == lbl] = 255

    return cv2.bitwise_not(cleaned_inverted)


def smooth_binary(binary_img, kernel_size=5):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    inverted = cv2.bitwise_not(binary_img)
    smoothed = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, kernel)
    smoothed = cv2.morphologyEx(smoothed, cv2.MORPH_OPEN, kernel)
    return cv2.bitwise_not(smoothed)


def get_skeleton(thresholded_img):
    veins_as_foreground = thresholded_img < 128
    skeleton = skeletonize(veins_as_foreground)
    return skeleton

def count_neighbors(skeleton):
    kernel = np.array([[1, 1, 1],
                       [1, 0, 1],
                       [1, 1, 1]])
    skeleton_int = skeleton.astype(np.uint8)
    neighbor_count = cv2.filter2D(skeleton_int, -1, kernel, borderType=cv2.BORDER_CONSTANT)
    return neighbor_count


def classify_points(skeleton):
    neighbor_count = count_neighbors(skeleton)
    endpoints, branch_points = [], []

    ys, xs = np.where(skeleton)
    for y, x in zip(ys, xs):
        n = neighbor_count[y, x]
        if n == 1:
            endpoints.append((y, x))
        elif n >= 3:
            branch_points.append((y, x))

    return endpoints, branch_points

def prune_spurs(skeleton, max_spur_length=8):
    skeleton = skeleton.copy()
    neighbor_count = count_neighbors(skeleton)
    endpoints = [tuple(p) for p in np.argwhere(skeleton & (neighbor_count == 1))]

    for start in endpoints:
        path = [start]
        current = start
        prev = None

        for _ in range(max_spur_length):
            y, x = current
            neighbors = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < skeleton.shape[0] and 0 <= nx < skeleton.shape[1]:
                        if skeleton[ny, nx] and (ny, nx) != prev:
                            neighbors.append((ny, nx))

            if len(neighbors) == 0:
                break
            if len(neighbors) >= 2:
                for (py, px) in path:
                    skeleton[py, px] = False
                break

            prev = current
            current = neighbors[0]
            path.append(current)

    return skeleton

def merge_nearby_points(points, image_shape, cluster_radius=8):
    if not points:
        return []

    mask = np.zeros(image_shape, dtype=np.uint8)
    for y, x in points:
        mask[y, x] = 1

    kernel = np.ones((cluster_radius, cluster_radius))
    dilated = cv2.dilate(mask, kernel)
    labeled, num_clusters = cluster_label(dilated)

    merged = []
    for cid in range(1, num_clusters + 1):
        ys, xs = np.where((labeled == cid) & (mask == 1))
        if len(ys) > 0:
            merged.append((int(np.mean(ys)), int(np.mean(xs))))

    return merged

def extract_feature_points(thresholded_img, max_spur_length=8,
                           smooth_kernel=5, cluster_radius=8,
                           remove_outline=True):

    img = thresholded_img
    if remove_outline:
        img = remove_border_touching_components(img)

    img = smooth_binary(img, kernel_size=smooth_kernel)

    skeleton = get_skeleton(img)
    skeleton = prune_spurs(skeleton, max_spur_length=max_spur_length)

    endpoints, branch_points = classify_points(skeleton)

    endpoints = merge_nearby_points(endpoints, skeleton.shape, cluster_radius)
    branch_points = merge_nearby_points(branch_points, skeleton.shape, cluster_radius)

    return skeleton, endpoints, branch_points

def visualize_feature_points(skeleton, endpoints, branch_points, save_path="data/feature_points.jpg"):
    vis = cv2.cvtColor((skeleton * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)

    for y, x in endpoints:
        cv2.circle(vis, (x, y), 4, (0, 255, 0), -1)   # green = endpoint

    for y, x in branch_points:
        cv2.circle(vis, (x, y), 4, (0, 0, 255), -1)   # red = branch point

    cv2.imwrite(save_path, vis)
    print(f"Saved visualization to {save_path}")
    return vis


if __name__ == "__main__":
    thresholded = cv2.imread("data/output_veins.png", cv2.IMREAD_GRAYSCALE)
    if thresholded is None:
        raise FileNotFoundError("Run preprocess.py first to generate data/output_thresholded.jpg")

    skeleton, endpoints, branch_points = extract_feature_points(
        thresholded,
        max_spur_length=8,
        smooth_kernel=5,
        cluster_radius=8,
        remove_outline=True,
    )

    print(f"Endpoints: {len(endpoints)}")
    print(f"Branch points: {len(branch_points)}")

    visualize_feature_points(skeleton, endpoints, branch_points)