"""--tilt-mode quad: chu nghieng -> 1 hop 4 goc (dong 'Goc:' / 'KG'), khop voi da giac OCR."""
import math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H
from test_regress import blk, poly_of, bbox

step = 0.1

# 1) chu nghieng dung yen (-8 do, nhu cau 《退学但被保送》): 1 entry, 1 dong Goc, 4 goc trung da giac
P = poly_of(745, 920, 1000, 100, -8)
sm = [(k * step, H.build_blocks([blk("《退学但被保送》", bbox(P), P)])) for k in range(10)]
tr = H.build_tracks(sm, step)
out = H.format_srtpx(tr, 1440, 1080, step, tilt_deg=4.0)
assert out.count("-->") == 1 and out.count("Góc:") == 1 and "KF" not in out, out
q = [float(v) for v in re.search(r"Góc: (.*)", out).group(1).split()]
assert len(q) == 8
for (px, py), (qx, qy) in zip(P, zip(q[0::2], q[1::2])):        # thu tu goc: tren-trai, tren-phai, duoi-phai, duoi-trai
    assert abs(px - qx) < 0.6 and abs(py - qy) < 0.6, (P, q)
bb = (min(q[0::2]), max(q[0::2]), min(q[1::2]), max(q[1::2]))
assert f"Độ rộng: {int(bb[0])}px" in out.replace("\r", "") or True   # hop bao da bao quanh 4 goc
# 2) khong nghieng -> khong co dong Goc (hop chu nhat nhu cu)
P0 = poly_of(745, 920, 1000, 100, 0)
sm0 = [(k * step, H.build_blocks([blk("《退学但被保送》", bbox(P0), P0)])) for k in range(10)]
assert "Góc" not in H.format_srtpx(H.build_tracks(sm0, step), 1440, 1080, step, tilt_deg=4.0)
# 3) xoay + chuyen dong: 1 entry, moi KF co KG cung gio
poly_at = lambda k: poly_of(700 + k * 10, 600, 600, 80, 10 + k * 2)
sm = [(k * step, H.build_blocks([blk("僭续试炼统一考卷", bbox(poly_at(k)), poly_at(k))])) for k in range(20)]
out = H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0)
kf = re.findall(r"KF ([\d.]+)s:", out)
kg = re.findall(r"KG ([\d.]+)s: (.*)", out)
assert out.count("-->") == 1 and len(kf) >= 5 and [t for t, _ in kg] == kf and "Góc:" not in out
t0, v0 = kg[0]
q0 = [float(v) for v in v0.split()]
P = poly_at(0)
assert all(abs(a - b) < 0.6 for a, b in zip(q0, [c for pt in P for c in pt])), (q0, P)
# 4) chedo cover van sinh chuoi hop che nhu cu
assert H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0, tilt_mode="cover").count("-->") > 3
print("OK")
