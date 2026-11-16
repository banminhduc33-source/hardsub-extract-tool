import cv2
import numpy as np

W, H, FPS = 640, 360, 30
out = cv2.VideoWriter("test_input.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))

def frame_with_text(text, x, y, scale=1.3, thickness=2):
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (40, 40, 40)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return img

# Cau 1: xuat hien dich sang phai dan 8 frame dau (gia lap hieu ung go chu / can le),
# roi dung yen 22 frame sau -> ky vong cong cu phat hien "cuoi cau" lech so voi luc dau.
for i in range(30):
    x = 260 - min(i, 8) * 6   # 260 -> 212, dich dan sang trai 8 frame dau roi dung yen
    out.write(frame_with_text("HELLO WORLD", x, 300))

# Khoang trong 5 frame (khong co chu) -> ngat cau
for i in range(5):
    out.write(frame_with_text("", 0, 0))

# Cau 2: on dinh ngay tu dau, khong doi vi tri -> khong co nhanh "cuoi cau"
for i in range(25):
    out.write(frame_with_text("STATIC TEXT", 230, 300))

out.release()
print("done")
