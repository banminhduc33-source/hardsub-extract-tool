"""Kiem tra hop den theo mat na chu (stable_text_box / refine_boxes_by_mask).

Nen CHUYEN DONG nhieu net (cac o xam ngau nhien doi tung khung -> Canny hong) + phu de dung yen (vang vien den / trang vien den)."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cv2
import numpy as np
import hardsub_extract as H

W, HT, FPS = 640, 360, 30
FONT = cv2.FONT_HERSHEY_SIMPLEX
TEXT = "SUBTITLE TEXT"
POS = (90, 300)
SC, TH = 1.4, 3


def noisy_bg(rng):
    cell = 12
    g = rng.integers(0, 256, (HT // cell + 1, W // cell + 1), dtype=np.uint8)
    img = cv2.resize(g, (g.shape[1] * cell, g.shape[0] * cell), interpolation=cv2.INTER_NEAREST)[:HT, :W]
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def _text_mask():
    m = np.zeros((HT, W), np.uint8)
    cv2.putText(m, TEXT, POS, FONT, SC, 255, TH, cv2.LINE_AA)
    return m > 100


OUTLINE = cv2.dilate(_text_mask().astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0   # vien day 3px moi phia


def frame(rng, fill):
    img = noisy_bg(rng)
    img[OUTLINE] = 0                                                        # vien den (cv2.putText khong ve vien day theo thickness)
    cv2.putText(img, TEXT, POS, FONT, SC, fill, TH, cv2.LINE_AA)
    return img


def true_fill_box(fill):
    """Hop that cua cac diem mau chu (ve 1 anh sach)."""
    img = np.zeros((HT, W, 3), np.uint8)
    cv2.putText(img, TEXT, POS, FONT, SC, fill, TH, cv2.LINE_AA)
    ys, xs = np.nonzero(img.max(axis=2) > 200)
    return int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


rng = np.random.default_rng(7)
for name, fill in (("vang", (0, 220, 255)), ("trang", (255, 255, 255))):
    t = true_fill_box(fill)
    crops = [frame(rng, fill) for _ in range(6)]
    row_h = t[3] - t[2]
    # hop OCR phinh to 14px moi phia (nhu Canny tren nen nhieu)
    loose = (t[0] - 14, t[1] + 14, t[2] - 14, t[3] + 14)
    got = H.stable_text_box(crops, loose, row_h)
    print(name, "that", t, "OCR", loose, "mat na", got)
    assert got is not None, name
    # hop mat na = hop chu + vien den (<= ~4px moi phia), khong phinh nhu hop OCR
    assert close(got, (t[0] - 4, t[1] + 4, t[2] - 4, t[3] + 4), 4), (name, got)
    # hop OCR cat mat 1 doan chu (hep 6px moi phia): van lay du chu (mat na khong tin hop OCR de mo rong, chi can chua mat na)
    tight = (t[0] + 6, t[1] - 6, t[2] + 3, t[3] - 3)
    got2 = H.stable_text_box(crops, tight, row_h)
    assert got2 is not None and got2[0] <= t[0] + 1 and got2[1] >= t[1] - 1, (name, got2)
    # chi dinh dung mau
    only = H.stable_text_box(crops, loose, row_h, text_color="yellow" if name == "vang" else "white")
    assert only is not None and close(only, got, 2), (name, only)
    # chi dinh sai mau -> khong tin (None)
    wrong = H.stable_text_box(crops, loose, row_h, text_color="white" if name == "vang" else "yellow")
    assert wrong is None, (name, wrong)

# Khong co chu (chi nen chuyen dong): None
nobg = [noisy_bg(rng) for _ in range(6)]
assert H.stable_text_box(nobg, (90, 400, 260, 310), 40) is None
# Qua it khung: None
assert H.stable_text_box([frame(rng, (255, 255, 255))], (80, 400, 260, 310), 40) is None

# --- ca duong ong: video that + Track ---
fill = (0, 220, 255)
t = true_fill_box(fill)
row_h = float(t[3] - t[2])
with tempfile.TemporaryDirectory() as d:
    video = os.path.join(d, "n.mp4")
    out = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, HT))
    for i in range(90):
        if 15 <= i < 75:
            out.write(frame(rng, fill))
        else:
            out.write(noisy_bg(rng))
    out.release()

    loose = (t[0] - 14.0, t[1] + 14.0, t[2] - 14.0, t[3] + 14.0)
    step = 3
    samples = [(f / FPS, [dict(text="SUBTITLE TEXT", bbox=loose, conf=0.9, row_h=row_h)] if 18 <= f < 72 else [])
               for f in range(0, 90, step)]
    tracks = H.build_tracks(samples, step / FPS)
    assert len(tracks) == 1
    changed, tried = H.refine_boxes_by_mask(video, tracks, FPS, step, W, HT, report=True)
    nb = tracks[0].frames[0][1]
    print("sau mat na:", nb, "that", t, "doi", changed, "/", tried)
    assert (changed, tried) == (1, 1)
    assert close(nb, (t[0] - 4, t[1] + 4, t[2] - 4, t[3] + 4), 5), nb
    assert all(b == nb for _, b in tracks[0].frames)                      # cau dung yen: moi khung cung 1 hop
    assert all(len(tr.frames) >= 2 for tr in tracks)

    # cau chuyen dong (hop troi 80px) bi bo qua, khong loi
    moving = []
    for f in range(18, 72, step):
        dx = (f - 18) * 2.0
        moving.append((f / FPS, [dict(text="MOVING", bbox=(100.0 + dx, 300.0 + dx, 100.0, 140.0), conf=0.9, row_h=40.0)]))
    mt = H.build_tracks(moving, step / FPS)
    c2, n2 = H.refine_boxes_by_mask(video, mt, FPS, step, W, HT)
    assert c2 == 0, (c2, n2)

    # cau tren vung khong co chu (OCR sai): giu hop cu
    ghost = H.build_tracks([(f / FPS, [dict(text="GHOST", bbox=(400.0, 600.0, 40.0, 80.0), conf=0.9, row_h=40.0)])
                            for f in range(18, 72, step)], step / FPS)
    c3, n3 = H.refine_boxes_by_mask(video, ghost, FPS, step, W, HT)
    assert c3 == 0 and ghost[0].frames[0][1] == (400.0, 600.0, 40.0, 80.0), (c3, ghost[0].frames[0])

print("OK")
