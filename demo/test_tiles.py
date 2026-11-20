"""Kiem tra quet theo o chong len nhau (detect_tiled / merge_dup_boxes / parse_tiles / auto_det_side).

Bo OCR gia: tim cac khoi trang bang thanh phan lien thong, va MO PHONG viec bo do chu thu anh ve det_side=640 -> chu cao nho
tren anh lon bi sot (cao < 12px sau khi thu). Nho vay quet ca khung bo sot chu nho, quet theo o thi bat duoc."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cv2
import numpy as np
import hardsub_extract as H

DET = 640


class FakeDet:
    def __init__(self):
        self.calls = []

    def detect(self, img):
        self.calls.append(img.shape[:2])
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        k = min(1.0, DET / max(g.shape))                       # PaddleOCR thu anh lon ve det_side
        n, _lab, st, _ = cv2.connectedComponentsWithStats((g > 128).astype(np.uint8), connectivity=8)
        out = []
        for i in range(1, n):
            x, y, w, h, _a = st[i]
            if h * k < 12 or w < 4:
                continue
            out.append(dict(text="字" * max(1, w // 20), conf=0.9, x_min=float(x), x_max=float(x + w), y_min=float(y),
                            y_max=float(y + h), poly=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
        return out


W, HT = 1920, 1080
img = np.zeros((HT, W, 3), np.uint8)
items = {                                   # ten -> (x1, x2, y1, y2)   cao 28px = chu nho tren video 1080p
    "tl": (100, 300, 100, 128),
    "tr": (1500, 1700, 120, 148),
    "bl": (120, 330, 900, 928),
    "br": (1450, 1700, 950, 978),
    "mid": (880, 1100, 500, 528),           # nam tron trong 2 o -> 2 o cung thay, phai gop con 1
    "seam": (1050, 1200, 700, 728),         # o trai bi cat o x=1133 (mep o), o phai thay tron -> giu ban tron
    "big": (700, 1200, 300, 380),           # chu to: ca khung cung thay
}
for x1, x2, y1, y2 in items.values():
    img[y1:y2, x1:x2] = 255

# 1) 1x1: chi 1 luot, chu nho bi sot
e = FakeDet()
one = H.detect_tiled(e, img, (1, 1))
assert len(e.calls) == 1 and len(one) == 1, (len(e.calls), len(one))           # chi "big" (cao 80*0.33=26px)

# 2) 2x2: du hop, khong trung, khong bi cat
e = FakeDet()
res = H.detect_tiled(e, img, (2, 2))
assert len(e.calls) == 5, e.calls                                               # 1 luot ca khung + 4 o
assert len(res) == len(items), (len(res), [(b["x_min"], b["y_min"]) for b in res])
for name, (x1, x2, y1, y2) in items.items():
    hit = [b for b in res if abs(b["x_min"] - x1) <= 1 and abs(b["x_max"] - x2) <= 1 and abs(b["y_min"] - y1) <= 1 and abs(b["y_max"] - y2) <= 1]
    assert len(hit) == 1, (name, hit)
    assert "clipped" not in hit[0]
    assert hit[0]["poly"][0] == (x1, y1), (name, hit[0]["poly"])                # da giac cung duoc doi ve toa do anh goc

# 3) co chuyen vao detect_frame_blocks: toa do quy ve khung goc, ROI offset + scale
blocks = H.detect_frame_blocks(FakeDet(), img, (10, 20), 1.0, cjk_only=True, min_h=0, min_chars=1, tiles=(2, 2))
assert len(blocks) >= 1
assert min(b["bbox"][0] for b in blocks) >= 10 + 100 - 1

# 4) anh nho: khong chia o (o < TILE_MIN_SIDE)
small = np.zeros((300, 500, 3), np.uint8)
small[100:140, 100:300] = 255
e = FakeDet()
H.detect_tiled(e, small, (2, 2))
assert len(e.calls) == 1

# 5) merge_dup_boxes: uu tien o khong bi cat, roi nhieu chu hon
a = dict(text="ab", conf=0.99, x_min=0, x_max=50, y_min=0, y_max=20, clipped=True)
b = dict(text="abc", conf=0.5, x_min=0, x_max=80, y_min=0, y_max=20)
assert H.merge_dup_boxes([a, b])[0]["text"] == "abc"
far = dict(text="zz", conf=0.9, x_min=200, x_max=240, y_min=0, y_max=20)
assert len(H.merge_dup_boxes([a, b, far])) == 2
# 2 dong sat nhau (chong mep tren/duoi it) khong bi coi la trung
l1 = dict(text="line1", conf=0.9, x_min=0, x_max=100, y_min=0, y_max=20)
l2 = dict(text="line2", conf=0.9, x_min=0, x_max=100, y_min=21, y_max=41)
assert len(H.merge_dup_boxes([l1, l2])) == 2

# 6) parse_tiles / auto_det_side
assert H.parse_tiles("auto", 1920, 1080) == (2, 2)
assert H.parse_tiles("auto", 768, 576) == (1, 1)
assert H.parse_tiles("auto", 1920, 270) == (2, 1)
assert H.parse_tiles("3x2", 100, 100) == (3, 2) and H.parse_tiles("1x1", 1920, 1080) == (1, 1)
try:
    H.parse_tiles("abc", 1, 1)
    raise SystemExit("phai bao loi")
except ValueError:
    pass
for tl, (rw, rh) in (((2, 2), (1920, 1080)), ((1, 1), (768, 576)), ((2, 1), (1920, 270))):
    d = H.auto_det_side(rw, rh, 2.0, tl)
    assert 960 <= d <= 1280 and d % 32 == 0, (tl, d)
print("OK")
