"""--tilt-mode quad: chu nghieng -> 1 hop 4 goc (dong 'Goc:' / 'KG'), khop voi da giac OCR."""
import math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H
from test_regress import blk, poly_of, bbox

step = 0.1

# 1) chu nghieng dung yen (-8 do, nhu cau 《退学但被保送》): 1 entry, 1 dong Da giac, 4 goc trung da giac OCR
P = poly_of(745, 920, 1000, 100, -8)
sm = [(k * step, H.build_blocks([blk("《退学但被保送》", bbox(P), P)])) for k in range(10)]
tr = H.build_tracks(sm, step)
out = H.format_srtpx(tr, 1440, 1080, step, tilt_deg=4.0)
assert out.count("-->") == 1 and out.count("Đa giác:") == 1 and "KF" not in out, out
pts = [tuple(float(v) for v in p.split(",")) for p in re.search(r"Đa giác: (.*)", out).group(1).split()]
assert len(pts) == 4
for (px, py), (qx, qy) in zip(P, pts):               # thu tu goc: tren-trai, tren-phai, duoi-phai, duoi-trai
    assert abs(px - qx) < 0.6 and abs(py - qy) < 0.6, (P, pts)
# 2) khong nghieng -> khong co dong Da giac (hop chu nhat nhu cu)
P0 = poly_of(745, 920, 1000, 100, 0)
sm0 = [(k * step, H.build_blocks([blk("《退学但被保送》", bbox(P0), P0)])) for k in range(10)]
assert "Đa giác" not in H.format_srtpx(H.build_tracks(sm0, step), 1440, 1080, step, tilt_deg=4.0)
# 3) xoay + chuyen dong: 1 entry, moi KF co 1 dong KP cung gio, 4 goc trung da giac OCR tung khung
poly_at = lambda k: poly_of(700 + k * 10, 600, 600, 80, 10 + k * 2)
sm = [(k * step, H.build_blocks([blk("僭续试炼统一考卷", bbox(poly_at(k)), poly_at(k))])) for k in range(20)]
out = H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0)
kf = re.findall(r"KF ([\d.]+)s:", out)
kp = re.findall(r"KP ([\d.]+)s: (.*)", out)
assert out.count("-->") == 1 and len(kf) >= 5 and [t for t, _ in kp] == kf and "Đa giác:" not in out
P = poly_at(0)
q0 = [tuple(float(v) for v in p.split(",")) for p in kp[0][1].split()]
assert all(abs(a - b) < 0.6 for (a, b2), (c, d) in zip(q0, P) for a, b in ((a, c), (b2, d))), (q0, P)
# 4) che do cover: chu nghieng dung yen cung ra chuoi hop che
assert H.format_srtpx(tr, 1440, 1080, step, tilt_deg=4.0, tilt_mode="cover").count("-->") > 3
print("OK")
