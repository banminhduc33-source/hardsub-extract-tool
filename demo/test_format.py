"""Kiem tra: dung du lieu cua file mau demo/testvn.srtpx de dung lai cac khung hinh gia lap,
chay qua bo theo doi + bo ghi file cua tool, ket qua phai GIONG HET (tung byte) file mau."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import hardsub_extract as H

ref = open(os.path.join(HERE, "testvn.srtpx"), "rb").read().decode("utf-8")
w, h = map(int, re.match(r"#res (\d+)x(\d+)", ref).groups())
step = 1 / 30

def ts2s(x):
    hh, mm, rest = x.split(":"); ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000

frames = {}
for e in ref.split("\r\n\r\n")[1:]:
    L = e.split("\r\n")
    a, b = L[1].split(" --> "); st, en = ts2s(a), ts2s(b)
    nums = lambda s: list(map(int, re.findall(r"-?\d+", s.split(":", 1)[1])))
    wx, py = nums(L[3]), nums(L[4])
    main = (wx[0], wx[1], py[0], py[1])
    kfs = []
    for l in L[5:]:
        m = re.match(r"KF ([\d.]+)s: (-?\d+) (-?\d+) (-?\d+) (-?\d+)", l)
        kfs.append((float(m.group(1)), tuple(map(int, m.groups()[1:]))))
    n0, n1 = round(st * 30), round(en * 30)
    for k in range(n0, n1):
        t, box = k / 30, main
        if kfs:
            box = kfs[0][1]
            for kt, kb in kfs:
                if t >= kt - 0.02:
                    box = kb
            if k == n1 - 1:
                box = kfs[-1][1]
        frames.setdefault(k, []).append(dict(text=L[2], bbox=tuple(float(v) for v in box), conf=0.9))

samples = [(k / 30, frames.get(k, [])) for k in range(max(frames) + 1)]
tracks = H.build_tracks(samples, step)
out = H.format_srtpx(tracks, w, h, step, poly_secondary=False)   # file mau cu chi co hop chu nhat
print("GIONG HET file mau:", out == ref)
sys.exit(0 if out == ref else 1)
