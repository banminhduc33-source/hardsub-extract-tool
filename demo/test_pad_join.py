"""Kiem tra dem vien hop (--pad) va noi moc thoi gian (--join-gap)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import hardsub_extract as H

step = 1 / 30


def samples_for(items, total):
    """items: (t0, t1, text, bbox, row_h). Moi khung moi cau 1 block."""
    out = []
    for k in range(total):
        t = k / 30
        blocks = [dict(text=tx, bbox=bb, conf=0.9, row_h=rh)
                  for (a, b, tx, bb, rh) in items if a <= t < b]
        out.append((t, blocks))
    return out


def parse(out):
    ents = []
    for e in out.split("\r\n\r\n")[1:]:
        L = e.split("\r\n")
        ents.append(L)
    return ents


# A: 0.0-1.0 ; B: 1.2-2.0 (gap 0.2, cung lan) ; C: 3.0-4.0 (gap 1.0) ; D: bang to 0.5-3.5 o cho khac
items = [
    (0.0, 1.0, "AAAAAA", (100.0, 300.0, 400.0, 440.0), 40.0),
    (1.2, 2.0, "BBBBBB", (110.0, 290.0, 402.0, 442.0), 40.0),
    (3.0, 4.0, "CCCCCC", (100.0, 300.0, 400.0, 440.0), 40.0),
    (0.5, 3.5, "DDDDDD", (50.0, 200.0, 50.0, 250.0), 40.0),
]
tr = H.build_tracks(samples_for(items, 130), step)
out = H.format_srtpx(tr, 640, 480, step, pad_ratio=0.25, join_gap=0.3)
ents = parse(out)
by = {e[2]: e for e in ents}
print("\n".join(out.split("\r\n")))

# 1) noi duoi A -> dau B (gap 0.2 <= 0.3, cung lan)
assert by["AAAAAA"][1].split(" --> ")[1] == by["BBBBBB"][1].split(" --> ")[0], by["AAAAAA"][1]
# 2) B -> C cach 1.0s: khong noi
assert by["BBBBBB"][1].split(" --> ")[1] != by["CCCCCC"][1].split(" --> ")[0]
# 3) bang to D (lan khac) khong bi keo dai
assert by["DDDDDD"][1].endswith("00:00:03,500") or by["DDDDDD"][1].split(" --> ")[1] == "00:00:03,500", by["DDDDDD"][1]
# 4) dem vien: A tinh, row_h 40 * 0.25 = 10px moi phia
assert by["AAAAAA"][3] == "Độ rộng: 90px - 310px", by["AAAAAA"][3]
assert by["AAAAAA"][4] == "Vị trí: 390px - 450px", by["AAAAAA"][4]
# 5) tat ca = giu nguyen
off = parse(H.format_srtpx(tr, 640, 480, step))
b0 = {e[2]: e for e in off}
assert b0["AAAAAA"][3] == "Độ rộng: 100px - 300px" and b0["AAAAAA"][1] != by["AAAAAA"][1]
# 6) kep trong khung hinh
tr2 = H.build_tracks(samples_for([(0, 1.0, "EEEEEE", (2.0, 100.0, 1.0, 30.0), 28.0)], 30), step)
e2 = parse(H.format_srtpx(tr2, 640, 480, step, pad_ratio=0.25))[0]
assert e2[3].startswith("Độ rộng: 0px"), e2[3]
assert e2[4].startswith("Vị trí: 0px"), e2[4]
print("OK")
