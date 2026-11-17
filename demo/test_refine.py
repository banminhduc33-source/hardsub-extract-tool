"""Kiem tra tinh chinh moc bat dau/ket thuc theo khung hinh goc (refine_edges).

Video gia 30fps: cau A hien dot ngot o khung 10..49, cau B mo dan (khung 70 mo, 71 nua mo, 72+ ro) toi khung 99.
OCR gia chi "doc" duoc cac khung lay mau (moi `step` khung) va bo sot khung mo -> moc OCR tre so voi thuc te."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cv2
import numpy as np
import hardsub_extract as H

W, HT, FPS = 640, 360, 30
FONT, SCALE, THICK = cv2.FONT_HERSHEY_SIMPLEX, 1.3, 2
TEXT_A, TEXT_B = "HELLO WORLD", "SECOND LINE"
POS_A, POS_B = (212, 300), (150, 200)
A_FRAMES = range(10, 50)            # chu hien dot ngot
B_ALPHA = {70: 0.35, 71: 0.7}       # B: mo dan, tu khung 72 ro han
B_LAST = 99


def bg():
    img = np.zeros((HT, W, 3), np.uint8)
    img[:] = (40, 40, 40)
    img[:, :, 1] = np.linspace(30, 70, W, dtype=np.uint8)[None, :]      # nen chuyen mau nhe
    return img


def draw(img, text, pos, alpha=1.0):
    layer = img.copy()
    cv2.putText(layer, text, pos, FONT, SCALE, (255, 255, 255), THICK, cv2.LINE_AA)
    return cv2.addWeighted(layer, alpha, img, 1 - alpha, 0)


def frame(i):
    img = bg()
    if i in A_FRAMES:
        img = draw(img, TEXT_A, POS_A)
    if 70 <= i <= B_LAST:
        img = draw(img, TEXT_B, POS_B, B_ALPHA.get(i, 1.0))
    return img


def bbox(text, pos):
    (w, h), base = cv2.getTextSize(text, FONT, SCALE, THICK)
    return (float(pos[0]), float(pos[0] + w), float(pos[1] - h), float(pos[1] + base))


def make_video(path, total=120):
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, HT))
    for i in range(total):
        out.write(frame(i))
    out.release()


def fake_samples(step, detected, total=120):
    """detected: {text: (bbox, first_seen_frame, last_seen_frame)} -> chi cac khung lay mau nam trong khoang do."""
    out = []
    for f in range(0, total, step):
        blocks = [dict(text=tx, bbox=bb, conf=0.9, row_h=bb[3] - bb[2])
                  for tx, (bb, a, b) in detected.items() if a <= f <= b]
        out.append((f / FPS, blocks))
    return out


def run(video, step, detected):
    tracks = H.build_tracks(fake_samples(step, detected), step / FPS)
    by = {tr.text(): tr for tr in tracks}
    n = H.refine_edges(video, tracks, FPS, step, W, HT)
    return by, n


def check(tr, start_f, end_f, step):
    s, e = tr.start * FPS, tr.end_t(step / FPS) * FPS
    assert abs(s - start_f) < 1e-6 and abs(e - end_f) < 1e-6, (tr.text(), s, e, "mong doi", start_f, end_f)


with tempfile.TemporaryDirectory() as d:
    video = os.path.join(d, "t.mp4")
    make_video(video)

    # 1) lay mau thua (fps 10 tren video 30fps, step=3): OCR thay A tu khung 12, B tu khung 72
    by, n = run(video, 3, {TEXT_A: (bbox(TEXT_A, POS_A), 12, 49), TEXT_B: (bbox(TEXT_B, POS_B), 72, B_LAST)})
    print("step=3 doi", n, "moc;", {k: (round(v.start * FPS), round(v.end_t(3 / FPS) * FPS)) for k, v in by.items()})
    assert by[TEXT_A].frames[0][0] * FPS == 12 and by[TEXT_B].frames[0][0] * FPS == 72   # truoc khi tinh chinh: tre
    check(by[TEXT_A], 10, 50, 3)           # A: chu hien o khung 10 (OCR tre 2 khung), tat sau khung 49
    check(by[TEXT_B], 70, 100, 3)          # B: tinh ca khung mo (70, 71); tat sau khung 99

    # 2) lay mau day du (step=1) nhung OCR bo sot 2 khung mo cua B (70, 71): van lui ve 70
    by, n = run(video, 1, {TEXT_A: (bbox(TEXT_A, POS_A), 10, 49), TEXT_B: (bbox(TEXT_B, POS_B), 72, B_LAST)})
    print("step=1 doi", n, "moc;", {k: (round(v.start * FPS), round(v.end_t(1 / FPS) * FPS)) for k, v in by.items()})
    check(by[TEXT_A], 10, 50, 1)           # da dung san: khong doi
    check(by[TEXT_B], 70, 100, 1)

    # 3) vung khong co chu (OCR sai): khong doi moc dau, khong loi
    by, n = run(video, 3, {"GHOST": ((300.0, 450.0, 20.0, 60.0), 30, 60)})
    tr = by["GHOST"]
    assert tr.refined_start is None, tr.refined_start

    # 4) tat tinh chinh bang cach khong goi refine_edges: moc van la khung OCR dau tien (hanh vi cu)
    tracks = H.build_tracks(fake_samples(3, {TEXT_A: (bbox(TEXT_A, POS_A), 12, 49)}), 3 / FPS)
    assert round(tracks[0].start * FPS) == 12 and round(tracks[0].end_t(3 / FPS) * FPS) == 51

print("OK")
