"""--workers: chia video thanh cac doan, quet song song (fork va spawn), ghep truoc buoc gom cau.
Ket qua phai GIONG HET quet mot mach."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import cv2
import numpy as np
import hardsub_extract as H


class FakeOcr:
    """OCR gia: tim vung chu trang -> 1 o chu; noi dung doc theo chieu rong (de 2 cau co chu khac nhau)."""
    def __init__(self, **kw):
        pass

    def detect(self, img):
        ys, xs = np.where(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > 200)
        if len(xs) < 30:
            return []
        w = xs.max() - xs.min()
        text = "你好世界" if w < 200 else "再见朋友们"
        return [dict(text=text, conf=0.95, x_min=float(xs.min()), x_max=float(xs.max()) + 1,
                     y_min=float(ys.min()), y_max=float(ys.max()) + 1)]


H.OcrEngine = FakeOcr          # o muc module: tien trinh con (spawn nap lai file nay) cung thay ban OCR gia


def make_video(path):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    bg = np.full((360, 640, 3), 40, np.uint8)

    def txt(s):
        f = bg.copy()
        cv2.putText(f, s, (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3, cv2.LINE_AA)
        return f
    for i in range(300):
        if 10 <= i < 190:
            vw.write(txt("AB"))                       # cau 1: nam vat qua nhieu moc cat doan
        elif 230 <= i < 290:
            vw.write(txt("ABCDEFGHIJ"))               # cau 2
        else:
            vw.write(bg)
    vw.release()


def run(vid, out, *extra):
    sys.argv = ["hardsub_extract.py", vid, "-o", out, "--engine", "paddleocr", "--fps", "30", "--scale", "1",
                "--min-height", "0", "--pad", "0", "--no-refine"] + list(extra)
    H.main()
    return open(out, "rb").read()


if __name__ == "__main__":
    # 1) split_segments: lien tiep, boi so cua step, phu het, doan cuoi doc den het video
    for n, k, step in ((300, 6, 1), (301, 5, 3), (100, 2, 2), (97, 7, 5)):
        segs = H.split_segments(n, k, step)
        assert len(segs) == k and segs[0][0] == 0 and segs[-1][1] is None, segs
        for (a, b), (c, d) in zip(segs, segs[1:]):
            assert b == c and a < b and a % step == 0 and b % step == 0, segs
        assert segs[-1][0] < n * step

    tmp = tempfile.mkdtemp()
    vid = os.path.join(tmp, "v.mp4")
    make_video(vid)
    info = H.video_info(vid, 30)
    assert info["frames"] == 300 and info["step"] == 1, info

    # 2) quet theo doan = quet mot mach: cung chi so mau, moc thoi gian, noi dung khung
    full = [(k, t, float(f.mean())) for k, t, f in H.iter_sampled(vid, 30)]
    assert [k for k, _, _ in full] == list(range(300))
    parts = []
    for a, b in H.split_segments(300, 4, 1):
        parts += [(k, t, float(f.mean())) for k, t, f in H.iter_sampled(vid, 30, a, b)]
    assert parts == full, "quet theo doan khac quet mot mach"
    full3 = [(k, t) for k, t, _ in H.iter_sampled(vid, 10)]                    # fps 10 tren video 30fps: step 3
    assert [k for k, _ in full3] == list(range(100)) and abs(full3[1][1] - 0.1) < 1e-9
    parts3 = []
    for a, b in H.split_segments(100, 3, 3):
        parts3 += [(k, t) for k, t, _ in H.iter_sampled(vid, 10, a, b)]
    assert parts3 == full3

    # 3) khong biet so khung / video qua ngan -> khong chia (tra None)
    assert H.scan_parallel(vid, 30, dict(info, frames=0), 4, {}) is None
    assert H.scan_parallel(vid, 30, dict(info, frames=40), 4, {}) is None
    assert H.scan_parallel(vid, 30, info, 1, {}) is None

    # 4) main() that su song song (fork roi spawn): file giong het mot mach, cau nam qua nhieu doan van la 1 cau
    base = run(vid, os.path.join(tmp, "one.srtpx"), "--no-skip")
    assert base.count(b"-->") == 2, base
    for mode in ("fork", "spawn"):
        os.environ["HARDSUB_MP_START"] = mode
        for extra in (["--no-skip"], []):
            ref = base if extra else run(vid, os.path.join(tmp, "one_skip.srtpx"))
            out = run(vid, os.path.join(tmp, f"{mode}.srtpx"), "--workers", "2", *extra)
            assert out == ref, (mode, extra, out, ref)
            assert out.count(b"-->") == 2
    print("OK")
