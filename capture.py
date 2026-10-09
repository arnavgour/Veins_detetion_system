import cv2
import os

def capture_image(source="sample", path="data/sample_veins/1.bmp"):
    if source == "sample":
        image = cv2.imread(path)
        if image is None:
            print(f"Error: Could not load image from {path}")
            return None
        return image

    elif source == "webcam":
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("Could not read from webcam.")
            return None
        return frame

    elif source == "nir":
        print("Not available yet")
        return None

    else:
        return None

if __name__ == "__main__":
    image = capture_image(source="sample")
    print("Image shape:", image.shape)
    cv2.imshow("Captured Image", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()