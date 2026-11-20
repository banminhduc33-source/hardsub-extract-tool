"""Kiem tra: (1) build_blocks khong noi chuoi cac o chu thanh khoi phinh to; (2) simplify_kfs go KF zich-zac do nhieu OCR nhung giu goc
ngoat that; (3) tighten_poly siet da giac chu nghieng theo net chu; (4) cau truot co nhieu OCR ra it KF."""
import math, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2, numpy as np
import hardsub_extract as H

# 1) 12 hang chu sat nhau: khong gioi han -> 1 khoi khong lo; co gioi han -> nhieu khoi, moi khoi <= MAX_BLOCK_ROWS hang
boxes = [dict(text="测试文字", x_min=100, x_max=300, y_min=20 + i * 30, y_max=45 + i * 30, conf=.9, poly=None) for i in range(12)]
assert len(H.build_blocks(boxes, max_rows=0)) == 1
bl = H.build_blocks(boxes)
assert len(bl) > 1 and all(b["bbox"][3] - b["bbox"][2] <= H.MAX_BLOCK_ROWS * 25 + 30 for b in bl), [b["bbox"] for b in bl]
two = H.build_blocks(boxes[:2])                      # phu de 2 dong binh thuong van gop
assert len(two) == 1

# 2) simplify_kfs: nhieu +-2px quanh duong thang -> chi con 2 KF; goc ngoat 40px van giu
random.seed(0)
line = [(i * 0.1, (100 + 10 * i + random.uniform(-2, 2),) * 2 + (50.0, 90.0)) for i in range(10)]
assert len(H.simplify_kfs(line, 3.0)) == 2
bent = [(i * 0.1, (100 + (10 * i if i < 5 else 50 + 40 * (i - 5)),) * 2 + (50.0, 90.0)) for i in range(10)]
assert len(H.simplify_kfs(bent, 3.0)) == 3

# 3) tighten_poly: chu nghieng 15 do, da giac no ~1.2 lan -> thu ve gan net chu
img = np.zeros((300, 500), np.uint8) + 30
cv2.putText(img, "HELLO WORLD", (100, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 255, 3)
(tw, th), _ = cv2.getTextSize("HELLO WORLD", cv2.FONT_HERSHEY_SIMPLEX, 1.6, 3)
M = cv2.getRotationMatrix2D((250, 150), 15, 1)
rot = cv2.warpAffine(img, M, (500, 300), borderValue=30)
c = M @ np.array([100 + tw / 2, 170 - th / 2, 1.0])
a = math.radians(-15)
L, t = tw * 1.2, th * 1.5 * 1.2
pt = lambda s, r: (c[0] + s * math.cos(a) - r * math.sin(a), c[1] + s * math.sin(a) + r * math.cos(a))
poly = [pt(-L / 2, -t / 2), pt(L / 2, -t / 2), pt(L / 2, t / 2), pt(-L / 2, t / 2)]
g0, g1 = H._quad_geom(poly), H._quad_geom(H.tighten_poly(rot, poly))
assert g1["t"] < 0.7 * g0["t"] and abs(g1["theta"] - g0["theta"]) < 1.0 and g1["L"] > 0.85 * tw, (g0, g1)

# 4) cau truot vao - nam yen - truot ra co nhieu OCR: it KF, KF cuoi dung luc ket thuc
step = 1 / 12
bx = []
for i in range(60):
    x = -300 + 30 * i if i < 10 else (0 if i < 45 else 30 * (i - 44))
    x += random.uniform(-5, 5)
    bx.append((200 + x, 500 + x, 300 + random.uniform(-3, 3), 340 + random.uniform(-3, 3)))
tr = H.Track(0, dict(text="测试文字内容", bbox=bx[0], conf=.9, row_h=40))
tr.frames = [(i * step, b) for i, b in enumerate(bx)]
tr.texts, tr.polys, tr.row_hs, tr.confs = ["测试文字内容"] * 60, [[]] * 60, [40] * 60, [.9] * 60
tr.last_t = 59 * step
_, kfs, _ = H.summarize_ex(tr, step)
assert 4 <= len(kfs) <= 16, len(kfs)
assert all(kfs[i][0] < kfs[i + 1][0] for i in range(len(kfs) - 1))
print("OK", len(kfs))
