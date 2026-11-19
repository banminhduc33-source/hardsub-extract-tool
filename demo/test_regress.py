"""Hoi quy 3 loi: gop cau, chu doc bi cat doi, hop chu nhat chéo qua to (chu nghieng/xoay + chuyen dong, chu doc nghieng)."""
import math, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H

step = 0.1


def blk(text, box, poly=None):
    x1, x2, y1, y2 = box
    return dict(text=text, conf=0.95, x_min=x1, x_max=x2, y_min=y1, y_max=y2, poly=poly)


def poly_of(cx, cy, L, t, deg):
    a = math.radians(deg)
    ux, uy, vx, vy = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    return [(cx + s * L * ux + r * t * vx, cy + s * L * uy + r * t * vy) for s, r in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]]


def bbox(p):
    xs, ys = [q[0] for q in p], [q[1] for q in p]
    return (min(xs), max(xs), min(ys), max(ys))


def parse(out):
    """-> list entry: dict(text, main=(x1,x2,y1,y2), kf=[(t, box)]).  (cau khong chu co dong trong giua gio va 'Do rong')"""
    ls = out.split("\r\n")
    ents, i = [], 0
    while i < len(ls):
        if "-->" in ls[i]:
            j = i + 1
            while not ls[j].startswith("Độ rộng"):
                j += 1
            w = re.findall(r"(-?\d+)px - (-?\d+)px", ls[j] + ls[j + 1])
            kf, k = [], j + 2
            while k < len(ls) and ls[k].startswith("KF "):
                m = re.match(r"KF ([\d.]+)s: (-?\d+) (-?\d+) (-?\d+) (-?\d+)", ls[k])
                kf.append((float(m.group(1)), tuple(int(m.group(q)) for q in range(2, 6))))
                k += 1
            ents.append(dict(text=" ".join(l for l in ls[i + 1:j] if l), main=tuple(int(v) for v in w[0] + w[1]), kf=kf))
            i = k
        else:
            i += 1
    return ents


def inside(pt, b):
    return b[0] - 1 <= pt[0] <= b[1] + 1 and b[2] - 1 <= pt[1] <= b[3] + 1


# 1) GOP CAU: 2 cau lien tiep cung cho, giong ~80% -> 2 cau; nhay OCR 1 khung trong cung 1 cau -> van 1 cau
A, B = "这题出得有问题", "题目出得有问题啊"
sm = [(k * step, H.build_blocks([blk(A, (400, 900, 960, 1040))])) for k in range(10)] + \
     [(k * step, H.build_blocks([blk(B, (380, 920, 960, 1040))])) for k in range(10, 20)]
tr = H.build_tracks(sm, step)
assert [t.text() for t in tr] == [A, B], [t.text() for t in tr]
assert abs(tr[1].start - 1.0) < 0.21, tr[1].start
sm = [(k * step, H.build_blocks([blk(A if k != 5 else "这题出得有同题", (400, 900, 960, 1040))])) for k in range(20)]
assert len(H.build_tracks(sm, step)) == 1
# 1b) 2 cau o 2 cho khac nhau, giong ~70%, cung luc -> 2 track rieng (khong dinh nhau)
sm = [(k * step, H.build_blocks([blk(A, (400, 900, 960, 1040)), blk(B, (400, 900, 100, 180))])) for k in range(10)]
assert len(H.build_tracks(sm, step)) == 2

# 1c) cung 1 cau doc y het bi OCR mat 0.4s giua chung (hieu ung phong to) -> 1 cau, khong tach doi
C = "《退学但被保送》"
sm = [(k * step, H.build_blocks([blk(C, (225, 1265, 804, 1037))])) for k in range(0, 10)] + \
     [(k * step, H.build_blocks([blk(C, (228, 1268, 797, 1032))])) for k in range(14, 30)]
assert len(H.build_tracks(sm, step)) == 1
# nhung 2 cau KHAC nhau cach 0.4s van 2 cau
sm = [(k * step, H.build_blocks([blk(C, (225, 1265, 804, 1037))])) for k in range(0, 10)] + \
     [(k * step, H.build_blocks([blk("《留级但被劝退》", (228, 1268, 797, 1032))])) for k in range(14, 30)]
assert len(H.build_tracks(sm, step)) == 2

# 2) CHU DOC: 2 o cung cot -> 1 khoi theo thu tu tren->duoi; chu doc + chu ngang -> tach
bs = H.build_blocks([blk("试炼统一考卷", (1022, 1124, 665, 1235)), blk("僭续", (1022, 1124, 469, 659))])
assert len(bs) == 1 and bs[0]["text"] == "僭续试炼统一考卷" and bs[0]["bbox"] == (1022, 1124, 469, 1235), bs
assert len(H.build_blocks([blk("僭续试炼", (1022, 1124, 469, 900)), blk("什么还有考题", (400, 900, 956, 1057))])) == 2

# 3) CHU XOAY + CHUYEN DONG: hop bao ngoai phinh to -> hop chinh + hop con voi KF rieng, phu kin chu o MOI khung
poly_at = lambda k: poly_of(700 + k * 10, 600, 600, 80, 10 + k * 2)       # 10 -> 48 do
sm = [(k * step, H.build_blocks([blk("僭续试炼统一考卷", bbox(poly_at(k)), poly_at(k))])) for k in range(20)]
tr = H.build_tracks(sm, step)
off = parse(H.format_srtpx(tr, 1440, 1080, step, tilt_deg=0, tilt_mode="cover"))
on = parse(H.format_srtpx(tr, 1440, 1080, step, tilt_deg=4, tilt_mode="cover"))
assert len(off) == 1 and len(on) > 3 and on[0]["text"] == "僭续试炼统一考卷" and all(e["text"] == "" for e in on[1:]), len(on)
n_kf = len(on[0]["kf"])
assert n_kf >= 5 and all(len(e["kf"]) == n_kf for e in on)             # moi hop co cung moc KF
for k in range(0, 20, 3):
    t = k * step
    j = min(range(n_kf), key=lambda q: abs(on[0]["kf"][q][0] - t))     # KF gan nhat (KF moi khung hinh)
    boxes = [e["kf"][j][1] for e in on]
    P = poly_at(int(round(on[0]["kf"][j][0] / step)))
    cx, cy = sum(q[0] for q in P) / 4, sum(q[1] for q in P) / 4
    for s in [i / 16 - .5 for i in range(17)]:
        for r in (-0.4, 0, 0.4):
            a = P[1][0] - P[0][0], P[1][1] - P[0][1]
            b = P[3][0] - P[0][0], P[3][1] - P[0][1]
            pt = (cx + s * a[0] + r * b[0], cy + s * a[1] + r * b[1])
            assert any(inside(pt, bx) for bx in boxes), (k, pt)
def union_area(bs):
    xs = range(int(min(b[0] for b in bs)), int(max(b[1] for b in bs)), 4)
    ys = range(int(min(b[2] for b in bs)), int(max(b[3] for b in bs)), 4)
    return sum(1 for x in xs for y in ys if any(inside((x, y), b) for b in bs)) * 16
mid = n_kf // 2
ua = union_area([e["kf"][mid][1] for e in on])
ob = off[0]["kf"][mid][1]
assert ua < 0.7 * (ob[1] - ob[0]) * (ob[3] - ob[2]), (ua, ob)

# 4) CHU NGHIENG DUNG (steep 60 do) + OCR cat doi thanh 2 da giac: van hop nho, khong 1 hop bao ngoai
for deg in (-60, 60):
    P = poly_of(700, 600, 700, 80, deg)
    r = H.tilt_cover(P, 4.0)
    assert r is not None and len(r[1]) >= 8, (deg, r and len(r[1]))
    assert abs(math.degrees(math.atan2(P[1][1] - P[0][1], P[1][0] - P[0][0])) - deg) < 1e-6
P1, P2 = poly_of(500, 600, 400, 80, -10), poly_of(900, 580, 400, 80, -10)
m = H.tilt_cover_multi([P1, P2], 4.0)
assert m is not None and len(m[1]) >= 4
# canh ngan xep truoc (thu tu diem xoay): van nhan ra huong dong chu
Q = poly_of(700, 600, 700, 80, 60); Q = Q[1:] + Q[:1]
assert H.tilt_cover(Q, 4.0) is not None
# 5) chu thang / nghieng nhe: khong doi
assert H.tilt_cover(poly_of(700, 600, 700, 80, 2), 4.0) is None
print("OK")
