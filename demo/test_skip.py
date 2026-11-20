"""Bo qua khung khong doi (FrameSkipper) + tham so Paddle (det_side / use_cls)."""
import os, sys, tempfile, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2
import numpy as np
import hardsub_extract as H

W, HH = 1440, 1080
rng = np.random.default_rng(1)


def base():
    img = np.full((HH, W, 3), 60, np.uint8)
    cv2.rectangle(img, (0, 700), (W, HH), (90, 70, 50), -1)          # mot it nen co cau truc
    return img


def with_text(img, x=300, y=200, w=76, h=38, v=255):
    out = img.copy()
    cv2.rectangle(out, (x, y), (x + w, y + h), (v, v, v), -1)          # ~2 chu: ~0,19% dien tich khung hinh
    return out


# 1) khung giong het: khung dau OCR, 8 khung ke tiep bo qua, roi bat buoc OCR lai (max_skip), lap lai
sk = H.FrameSkipper(0.05, 8)
seq = [sk.should_skip(base()) for _ in range(20)]
assert seq == [False] + [True] * 8 + [False] + [True] * 8 + [False, True], seq
assert sk.skipped == 17 and sk.total == 20

# 2) nhieu nen + dao dong do sang nhe -> van coi la khong doi
sk = H.FrameSkipper(0.05, 8)
b = base()
sk.should_skip(b)
for _ in range(5):
    noisy = np.clip(b.astype(np.int16) + rng.normal(0, 3, b.shape) + rng.integers(-2, 3), 0, 255).astype(np.uint8)
    assert sk.should_skip(noisy), "nhieu nen nhe bi coi la thay doi"

# 3) chu moi hien (2 chu, ~0,19% khung) -> KHONG duoc bo qua; chu bien mat cung vay
sk = H.FrameSkipper(0.05, 8)
sk.should_skip(base())
assert sk.should_skip(base())
assert not sk.should_skip(with_text(base())), "chu moi hien bi bo qua"
assert sk.should_skip(with_text(base()))                              # chu dung yen sau do: bo qua
assert not sk.should_skip(base()), "chu bien mat bi bo qua"

# 4) chu mo dan (thay doi tu tu): so voi khung OCR gan nhat nen cong don, khong bi bo qua het
sk = H.FrameSkipper(0.05, 30)
sk.should_skip(base())
res = [sk.should_skip(with_text(base(), v=60 + 19 * k)) for k in range(1, 11)]        # 79 .. 250
assert not all(res) and res[-1] is False, res

# 5) nen dong lon (10% khung hinh doi) -> khong bo qua; max_skip=0 -> khong bao gio bo qua
sk = H.FrameSkipper(0.05, 8)
sk.should_skip(base())
moved = base(); moved[100:400, 100:600] = 200
assert not sk.should_skip(moved)
sk0 = H.FrameSkipper(0.05, 0)
assert [sk0.should_skip(base()) for _ in range(5)] == [False] * 5

# 6) tham so Paddle: det_side / use_cls di vao PaddleOCR va cls cua .ocr(); mac dinh cua lop giu nhu PaddleOCR goc
calls = {}


class FakePaddle:
    def __init__(self, **kw):
        calls["init"] = kw

    def ocr(self, img, cls=True):
        calls["cls"] = cls
        return [None]


sys.modules["paddleocr"] = types.SimpleNamespace(PaddleOCR=FakePaddle)
e = H.OcrEngine("paddleocr", lang="ch", det_side=640, use_cls=False)
assert calls["init"]["det_limit_side_len"] == 640 and calls["init"]["use_angle_cls"] is False, calls
assert calls["init"]["enable_mkldnn"] is False and calls["init"]["ir_optim"] is False      # che do an toan van giu
assert e.detect(np.zeros((50, 50, 3), np.uint8)) == [] and calls["cls"] is False
H.OcrEngine("paddleocr", lang="ch")
assert calls["init"]["det_limit_side_len"] == 960 and calls["init"]["use_angle_cls"] is True

# 7) chay main() het cau: bo qua cho ra file GIONG HET khi tat bo qua, nhung it lan OCR hon
tmp = tempfile.mkdtemp()
vid = os.path.join(tmp, "v.mp4")
vw = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
bg = np.full((360, 640, 3), 40, np.uint8)
def txt(n):
    f = bg.copy(); cv2.putText(f, n, (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3, cv2.LINE_AA); return f
for _ in range(20): vw.write(txt("AB"))
for _ in range(6): vw.write(bg)
for _ in range(20): vw.write(txt("ABCDEFGHIJ"))
for _ in range(6): vw.write(bg)
vw.release()


class FakeOcr:
    n_calls = 0

    def __init__(self, **kw):
        pass

    def detect(self, img):
        FakeOcr.n_calls += 1
        ys, xs = np.where(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > 200)
        if len(xs) < 30:
            return []
        w = xs.max() - xs.min()
        text = "你好世界" if w < 200 else "再见朋友们"
        return [dict(text=text, conf=0.95, x_min=float(xs.min()), x_max=float(xs.max()) + 1,
                     y_min=float(ys.min()), y_max=float(ys.max()) + 1)]


H.OcrEngine = FakeOcr
outs = {}
for name, extra in (("skip", []), ("noskip", ["--no-skip"])):
    FakeOcr.n_calls = 0
    out = os.path.join(tmp, name + ".srtpx")
    sys.argv = ["hardsub_extract.py", vid, "-o", out, "--engine", "paddleocr", "--fps", "30", "--scale", "1",
                "--min-height", "0", "--pad", "0", "--no-refine"] + extra
    H.main()
    outs[name] = (open(out, "rb").read(), FakeOcr.n_calls)
assert outs["skip"][0] == outs["noskip"][0], (outs["skip"][0], outs["noskip"][0])
assert outs["noskip"][1] == 52 and outs["skip"][1] < 0.6 * 52, (outs["skip"][1], outs["noskip"][1])
assert outs["skip"][0].count(b"-->") == 2
print("OK", outs["skip"][1], "/", outs["noskip"][1], "lan OCR")
