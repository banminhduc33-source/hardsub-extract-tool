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
assert "Đa giác" not in H.format_srtpx(H.build_tracks(sm0, step), 1440, 1080, step, tilt_deg=4.0, poly_secondary=False)
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


# ---- poly_secondary: moi phu de PHU deu la da giac, phu de chinh giu hop chu nhat
def entries(out):
    return out.split("\r\n\r\n")[1:]                 # phan tu dau la dong "#res WxH"


def corners(entry_text, tag="Đa giác"):
    m = re.search(tag + r": (.*)", entry_text)
    return [tuple(float(v) for v in p.split(",")) for p in m.group(1).split()]


# 5) poly_secondary mac dinh la True: cau thang cung ra 4 goc; tat di (False) thi chu thang van la hop chu nhat nhu cu
P0 = poly_of(745, 920, 1000, 100, 0)
sm0 = [(k * step, H.build_blocks([blk("《退学但被保送》", bbox(P0), P0)])) for k in range(10)]
tr0 = H.build_tracks(sm0, step)
assert "Đa giác" not in H.format_srtpx(tr0, 1440, 1080, step, tilt_deg=4.0, poly_secondary=False)
out = H.format_srtpx(tr0, 1440, 1080, step, tilt_deg=4.0)      # mac dinh = True
assert out.count("Đa giác:") == 1 and "KF" not in out, out
q = corners(out)
assert len(q) == 4
for (px, py), (qx, qy) in zip(P0, q):                  # chu thang: 4 goc = hop da siet (tren-trai, tren-phai, duoi-phai, duoi-trai)
    assert abs(px - qx) < 1.0 and abs(py - qy) < 1.0, (P0, q)

# 6) co nhom phu de chinh (3 cau cung hang) + 1 phu de phu o cho khac: chinh = hop chu nhat, phu = da giac
LANE = (400, 1040, 940, 1020)
main_txt = ["今天天气很好真不错", "我们一起去公园玩耍吧", "明天考试千万不能迟到"]
SEC = (900, 1000, 150, 400)
sm = []
for k in range(30):
    bl = [blk(main_txt[k // 10], LANE), blk("僭续试炼", SEC)]
    sm.append((k * step, H.build_blocks(bl)))
out = H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0, poly_secondary=True)
ents = entries(out)
by_text = {e.split("\r\n")[2]: e for e in ents}
assert set(by_text) >= set(main_txt) | {"僭续试炼"}, list(by_text)
for t in main_txt:
    assert "Đa giác" not in by_text[t] and "KP" not in by_text[t], by_text[t]      # phu de chinh: hop chu nhat nhu cu
assert by_text["僭续试炼"].count("Đa giác:") == 1, by_text["僭续试炼"]            # phu de phu: da giac
assert H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0, poly_secondary=False).count("Đa giác") == 0
assert H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0).count("Đa giác:") >= 1   # mac dinh: phu de phu la da giac

# 7) the bay + xoay (cot chu doc ~ 90 do, qua moc 45 do) nhu cau "继续试炼" o video Belike: moi KF mot dong KP, khong khung nao
#    bi loai, khung khong co da giac van duoc 4 goc hop, va thu tu goc lien tuc (khong bi xoan khi canh ngan/dai doi vai tro)
def card_poly(k):
    return poly_of(650 + k * 8, 700 - k * 4, 250, 75, 30 + k * 3)       # 30 -> 87 do: qua 45 do giua chung

blocks_at = lambda k: ([blk("继续试炼", bbox(card_poly(k)), card_poly(k))] if k % 7 != 3     # vai khung OCR mat da giac
                       else [blk("继续试炼", bbox(card_poly(k)), None)])
sm = [(k * step, H.build_blocks(blocks_at(k))) for k in range(20)]
out = H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=4.0, poly_secondary=True)
ents = entries(out)
assert len(ents) == 1, out
kf = re.findall(r"KF ([\d.]+)s:", ents[0])
kp = re.findall(r"KP ([\d.]+)s: (.*)", ents[0])
assert len(kf) >= 5 and [t for t, _ in kp] == kf and "Đa giác:" not in ents[0], ents[0]
qs = [[tuple(float(v) for v in p.split(",")) for p in s.split()] for _, s in kp]
assert all(len(x) == 4 for x in qs)
for a, b in zip(qs, qs[1:]):
    worst = max(math.hypot(p[0] - r[0], p[1] - r[1]) for p, r in zip(a, b))
    assert worst < 60, ("hop bi xoan giua 2 keyframe", worst, a, b)      # khong nhan goc thi nhay ~ 100+ px o moc 45 do

# 8) khong co khung nao co da giac (tesseract) van ra da giac tu hop; --tilt 0 van cho phep (poly_secondary doc lap)
sm = [(k * step, H.build_blocks([blk("僭续试炼统一考卷", bbox(poly_of(700 + k * 10, 600, 600, 80, 0)))])) for k in range(20)]
out = H.format_srtpx(H.build_tracks(sm, step), 1440, 1080, step, tilt_deg=0.0, poly_secondary=True)
kf = re.findall(r"KF ([\d.]+)s:", out)
kp = re.findall(r"KP ([\d.]+)s:", out)
assert len(kf) >= 5 and kp == kf, out
print("OK")
