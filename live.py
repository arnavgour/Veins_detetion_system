import cv2, os
from datetime import datetime

PI_IP = "100.105.134.6"   # your Pi's IP
cap = cv2.VideoCapture(f"tcp://{PI_IP}:8888", cv2.CAP_FFMPEG)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
os.makedirs("captures", exist_ok=True)

while True:
    ok, frame = cap.read()
    if not ok:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enh = clahe.apply(cv2.GaussianBlur(gray, (5, 5), 0))
    cv2.imshow("Raw", gray)
    cv2.imshow("Enhanced", enh)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("s"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(f"captures/{ts}_raw.png", gray)
        cv2.imwrite(f"captures/{ts}_enhanced.png", enh)
        print("saved", ts)
    elif key == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()