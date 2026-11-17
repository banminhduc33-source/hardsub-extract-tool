"""Chi boc chu to, ro: bo chu li ti (bang/UI) va khoi qua ngan."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardsub_extract as H


class Fake:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, img):
        return self.boxes


def box(text, x1, y1, x2, y2, conf=0.9):
    return dict(text=text, x_min=x1, x_max=x2, y_min=y1, y_max=y2, conf=conf)


# khung 576 cao, scale 1: phu de cao 38px, chu bang cao 10px, 1 chu le
eng = Fake([box("今天天气很好", 100, 400, 500, 438),
            box("装备强化材料", 20, 100, 90, 110),
            box("好", 300, 200, 340, 240)])
out = H.detect_frame_blocks(eng, None, (0, 0), 1.0, True, min_h=0.035 * 576, min_chars=2)
assert [b["text"] for b in out] == ["今天天气很好"], out
# tat bo loc -> lay het (hanh vi cu)
out0 = H.detect_frame_blocks(eng, None, (0, 0), 1.0, True)
assert len(out0) == 3, out0
print("OK")
