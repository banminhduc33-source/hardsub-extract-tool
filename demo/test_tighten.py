"""Kiem tra siet hop OCR theo net chu (tighten_box)."""
import os, sys
import numpy as np
import cv2
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import hardsub_extract as H

# Anh nen toi, chu trang vien den (giong hardsub)
img = np.zeros((200, 600, 3), np.uint8)
cv2.putText(img, "HARDSUB", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 8)
cv2.putText(img, "HARDSUB", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Hop that cua chu (tu cac diem sang)
ys, xs = np.where(gray > 128)
true = (xs.min(), xs.max() + 1, ys.min(), ys.max() + 1)
print("true", true)

# 1) hop OCR thua nen: 10px moi phia -> phai siet lai sat chu (sai so <= 3px moi mep)
loose = (true[0] - 10, true[1] + 10, true[2] - 10, true[3] + 10)
t = H.tighten_box(gray, loose)
print("loose ->", t)
assert all(abs(a - b) <= 3 for a, b in zip(t, true)), t

# 2) hop OCR cat mat chu (hep 5px moi phia) -> mo rong ra gan het chu
tight = (true[0] + 5, true[1] - 5, true[2] + 5, true[3] - 5)
t2 = H.tighten_box(gray, tight)
print("clipped ->", t2)
assert all(abs(a - b) <= 4 for a, b in zip(t2, true)), t2

# 3) hop toan nen trong: giu nguyen
blank = np.zeros((100, 300), np.uint8)
assert H.tighten_box(blank, (10, 200, 10, 80)) == (10, 200, 10, 80)

# 4) hop qua nho / sat mep anh khong loi
H.tighten_box(gray, (0, 3, 0, 3))
H.tighten_box(gray, (-5, 700, -5, 300))

# 5) _axis_aligned
assert H._axis_aligned([(0, 0), (100, 1), (100, 30), (0, 29)])
assert not H._axis_aligned([(0, 0), (100, 20), (95, 50), (0, 30)])
print("OK")
