"""Hop den chi bao dung chu: khong gop nham khoi khac nhau (du lieu that: tieu de + phu de bi gop thanh hop 599px)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H


def box(text, x1, y1, x2, y2, conf=0.9):
    return dict(text=text, x_min=x1, x_max=x2, y_min=y1, y_max=y2, conf=conf)


def texts(boxes):
    return sorted(b["text"] for b in H.build_blocks(boxes))


# 1) cung hang, sat nhau -> gop
assert texts([box("今天天气", 100, 900, 400, 960), box("很好啊", 420, 902, 600, 962)]) == ["今天天气很好啊"]
# 2) tieu de tren cao + phu de duoi cung (cheo, xa nhau) -> KHONG gop
assert len(H.build_blocks([box("臀续试炼", 717, 636, 943, 823), box("什么还有考题", 437, 956, 978, 1057)])) == 2
# 3) 2 dong phu de xep chong, can giua, cao bang nhau -> gop thanh 1 cau 2 dong
bl = H.build_blocks([box("第一行字很长很长", 300, 900, 900, 960), box("第二行字", 400, 975, 800, 1035)])
assert len(bl) == 1 and bl[0]["bbox"] == (300, 900, 900, 1035), bl
# 4) chu thich * cung hang voi tieu de -> tach
assert len(H.build_blocks([box("各神答题belike", 409, 40, 900, 120), box("*老实做题", 930, 45, 1378, 125)])) == 2
# 5) chu lon + chu be sat nhau (cao lech > 35%) -> tach
assert len(H.build_blocks([box("大标题", 100, 100, 500, 200), box("小字说明", 100, 205, 300, 235)])) == 2
# 6) hop den khit chu: dem mac dinh 5% hoac toi thieu 2px
assert H.pad_box((100.0, 300.0, 400.0, 440.0), 40.0, 0.05, 640, 480) == (98.0, 302.0, 398.0, 442.0)
print("OK")
