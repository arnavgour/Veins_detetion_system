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


def spur_length_px(shape, frac=0.016, min_px=16, max_px=36):
    return min(max_px, max(min_px, int(min(shape[:2]) * frac)))


def prepare_skeleton_mask(binary_img, kernel_size=9, median_ksize=5, gauss_ksize=7):
    """Round vessel walls so thinning does not grow a fur of false spurs."""
    inv = cv2.bitwise_not(binary_img)
    if median_ksize >= 3:
        inv = cv2.medianBlur(inv, median_ksize)
    if gauss_ksize >= 3:
        blur = cv2.GaussianBlur(inv, (gauss_ksize, gauss_ksize), 0)
        _, inv = cv2.threshold(blur, 127, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    inv = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel)
    inv = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel)
    return cv2.bitwise_not(inv)


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

def prune_spurs(skeleton, max_spur_length=8, max_rounds=6):
    skeleton = np.asarray(skeleton, dtype=bool).copy()
    h, w = skeleton.shape
    for _ in range(max_rounds):
        neighbor_count = count_neighbors(skeleton)
        starts = [tuple(p) for p in np.argwhere(skeleton & (neighbor_count == 1))]
        changed = False
        for start in starts:
            if not skeleton[start]:
                continue
            path = [start]
            current = start
            prev = None
            hit_junction = False
            for _step in range(max_spur_length):
                y, x = current
                neighbors = []
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and skeleton[ny, nx] and (ny, nx) != prev:
                            neighbors.append((ny, nx))
                if len(neighbors) == 0:
                    break
                if len(neighbors) >= 2:
                    hit_junction = True
                    break
                prev = current
                current = neighbors[0]
                path.append(current)
            if hit_junction:
                for py, px in path:
                    skeleton[py, px] = False
                changed = True
        if not changed:
            break
    return skeleton


def drop_short_skeleton_segments(skeleton, min_len=16):
    img = (np.asarray(skeleton, dtype=np.uint8) * 255)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(img, connectivity=8)
    keep = np.zeros(skeleton.shape, dtype=bool)
    for i in range(1, num):
        if stats[i, cv2.CC_STAT_AREA] >= min_len:
            keep[labels == i] = True
    return keep

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

def extract_feature_points(thresholded_img, max_spur_length=None,
                           smooth_kernel=9, cluster_radius=8,
                           remove_outline=True):

    img = thresholded_img
    if remove_outline:
        img = remove_border_touching_components(img)

    img = prepare_skeleton_mask(img, kernel_size=smooth_kernel)

    if max_spur_length is None:
        max_spur_length = spur_length_px(img.shape)

    skeleton = get_skeleton(img)
    skeleton = prune_spurs(skeleton, max_spur_length=max_spur_length)
    skeleton = drop_short_skeleton_segments(skeleton, min_len=max_spur_length)

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