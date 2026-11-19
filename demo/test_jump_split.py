"""Chu phu NHAY sang cho khac -> tach block moi (khong de KF truot cham tu cho cu qua cho moi). Chi ap dung cho phu de phu."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H

step = 0.1
W, HT = 1440, 1080


def blk(text, box):
    x1, x2, y1, y2 = box
    return dict(text=text, conf=0.95, x_min=x1, x_max=x2, y_min=y1, y_max=y2, poly=None)


def samples(items, n):
    """items: list (text, k_dau, k_cuoi, ham k -> hop). Tra ve samples[(t, blocks)] cho k = 0..n-1."""
    out = []
    for k in range(n):
        bs = [blk(tx, box(k)) for tx, a, b, box in items if a <= k <= b]
        out.append((k * step, H.build_blocks(bs)))
    return out


def entries(out):
    """-> list (text, start_giay, so KF) tu chuoi .srtpx."""
    res = []
    for m in re.finditer(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> .*?\r\n(.*?)\r\nĐộ rộng.*?(?=\r\n\r\n|\Z)", out, re.S):
        h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
        res.append((m.group(5), h * 3600 + mi * 60 + s + ms / 1000, m.group(0).count("KF ")))
    return res


MAIN = (400, 900, 960, 1040)                                      # hang phu de chinh o duoi khung hinh
A, B = (200, 500, 100, 160), (900, 1200, 500, 560)                # 2 cho khac nhau cua chu phu
T1, T2, T3, T4 = "今天天气非常好啊", "我们一起去吃饭吧", "他昨天买了新手机", "这个问题很难回答"   # khac han nhau: khong bi tracker gop
main_items = [(T1, 0, 9, lambda k: MAIN), (T2, 10, 19, lambda k: MAIN), (T3, 20, 39, lambda k: MAIN)]


def track_all(items, n=40):
    return H.build_tracks(samples(items, n), step)


# 1) LOI CU: chu phu dung o A 2s roi nhay sang B -> khong tach thi chi co 2 KF cach nhau 2s = truot cham tu A qua B
jump = [("标题文字在这里", 0, 39, lambda k: A if k < 20 else B)]
tr = track_all(main_items + jump)
old = entries(H.format_srtpx(tr, W, HT, step))
kf_entry = next(e for e in old if e[0] == "标题文字在这里")
assert kf_entry[2] >= 2, old
times = [float(t) for t in re.findall(r"KF ([\d.]+)s:", H.format_srtpx(tr, W, HT, step))]
assert times[1] - times[0] >= 1.9, times                          # KF dau tai luc bat dau A, KF ke tai luc den B: noi suy ca 2s

# 2) SAU KHI TACH: 2 block dung yen, block sau bat dau dung luc chu hien o B, khong con KF
sp, n_cut = H.split_jumpy_tracks(tr, W, HT, step_sec=step)
assert n_cut == 1 and len(sp) == len(tr) + 1, (n_cut, len(sp), len(tr))
out = H.format_srtpx(sp, W, HT, step)
ents = [e for e in entries(out) if e[0] == "标题文字在这里"]
assert len(ents) == 2 and all(e[2] == 0 for e in ents), ents
assert abs(ents[0][1] - 0.0) < 0.11 and abs(ents[1][1] - 2.0) < 0.11, ents
boxes = re.findall(r"标题文字在这里\r\nĐộ rộng: (\d+)px - (\d+)px\r\nVị trí: (\d+)px - (\d+)px", out)
assert len(boxes) == 2
(ax1, ax2, ay1, ay2), (bx1, bx2, by1, by2) = (tuple(int(v) for v in b) for b in boxes)
assert abs(ax1 - A[0]) <= 6 and abs(bx1 - B[0]) <= 6 and abs(ay1 - A[2]) <= 6 and abs(by1 - B[2]) <= 6, boxes
# phu de chinh khong bi dong vao
assert [e[0] for e in entries(out) if e[0] in (T1, T2, T3)] == [e[0] for e in old if e[0] in (T1, T2, T3)] == [T1, T2, T3]

# 3) Chuyen dong THAT (truot cham) khong bi tach: van 1 block co KF
slide = [("标题文字在这里", 0, 39, lambda k: (200 + k * 18, 500 + k * 18, 100, 160))]   # 180px/s << 0,5 chieu cao khung hinh/s
sp, n_cut = H.split_jumpy_tracks(track_all(main_items + slide), W, HT, step_sec=step)
assert n_cut == 0, n_cut
assert [e for e in entries(H.format_srtpx(sp, W, HT, step)) if e[0] == "标题文字在这里"][0][2] >= 2

# 4) Nhieu OCR do lech 1 khung roi ve cho cu: khong tach
spike = [("标题文字在这里", 0, 39, lambda k: B if k == 20 else A)]
sp, n_cut = H.split_jumpy_tracks(track_all(main_items + spike), W, HT, step_sec=step)
assert n_cut == 0, n_cut

# 5) Nhay 2 lan (A -> B -> C): tach thanh 3 block
C = (100, 400, 800, 860)
two = [("标题文字在这里", 0, 59, lambda k: A if k < 20 else (B if k < 40 else C))]
sp, n_cut = H.split_jumpy_tracks(track_all(main_items + two, 60), W, HT, step_sec=step)
assert n_cut == 2, n_cut
assert [round(e[1], 1) for e in entries(H.format_srtpx(sp, W, HT, step)) if e[0] == "标题文字在这里"] == [0.0, 2.0, 4.0]

# 6) PHU DE CHINH duoc mien: cau thuoc nhom cung vi tri dong nhat co doi cho thi KHONG tach
main_jump = [(T4, 40, 79, lambda k: (100, 500, 960, 1040) if k < 60 else MAIN)]   # sau 3 cau kia: khong chong gio
tr6 = track_all(main_items + main_jump, 80)
assert len(H.main_lane_ids(tr6, W, HT)) == 4
assert H.split_jumpy_tracks(tr6, W, HT, step_sec=step)[1] == 0
# ... con cung kieu nhay do o cho khac (phu) thi tach (xem 2)

# 7) Khong co nhom chinh (chi 1 cau): moi cau deu coi la phu
tr7 = track_all(jump)
assert H.main_lane_ids(tr7, W, HT) == set()
assert H.split_jumpy_tracks(tr7, W, HT, step_sec=step)[1] == 1

# 8) --jump-rows 0 tat; chu doi cho cham (jump_speed cao) khong tach
assert H.split_jumpy_tracks(tr, W, HT, jump_rows=0, step_sec=step)[1] == 0
assert H.split_jumpy_tracks(tr, W, HT, jump_speed=1e6, step_sec=step)[1] == 0

print("OK")
