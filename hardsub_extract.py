#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hardsub_extract.py
===================

Boc hardsub (chu cung) tieng Trung tu video ra file .srtpx.

DINH DANG .srtpx (theo file mau testvn.srtpx):
    #res 768x576                      <- dong dau: do phan giai video
    <dong trong>
    1
    00:00:00,267 --> 00:00:09,467     <- start .. end (end = luc cau bien mat)
    Noi dung chu
    Do rong: 252px - 520px            <- khung chu o trang thai on dinh (x1 - x2)
    Vi tri: 46px - 80px               <- (y1 - y2)
    KF 0.27s: 217 555 -21 18          <- (chi co khi khung chu chuyen dong)
    KF 1.00s: 252 520 46 80              moi dong KF = "thoi gian: x1 x2 y1 y2"
    KF 9.47s: 252 520 46 80
    <dong trong>
    2
    ...
  File dung xuong dong CRLF (\r\n), UTF-8 khong BOM, khong co dong trong o cuoi.
  ("Do rong" / "Vi tri" trong file that viet co dau: "Độ rộng" / "Vị trí")

NGUYEN LY:
  1. Doc video, lay mau khung hinh theo --fps.
  2. OCR trong vung --roi de tim CHU nam o dau + noi dung.
  3. Gom cac o chu gan nhau thanh "khoi" (1 cau), bo chu khong phai chu Han
     (so, logo...) de khong dinh nhieu.
  4. Theo doi tung khoi qua cac khung hinh (cac khung giong nhau = cung 1 cau),
     nhieu cau co the cung hien 1 luc o cac vi tri khac nhau.
  5. Neu khung chu chuyen dong (hieu ung) thi ghi cac dong KF.

CAI DAT:  pip install opencv-python-headless numpy pillow paddleocr paddlepaddle
VI DU:
  python3 hardsub_extract.py video.mp4 -o ketqua.srtpx --engine paddleocr --lang ch --fps 30
"""

import argparse
import math
import collections
import difflib
import os
import statistics
import sys

import cv2
import numpy as np


# --------------------------------------------------------------------------
# 1) DOC VIDEO
# --------------------------------------------------------------------------

def video_info(video_path, target_fps):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được video: {video_path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    sample_fps = min(target_fps, native_fps) if target_fps else native_fps
    step = max(1, round(native_fps / sample_fps))
    return dict(width=w, height=h, native_fps=native_fps, step=step, step_sec=step / native_fps)


def iter_frames(video_path, target_fps):
    """Sinh (thoi_gian_giay, frame_BGR) theo target_fps; thoi gian tinh theo FPS goc."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được video: {video_path}")
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    sample_fps = min(target_fps, native_fps) if target_fps else native_fps
    step = max(1, round(native_fps / sample_fps))
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step == 0:
            yield frame_idx / native_fps, frame
        frame_idx += 1
    cap.release()


def seconds_to_srt_ts(t):
    if t < 0:
        t = 0
    ms_total = round(t * 1000)
    h, rem = divmod(ms_total, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------------------------------------------------------
# 2) OCR
# --------------------------------------------------------------------------

def _force_paddle_no_ir(config_cls=None):
    """Ep Paddle Inference KHONG chay cac pass toi uu IR (SelfAttentionFusePass... gay SIGILL / exit 132 tren CPU
    runner thieu AVX).  paddleocr 2.7.x tu goi config.switch_ir_optim(True) trong create_predictor nen tham so
    ir_optim=False cua PaddleOCR bi bo qua -> vo hieu hoa o cap Config.  config_cls chi de test."""
    try:
        if config_cls is None:
            from paddle import inference
            config_cls = inference.Config
        if getattr(config_cls, "_hardsub_no_ir", False):
            return True
        orig = config_cls.switch_ir_optim

        def switch_ir_optim(self, x=True):
            return orig(self, False)

        config_cls.switch_ir_optim = switch_ir_optim
        config_cls._hardsub_no_ir = True
        return True
    except Exception as e:                      # khong chan chay neu ban Paddle khac
        print(f"Canh bao: khong tat duoc IR optim cua Paddle ({e})", file=sys.stderr)
        return False


class OcrEngine:
    """Lớp bọc chung cho 3 backend: tesseract / easyocr / paddleocr.

    detect(img_bgr) -> list[dict(text, x_min, y_min, x_max, y_max, conf)]
    toạ độ trả về theo đúng hệ toạ độ của img_bgr truyền vào (ảnh đã
    crop ROI và có thể đã phóng to theo `scale`).
    """

    def __init__(self, engine="tesseract", lang="chi_sim", min_conf=0.4):
        self.engine = engine
        self.lang = lang
        self.min_conf = min_conf
        self._backend = None

        if engine == "paddleocr":
            _force_paddle_no_ir()
            from paddleocr import PaddleOCR  # lazy import
            # CPU cua runner GitHub co the thieu tap lenh (AVX/oneDNN) ma cac pass
            # toi uu cua Paddle Inference dung -> SIGILL (exit 132) trong
            # SelfAttentionFusePass. Tat ir_optim + mkldnn de chay an toan.
            self._backend = PaddleOCR(
                use_angle_cls=True, lang=lang, show_log=False,
                use_gpu=False, enable_mkldnn=False, ir_optim=False,
            )
        elif engine == "easyocr":
            import easyocr  # lazy import
            langs = [lang] if isinstance(lang, str) else lang
            self._backend = easyocr.Reader(langs, gpu=False)
        elif engine == "tesseract":
            import pytesseract  # lazy import
            self._backend = pytesseract
        else:
            raise ValueError(f"Engine không hỗ trợ: {engine}")

    def detect(self, img_bgr):
        if self.engine == "paddleocr":
            return self._detect_paddle(img_bgr)
        if self.engine == "easyocr":
            return self._detect_easyocr(img_bgr)
        return self._detect_tesseract(img_bgr)

    def _detect_paddle(self, img_bgr):
        out = []
        result = self._backend.ocr(img_bgr, cls=True)
        if not result or result[0] is None:
            return out
        for box, (text, conf) in result[0]:
            if conf < self.min_conf or not text.strip():
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(dict(text=text.strip(), x_min=min(xs), x_max=max(xs),
                             y_min=min(ys), y_max=max(ys), conf=conf,
                             poly=[(float(q[0]), float(q[1])) for q in box]))
        return out

    def _detect_easyocr(self, img_bgr):
        out = []
        for box, text, conf in self._backend.readtext(img_bgr):
            if conf < self.min_conf or not text.strip():
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(dict(text=text.strip(), x_min=min(xs), x_max=max(xs),
                             y_min=min(ys), y_max=max(ys), conf=conf,
                             poly=[(float(q[0]), float(q[1])) for q in box]))
        return out

    def _detect_tesseract(self, img_bgr):
        from pytesseract import Output
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        data = self._backend.image_to_data(rgb, lang=self.lang, output_type=Output.DICT)
        # Gom theo (block_num, par_num, line_num) thành từng "dòng chữ"
        lines = collections.defaultdict(list)
        n = len(data["text"])
        for i in range(n):
            txt = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not txt or conf < 0:
                continue
            if conf / 100.0 < self.min_conf:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            lines[key].append((txt, x, y, x + w, y + h, conf / 100.0))

        out = []
        for key, words in lines.items():
            words.sort(key=lambda w: w[1])
            text = "".join(w[0] for w in words) if self.lang.startswith("chi") else " ".join(w[0] for w in words)
            x_min = min(w[1] for w in words)
            y_min = min(w[2] for w in words)
            x_max = max(w[3] for w in words)
            y_max = max(w[4] for w in words)
            conf = statistics.mean(w[5] for w in words)
            out.append(dict(text=text, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max, conf=conf))
        return out


def _is_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in s)


def _join_text(group):
    """Noi chu cua 1 khoi: theo hang (tren->duoi), trong hang (trai->phai).
    Khoi chu doc: theo cot (phai->trai), trong cot (tren->duoi)."""
    if all(_is_vertical(b) for b in group):
        cols = []
        for b in sorted(group, key=lambda b: -(b["x_min"] + b["x_max"]) / 2):
            cx, w = (b["x_min"] + b["x_max"]) / 2, b["x_max"] - b["x_min"]
            if cols and abs(cx - cols[-1]["cx"]) <= 0.6 * max(w, cols[-1]["w"]):
                cols[-1]["items"].append(b)
            else:
                cols.append(dict(cx=cx, w=w, items=[b]))
        return "".join("".join(b["text"] for b in sorted(c["items"], key=lambda b: b["y_min"])) for c in cols)
    group = sorted(group, key=lambda b: (b["y_min"] + b["y_max"]) / 2)
    rows = []
    for b in group:
        cy = (b["y_min"] + b["y_max"]) / 2
        h = b["y_max"] - b["y_min"]
        if rows and abs(cy - rows[-1]["cy"]) <= 0.6 * max(h, rows[-1]["h"]):
            rows[-1]["items"].append(b)
        else:
            rows.append(dict(cy=cy, h=h, items=[b]))
    parts = []
    for r in rows:
        items = sorted(r["items"], key=lambda b: b["x_min"])
        sep = "" if any(_is_cjk(b["text"]) for b in items) else " "
        parts.append(sep.join(b["text"] for b in items))
    return " ".join(parts)


MARKERS = "*＊#＃※★☆†‡✱✲⁎"


def _is_vertical(b):
    """O chu doc (chu Han xep tu tren xuong, vd tieu de tren to giay xoay 90 do): cao >= 1.5 x rong, tu 2 chu tro len."""
    w, h = b["x_max"] - b["x_min"], b["y_max"] - b["y_min"]
    return _is_cjk(b["text"]) and len(b["text"]) >= 2 and h >= 1.5 * w


def _transpose(b):
    """Doi cho x <-> y de dung lai luat gop theo hang cho chu doc."""
    t = dict(b)
    t["x_min"], t["x_max"], t["y_min"], t["y_max"] = b["y_min"], b["y_max"], b["x_min"], b["x_max"]
    return t


def _thickness(b):
    """Be day 1 dong chu: chieu cao voi chu ngang, chieu rong voi chu doc."""
    return (b["x_max"] - b["x_min"]) if _is_vertical(b) else (b["y_max"] - b["y_min"])


def _should_merge(a, b):
    """2 o chu co thuoc CUNG 1 cau khong. Chat de hop den chi bao dung chu, khong gop nham 2 khoi khac nhau:
      - cung hang: chong nhau theo chieu doc >= 50% va cach nhau theo chieu ngang <= 1.0 x chieu cao chu;
      - xuong dong: hang duoi sat hang tren (cach <= 0.35 x chieu cao chu) va 2 hang chong nhau theo chieu ngang;
      - 2 o phai cao gan bang nhau (>= 65%); 1 o bat dau bang dau chu thich (* # ...) con o kia thi khong -> tach.
    Khong gop cheo (lech ca hai chieu) nhu truoc.
    Chu doc: 2 o cung doc thi dung y het luat tren sau khi doi x <-> y (cung COT; o ngan + o dai trong 1 cot
    van gop vi chi so be day cot, khong so do dai); 1 o doc + 1 o ngang -> tach."""
    va, vb = _is_vertical(a), _is_vertical(b)
    if va != vb:
        return False
    if va:
        a, b = _transpose(a), _transpose(b)     # sau khi doi truc, "chieu cao" = be day cot, "hang" = cot
    return _should_merge_h(a, b)


def _should_merge_h(a, b):
    """Luat gop cho chu ngang (chu doc goi sau khi doi truc x <-> y)."""
    ha, hb = a["y_max"] - a["y_min"], b["y_max"] - b["y_min"]
    hmin, hmax = max(min(ha, hb), 1), max(ha, hb, 1)
    if hmin / hmax < 0.65:
        return False
    if (a["text"][:1] in MARKERS) != (b["text"][:1] in MARKERS):
        return False
    vover = min(a["y_max"], b["y_max"]) - max(a["y_min"], b["y_min"])      # >0: chong nhau theo chieu doc
    hgap = max(a["x_min"], b["x_min"]) - min(a["x_max"], b["x_max"])      # <0: chong nhau theo chieu ngang
    if vover >= 0.5 * hmin and hgap <= 1.0 * hmax:                          # cung hang
        return True
    wmin = max(min(a["x_max"] - a["x_min"], b["x_max"] - b["x_min"]), 1)
    hover = -hgap
    if -vover <= 0.35 * hmax and vover < 0.5 * hmin and hover >= 0.4 * wmin:  # hang duoi sat hang tren
        return True
    return False


def build_blocks(boxes, cjk_only=True):
    """Gom cac o chu gan nhau thanh khoi (1 cau). boxes da o toa do khung hinh goc.
    Tra ve list[dict(text, bbox=(x_min,x_max,y_min,y_max), conf)]."""
    if cjk_only:
        boxes = [b for b in boxes if _is_cjk(b["text"])]
    if not boxes:
        return []
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _should_merge(boxes[i], boxes[j]):
                parent[find(i)] = find(j)

    groups = collections.defaultdict(list)
    for i, b in enumerate(boxes):
        groups[find(i)].append(b)

    blocks = []
    for g in groups.values():
        blocks.append(dict(
            text=_join_text(g),
            bbox=(min(b["x_min"] for b in g), max(b["x_max"] for b in g),
                  min(b["y_min"] for b in g), max(b["y_max"] for b in g)),
            conf=statistics.mean(b["conf"] for b in g),
            row_h=statistics.median(_thickness(b) for b in g),
            polys=[b["poly"] for b in g] if all(b.get("poly") for b in g) else []))
    blocks.sort(key=lambda b: (b["bbox"][2], b["bbox"][0]))
    return blocks


def count_chars(text, cjk_only=True):
    """So chu that su (khong tinh khoang trang/ky hieu); cjk_only -> chi dem chu Han."""
    if cjk_only:
        return sum(1 for ch in text if _is_cjk(ch))
    return sum(1 for ch in text if ch.isalnum())


def detect_frame_blocks(engine, roi_img, roi_offset, scale, cjk_only=True, min_h=0.0, min_chars=1):
    """OCR 1 frame da crop ROI -> list khoi chu, toa do quy ve khung hinh goc.

    Chi giu chu LON, ro (hien thi tren man hinh): bo o chu cao < min_h px (chu li ti trong bang/UI/watermark)
    va bo khoi co it hon min_chars chu."""
    ox, oy = roi_offset
    boxes = []
    for b in engine.detect(roi_img):
        y_min, y_max = b["y_min"] / scale + oy, b["y_max"] / scale + oy
        if y_max - y_min < min_h:
            continue
        poly = [(q[0] / scale + ox, q[1] / scale + oy) for q in b["poly"]] if b.get("poly") else None
        boxes.append(dict(text=b["text"], conf=b["conf"],
                          x_min=b["x_min"] / scale + ox, x_max=b["x_max"] / scale + ox,
                          y_min=y_min, y_max=y_max, poly=poly))
    blocks = build_blocks(boxes, cjk_only)
    return [bl for bl in blocks if count_chars(bl["text"], cjk_only) >= min_chars]


# --------------------------------------------------------------------------
# 3) THEO DOI CAU PHU DE QUA CAC KHUNG HINH
# --------------------------------------------------------------------------

def similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def _boxdiff(a, b):
    return max(abs(a[i] - b[i]) for i in range(4))


def _median_box(boxes):
    return tuple(statistics.median(b[i] for b in boxes) for i in range(4))


def _near(a, b):
    """2 khung co chong len nhau khong (sau khi no a ra 0.5 chieu cao chu)?"""
    m = 0.5 * (a[3] - a[2])
    return (min(a[1] + m, b[1]) - max(a[0] - m, b[0]) > 0 and
            min(a[3] + m, b[3]) - max(a[2] - m, b[2]) > 0)


class Track:
    def __init__(self, t, block):
        self.frames = [(t, block["bbox"])]
        self.texts = [block["text"]]          # text OCR doc duoc o tung khung (song song voi frames)
        self.row_hs = [block.get("row_h", block["bbox"][3] - block["bbox"][2])]  # chieu cao 1 dong chu
        self.polys = [block.get("polys", [])]  # cac goc da giac cua tung o chu o tung khung (cho chu nghieng)
        self.confs = [block["conf"]]
        self.score = collections.defaultdict(float)
        self.score[block["text"]] += block["conf"]
        self.last_t = t

    def add(self, t, block):
        self.frames.append((t, block["bbox"]))
        self.texts.append(block["text"])
        self.row_hs.append(block.get("row_h", block["bbox"][3] - block["bbox"][2]))
        self.polys.append(block.get("polys", []))
        self.confs.append(block["conf"])
        self.score[block["text"]] += block["conf"]
        self.last_t = t

    refined_start = None      # giay; do refine_edges() dat sau khi gom track (None = dung khung OCR dau tien)
    refined_end = None        # giay (loai tru); None = khung OCR cuoi + 1 buoc lay mau

    @property
    def start(self):
        return self.refined_start if self.refined_start is not None else self.frames[0][0]

    def end_t(self, step_sec):
        return self.refined_end if self.refined_end is not None else self.last_t + step_sec

    def text(self):
        return max(self.score, key=lambda k: (self.score[k], len(k)))

    def row_h(self):
        """Chieu cao 1 dong chu (trung vi), dung lam don vi de dem vien cho hop."""
        return statistics.median(self.row_hs)

    def absorb(self, other):
        pairs = sorted(list(zip(self.frames, self.texts, self.polys, self.row_hs, self.confs)) +
                       list(zip(other.frames, other.texts, other.polys, other.row_hs, other.confs)),
                       key=lambda p: p[0][0])
        self.frames = [p[0] for p in pairs]
        self.texts = [p[1] for p in pairs]
        self.polys = [p[2] for p in pairs]
        self.row_hs = [p[3] for p in pairs]
        self.confs = [p[4] for p in pairs]
        for k, v in other.score.items():
            self.score[k] += v
        self.last_t = max(self.last_t, other.last_t)

    def slice(self, i, j):
        """Track con gom cac khung [i, j) (dung khi tach 1 track thanh nhieu cau)."""
        new = Track.__new__(Track)
        new.frames, new.texts, new.polys = self.frames[i:j], self.texts[i:j], self.polys[i:j]
        new.row_hs, new.confs = self.row_hs[i:j], self.confs[i:j]
        new.score = collections.defaultdict(float)
        for tx, c in zip(new.texts, new.confs):
            new.score[tx] += c
        new.last_t = new.frames[-1][0]
        return new


def _gate_near(track_box, block_box):
    """Khung moi co gan khung cuoi cua track khong (no track_box ra 1.5 x chieu cao chu moi phia)?"""
    m = 1.5 * max(track_box[3] - track_box[2], 1.0)
    return (min(track_box[1] + m, block_box[1]) - max(track_box[0] - m, block_box[0]) > 0 and
            min(track_box[3] + m, block_box[3]) - max(track_box[2] - m, block_box[2]) > 0)


def split_track(tr, step_sec, min_run_sec=0.3, split_sim=0.85):
    """Tach 1 track thanh nhieu cau neu noi dung doi han giua chung.

    Truoc day 2 cau lien tiep cung cho, giong nhau >= 60% (vd 'X出得有问题' -> 'Y出得有问题啊') bi gop
    thanh 1 cau. Hai cau khac nhau thi moi cau OCR doc ra MOT noi dung on dinh (nhieu khung giong het nhau)
    trong it nhat min_run_sec; con nhieu OCR cua cung 1 cau chi nhap nhay vai khung. Vay: tim cac doan 'on dinh'
    (>= min_run khung lien tiep cung text); 2 doan on dinh ke nhau ma giong nhau < split_sim -> cat o giua."""
    n = len(tr.frames)
    min_run = max(3, round(min_run_sec / step_sec))
    if n < 2 * min_run:
        return [tr]
    runs, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and tr.texts[j + 1] == tr.texts[i]:
            j += 1
        runs.append((i, j + 1, tr.texts[i]))
        i = j + 1
    stable = [r for r in runs if r[1] - r[0] >= min_run]
    cuts = []
    for r0, r1 in zip(stable, stable[1:]):
        if similar(r0[2], r1[2]) < split_sim:
            cuts.append((r0[1] + r1[0]) // 2)             # cat giua 2 doan on dinh (khung chuyen tiep chia doi)
    if not cuts:
        return [tr]
    bounds = [0] + cuts + [n]
    return [tr.slice(a, b) for a, b in zip(bounds, bounds[1:])]


def build_tracks(samples, step_sec, similarity=0.6, max_gap_frames=2,
                 min_frames=2, merge_sim=0.5, split_sim=0.85, min_run_sec=0.3):
    """samples: list[(t, blocks)] theo thu tu thoi gian -> list[Track]."""
    active, done = [], []
    eps = 1e-6
    for t, blocks in samples:
        pairs = []
        for bi, b in enumerate(blocks):
            for ti, tr in enumerate(active):
                r = similar(tr.text(), b["text"])
                # giong it (0.6..0.85) thi con phai o gan khung cu: tranh dinh 2 cau khac nhau o 2 cho khac nhau
                if r >= similarity and (r >= 0.85 or _gate_near(tr.frames[-1][1], b["bbox"])):
                    pairs.append((r, bi, ti))
        pairs.sort(reverse=True)
        used_b, used_t = set(), set()
        for r, bi, ti in pairs:
            if bi in used_b or ti in used_t:
                continue
            active[ti].add(t, blocks[bi])
            used_b.add(bi)
            used_t.add(ti)
        for bi, b in enumerate(blocks):
            if bi not in used_b:
                active.append(Track(t, b))
        still = []
        for tr in active:
            if t - tr.last_t > (max_gap_frames + 1) * step_sec + eps:
                done.append(tr)
            else:
                still.append(tr)
        active = still
    done.extend(active)

    # Noi cac manh bi OCR doc lech/hieu ung xuat hien lam dut thanh nhieu cau.
    # Chi noi MANH NGAN (< min_run khung) hoac manh giong han (>= split_sim): 2 cau dai, ke nhau, giong ~50-80%
    # la 2 cau khac nhau (khong noi, neu khong se gop cau).
    min_run = max(3, round(min_run_sec / step_sec))
    done.sort(key=lambda tr: tr.start)
    merged = []
    for tr in done:
        best, best_r = None, 0.0
        for prev in merged:
            gap = tr.start - (prev.last_t + step_sec)
            if gap < -eps or gap > (max_gap_frames + 1) * step_sec + eps:
                continue
            r = similar(prev.text(), tr.text())
            fragment = min(len(prev.frames), len(tr.frames)) < min_run
            if r >= merge_sim and (fragment or r >= split_sim) and r > best_r and _near(prev.frames[-1][1], tr.frames[0][1]):
                best, best_r = prev, r
        if best:
            best.absorb(tr)
        else:
            merged.append(tr)

    out = []
    for tr in merged:
        out.extend(split_track(tr, step_sec, min_run_sec, split_sim))
    return [tr for tr in out if len(tr.frames) >= min_frames]


# --------------------------------------------------------------------------
# 3b) TINH CHINH MOC BAT DAU / KET THUC THEO KHUNG HINH GOC
# --------------------------------------------------------------------------
# OCR chi chay o cac khung lay mau (--fps 10 tren video 30fps = cu 3 khung 1 lan), lai hay bo sot khung dau khi chu
# dang hien dan (mo/nhat). Nen moc bat dau thuong tre 1-3 khung so voi luc chu that su hien -> chu goc hien ra truoc
# roi 1 khung sau moi co hop den. Ham nay xem lai CAC KHUNG GOC nam sat truoc dau / sau cuoi moi cau, khong can OCR:
# chu da hien thi khi cac net chu (canh) cua khung on dinh van nam dung cho cu trong khung do.

def _edge_map(gray):
    return cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160) > 0


def _coverage(ref, gray):
    """Ti le net chu (ref: mat na canh cua khung on dinh) con nam dung cho cu trong anh gray (cho lech ~1px)."""
    near = cv2.dilate(_edge_map(gray).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return float((ref & near).sum()) / float(ref.sum())


def _text_region(tr, width, height):
    box = _median_box([b for _, b in tr.frames])
    p = 2.0 + 0.3 * tr.row_h()
    x1, x2 = max(0, int(box[0] - p)), min(width, int(math.ceil(box[1] + p)))
    y1, y2 = max(0, int(box[2] - p)), min(height, int(math.ceil(box[3] + p)))
    return (x1, x2, y1, y2) if x2 - x1 >= 4 and y2 - y1 >= 4 else None


def refine_edges(video_path, tracks, native_fps, step, width, height, reach=None, min_cov=0.55, min_ref_px=40):
    """Dat tr.refined_start / tr.refined_end sat voi khung hinh goc dau tien / cuoi cung co chu.

    reach = so khung goc toi da xet lui (truoc dau) va toi (sau cuoi) cho moi cau, mac dinh max(step, 4).
    Bo qua cau chu chuyen dong (KF) va cau khong du net chu de so. Tra ve so moc da doi."""
    if not tracks:
        return 0
    reach = max(step, 4) if reach is None else max(1, int(reach))
    jobs = []                           # (track, region, f_first, f_last)
    need = collections.defaultdict(list)
    for tr in tracks:
        region = _text_region(tr, width, height)
        if region is None or classify_motion(tr, step / native_fps)[0]:
            continue
        f0 = int(round(tr.frames[0][0] * native_fps))
        f1 = int(round(tr.last_t * native_fps))
        j = len(jobs)
        jobs.append((tr, region, f0, f1))
        want = {f0, f1}
        if len(tr.frames) >= 2:
            want |= {int(round(tr.frames[1][0] * native_fps)), int(round(tr.frames[-2][0] * native_fps))}
        want |= {f0 - k for k in range(1, reach + 2)} | {f1 + k for k in range(1, reach + 2)}
        for f in want:
            if f >= 0:
                need[f].append(j)
    if not need:
        return 0

    crops = {}
    last_needed = max(need)
    cap = cv2.VideoCapture(video_path)
    idx = 0
    while idx <= last_needed:
        ok, frame = cap.read()
        if not ok:
            break
        for j in need.get(idx, ()):
            x1, x2, y1, y2 = jobs[j][1]
            crops[(j, idx)] = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        idx += 1
    cap.release()

    changed = 0
    for j, (tr, region, f0, f1) in enumerate(jobs):
        def has(f):
            return crops.get((j, f)) is not None

        def refmask(fa, fb):
            """Net chu on dinh: canh cua khung fa (neu khung fb cung co thi chi giu net co o ca hai)."""
            if not has(fa):
                return None
            m = _edge_map(crops[(j, fa)])
            if has(fb) and fb != fa:
                near = cv2.dilate(_edge_map(crops[(j, fb)]).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                both = m & near
                if both.sum() >= min_ref_px:
                    m = both
            return m if m.sum() >= min_ref_px else None

        t1 = int(round(tr.frames[1][0] * native_fps)) if len(tr.frames) >= 2 else f0
        t2 = int(round(tr.frames[-2][0] * native_fps)) if len(tr.frames) >= 2 else f1
        # --- dau cau: lui tung khung goc khi chu da hien ---
        ref = refmask(f0, t1)
        if ref is not None:
            base = _coverage(ref, crops[(j, f0 - reach - 1)]) if has(f0 - reach - 1) else 0.0
            thr = max(min_cov, min(0.9, base + 0.2))        # nen nhieu net (da trung ref san) -> doi chat hon
            first = f0
            for k in range(1, reach + 1):
                if has(f0 - k) and _coverage(ref, crops[(j, f0 - k)]) >= thr:
                    first = f0 - k
                else:
                    break
            if first != f0:
                tr.refined_start = first / native_fps
                changed += 1
        # --- cuoi cau: toi tung khung goc khi chu con hien ---
        ref = refmask(f1, t2)
        if ref is not None:
            base = _coverage(ref, crops[(j, f1 + reach + 1)]) if has(f1 + reach + 1) else 0.0
            thr = max(min_cov, min(0.9, base + 0.2))
            last = f1
            for k in range(1, reach + 1):
                if has(f1 + k) and _coverage(ref, crops[(j, f1 + k)]) >= thr:
                    last = f1 + k
                else:
                    break
            new_end = (last + 1) / native_fps
            if abs(new_end - tr.end_t(step / native_fps)) > 1e-9:
                tr.refined_end = new_end
                changed += 1
    return changed


# --------------------------------------------------------------------------
# 4) KHUNG CHU: on dinh hay chuyen dong (KF)
# --------------------------------------------------------------------------

def _despike(vals, k, tol):
    """Xoa gai: khung nao lech > tol so voi trung vi cua so k thi thay bang trung vi.
    Doan chuyen dong lien tuc (don dieu) khong bi dong vao vi trung vi = chinh no.
    Khung dau/cuoi giu nguyen (khong du lang gieng de ket luan)."""
    n = len(vals)
    out = list(vals)
    if k <= 1 or n < 3:
        return out
    r = k // 2
    for i in range(1, n - 1):
        m = statistics.median(vals[max(0, i - r): i + r + 1])
        if abs(vals[i] - m) > tol:
            out[i] = m
    return out


def _geometry_frames(tr, min_text_sim=0.8):
    """Chi tin khung hinh cua cac khung OCR doc ra DUNG noi dung cau (cung do dai, giong >= 0.8).
    Khung doc thieu/thua chu hoac dinh chu la o ben canh se lam khung chu rong ra/hep lai
    mot ky tu (~45px) -> khong phai chuyen dong. Neu loc xong con qua it thi dung het."""
    best = tr.text()
    keep = [f for f, tx in zip(tr.frames, tr.texts)
            if len(tx) == len(best) and similar(tx, best) >= min_text_sim]
    return keep if len(keep) >= max(2, int(0.4 * len(tr.frames))) else list(tr.frames)


def classify_motion(tr, step_sec, move_tol=10.0, med_win=5, min_move_sec=0.1):
    """Phan loai 1 cau: tra ve (is_dynamic, frames_da_loc, box_on_dinh, ly_do).

    Chuyen dong THAT = ca 2 mep cua khung cung lech khoi vi tri on dinh (tinh tien: 2 mep cung
    huong; phong/thu: 2 mep nguoc huong) VA keo dai >= min_move_sec.
    Khong tinh la chuyen dong:
      - nhay dot bien 1-2 khung roi ve cho cu       (loc trung vi)
      - chi 1 mep lech (x2 vot ra/x1 vot vao)        (OCR thua/thieu chu hoac dinh chu ben canh)
      - lech nho <= tol (rung do OCR)                (tol = max(move_tol, 0.15 * chieu cao chu))
    """
    geo = _geometry_frames(tr)
    ts = [t for t, _ in geo]
    ref = _median_box([b for _, b in geo])
    tol = max(move_tol, 0.15 * (ref[3] - ref[2]))
    cols = [_despike([b[i] for _, b in geo], med_win, tol) for i in range(4)]
    boxes = list(zip(*cols))
    ref = _median_box(boxes)
    need = max(2, round(min_move_sec / step_sec))

    def moving(b):
        two_x = abs(b[0] - ref[0]) > tol and abs(b[1] - ref[1]) > tol
        two_y = abs(b[2] - ref[2]) > tol and abs(b[3] - ref[3]) > tol
        return two_x or two_y

    run = best = 0
    for b in boxes:
        run = run + 1 if moving(b) else 0
        best = max(best, run)
    if best >= need:
        return True, list(zip(ts, boxes)), ref, f"dong: {best} khung lien tiep lech > {tol:.0f}px"
    return False, list(zip(ts, boxes)), ref, f"tinh: lech lon nhat {best} khung (< {need}) hoac chi 1 mep"


def summarize(tr, step_sec, kf_tol=6.0, stable_sec=0.5, med_win=5, min_move_sec=0.1, move_tol=10.0,
              end_t=None):
    """Tra ve (main_box, kf_list). kf_list rong neu khung chu khong chuyen dong that."""
    is_dyn, frames, ref, _ = classify_motion(tr, step_sec, move_tol, med_win, min_move_sec)
    if not is_dyn:
        return ref, []                       # tinh: chi 1 khung, khong KF

    if end_t is None:
        end_t = tr.last_t + step_sec
    kfs = [frames[0]]
    for t, b in frames[1:]:
        if _boxdiff(b, kfs[-1][1]) > kf_tol:
            kfs.append((t, b))

    # KF cuoi dat tai luc ket thuc cau, voi khung o khung hinh cuoi
    if end_t - kfs[-1][0] > 1.5 * step_sec:
        kfs.append((end_t, frames[-1][1]))
    else:
        kfs[-1] = (end_t, kfs[-1][1])

    # Khung chinh = doan on dinh dai nhat (>= stable_sec), neu khong co thi khung dau
    runs = []
    for t, b in frames:
        if runs and _boxdiff(b, runs[-1]["ref"]) <= kf_tol:
            runs[-1]["boxes"].append(b)
            runs[-1]["end"] = t + step_sec
        else:
            runs.append(dict(ref=b, start=t, end=t + step_sec, boxes=[b]))
    best = max(runs, key=lambda r: r["end"] - r["start"])
    if best["end"] - best["start"] >= stable_sec:
        main = _median_box(best["boxes"])
    else:
        main = frames[0][1]
    return main, kfs


# --------------------------------------------------------------------------
# 5) GHI FILE .srtpx
# --------------------------------------------------------------------------

def _i(v):
    return int(round(v))


def pad_box(box, row_h, pad_ratio, width, height, min_px=2.0):
    """No hop ra de che het vien chu (net vien/bong/mep mo cua chu cung ma OCR khong do duoc).

    Dem = max(min_px, pad_ratio * chieu cao 1 dong chu) moi phia, roi kep trong khung hinh.
    pad_ratio <= 0 -> giu nguyen hop OCR."""
    if pad_ratio <= 0:
        return tuple(box)
    p = max(min_px, pad_ratio * row_h)
    x1, x2, y1, y2 = box
    return (max(0.0, x1 - p), min(float(width), x2 + p),
            max(0.0, y1 - p), min(float(height), y2 + p))


def join_ends(tracks, step_sec, join_gap):
    """Noi DUOI cau truoc voi DAU cau sau neu 2 cau cach nhau <= join_gap giay (khong chong nhau).

    Chi noi 2 cau cung "lan" (khung chu chong nhau theo chieu doc >= 50% chieu cao khung thap hon),
    de cau o cho khac (bang to, chu phu...) hien cung luc khong bi keo dai nham.
    tracks phai da sap theo thoi gian bat dau. Tra ve list end_t (giay) song song voi tracks."""
    ends = [tr.end_t(step_sec) for tr in tracks]
    if join_gap <= 0:
        return ends
    eps = 1e-6
    ybox = []
    for tr in tracks:
        box = _median_box([b for _, b in tr.frames])
        ybox.append((box[2], box[3]))

    def same_lane(i, j):
        top = max(ybox[i][0], ybox[j][0])
        bot = min(ybox[i][1], ybox[j][1])
        h = max(1.0, min(ybox[i][1] - ybox[i][0], ybox[j][1] - ybox[j][0]))
        return bot - top >= 0.5 * h

    n = len(tracks)
    for i in range(n):
        best = None
        for j in range(n):
            if j == i:
                continue
            gap = tracks[j].start - ends[i]
            if -eps <= gap <= join_gap + eps and same_lane(i, j):
                if best is None or tracks[j].start < tracks[best].start:
                    best = j
        if best is not None:
            ends[i] = max(ends[i], tracks[best].start)
    return ends


MAX_TILT_DEG = 80.0     # chu doc gan 90 do: hop bao ngoai da khit, khong can hop cheo
MAX_COVERS = 16


def _tilt_geom(poly):
    """Da giac 4 goc cua 1 dong chu -> hinh binh hanh (tam C, vec-to huong dong a, vec-to be day b, L, t, theta).
    Lay canh DAI lam huong dong chu (khong tin thu tu 4 diem: chu xoay > 45 do thi canh 0-1 la canh ngan),
    chuan hoa a huong sang phai (ax > 0), b huong xuong (by > 0) de thu tu cac hop con khong lat giua cac khung.
    None neu khong phai dong chu dai (L < 2t) hoac gan thang dung (> MAX_TILT_DEG)."""
    if not poly or len(poly) != 4:
        return None
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = poly
    e1 = ((x1 - x0) + (x2 - x3)) / 2, ((y1 - y0) + (y2 - y3)) / 2     # canh 0-1 va 3-2
    e2 = ((x3 - x0) + (x2 - x1)) / 2, ((y3 - y0) + (y2 - y1)) / 2     # canh 0-3 va 1-2
    (ax, ay), (bx, by) = (e1, e2) if math.hypot(*e1) >= math.hypot(*e2) else (e2, e1)
    L, t = math.hypot(ax, ay), math.hypot(bx, by)
    if t < 1 or L < 2 * t:                                              # chu ngan/vuong: khong xu ly
        return None
    if ax < 0:
        ax, ay = -ax, -ay
    if by < 0:
        bx, by = -bx, -by
    theta = math.degrees(math.atan2(ay, ax))                            # (-90, 90)
    if abs(theta) > MAX_TILT_DEG:
        return None
    return dict(cx=(x0 + x1 + x2 + x3) / 4, cy=(y0 + y1 + y2 + y3) / 4, ax=ax, ay=ay, bx=bx, by=by,
                L=L, t=t, theta=theta)


def _tilt_k(g, tol=0.35):
    """So hop con can de moi hop chi thua <= tol x be day chu theo chieu lech (chieu ngan hon cua hop bao ngoai
    1 doan: (L/k) * min(|sin|, |cos|))."""
    th = math.radians(g["theta"])
    slack = g["L"] * min(abs(math.sin(th)), abs(math.cos(th)))
    return max(2, min(MAX_COVERS, math.ceil(slack / (tol * g["t"]))))


def _tilt_boxes(g, k, text_frac=0.7):
    """(band, covers) tu hinh binh hanh g va so hop con k. Hop = (x1, x2, y1, y2).
    band: hop o giua dong, chua chu viet (nghieng <= 45 do: rong text_frac x L, cao t / cos; doc hon: nguoc lai)."""
    covers = []
    for i in range(k):
        s0, s1 = i / k - 0.5, (i + 1) / k - 0.5
        xs, ys = [], []
        for s in (s0, s1):
            for r in (-0.5, 0.5):
                xs.append(g["cx"] + s * g["ax"] + r * g["bx"])
                ys.append(g["cy"] + s * g["ay"] + r * g["by"])
        covers.append((min(xs), max(xs), min(ys), max(ys)))
    th = math.radians(g["theta"])
    cos_t, sin_t = math.cos(th), abs(math.sin(th))
    if abs(g["theta"]) <= 45:
        w, h = text_frac * g["L"] * cos_t, g["t"] / cos_t
    else:
        w, h = g["t"] / sin_t, text_frac * g["L"] * sin_t
    band = (g["cx"] - w / 2, g["cx"] + w / 2, g["cy"] - h / 2, g["cy"] + h / 2)
    return band, covers


def tilt_cover(poly, min_tilt_deg=4.0, tol=0.35, max_k=MAX_COVERS, text_frac=0.7):
    """Chu nghieng (dong chu la hinh binh hanh 4 goc): thay hop chu nhat to bang
    - band: hop nam giua dong (chua chu viet);
    - covers: chuoi hop nho doc theo duong cheo (moi hop chi cheo them <= tol x be day chu), phu kin chu cu.
    Tra ve (band, covers) hoac None neu chu khong nghieng (< min_tilt_deg) / khong du dieu kien."""
    g = _tilt_geom(poly)
    if g is None or abs(g["theta"]) < min_tilt_deg:
        return None
    return _tilt_boxes(g, min(max_k, _tilt_k(g, tol)), text_frac)


def tilt_cover_multi(polys, min_tilt_deg=4.0):
    """Nhu tilt_cover nhung cho khoi co NHIEU dong chu (OCR cat 1 cau nghieng thanh nhieu da giac, hoac cau 2 dong):
    moi dong nghieng -> hop chinh + hop con; dong thang -> 1 hop bao ngoai. Hop chinh (chua chu) = dong nghieng dai nhat.
    None neu khong dong nao nghieng."""
    geoms = [(p, _tilt_geom(p)) for p in polys]
    tilted = [(p, g) for p, g in geoms if g is not None and abs(g["theta"]) >= min_tilt_deg]
    if not tilted:
        return None
    main_g = max(tilted, key=lambda pg: pg[1]["L"])[1]
    band, covers = _tilt_boxes(main_g, _tilt_k(main_g))
    for p, g in geoms:
        if g is main_g:
            continue
        if g is not None and abs(g["theta"]) >= min_tilt_deg:
            bd, cv = _tilt_boxes(g, _tilt_k(g))
            covers.extend([bd] + cv)
        else:
            xs, ys = [q[0] for q in p], [q[1] for q in p]
            covers.append((min(xs), max(xs), min(ys), max(ys)))
    return band, covers


def _tilt_for_track(tr, main, tilt_deg):
    """Chu nghieng DUNG YEN -> (band, covers); khong thi None."""
    if tilt_deg <= 0 or not tr.polys:
        return None
    idx = min(range(len(tr.frames)), key=lambda i: _boxdiff(tr.frames[i][1], main))
    polys = tr.polys[idx]
    if not polys:
        return None
    return tilt_cover_multi(polys, min_tilt_deg=tilt_deg)


def _tilt_dynamic(tr, main, kfs, tilt_deg):
    """Chu nghieng/xoay VA chuyen dong (to giay bay + xoay, cau phong to...): hop bao ngoai cua chu xoay phinh to
    theo duong cheo -> thay bang hop chinh + K hop con, MOI hop co chuoi KF rieng (cung moc thoi gian voi kfs).
    Tra ve (main_boxes, kf_boxes) hoac None; main_boxes = [band, cover_1..K]; kf_boxes = [(t, [band, cover_1..K]), ...]
    Chi dung khung hinh co dung 1 da giac (khung khac lay hinh gan nhat), can >= 60% khung hop le va co khung nghieng."""
    if tilt_deg <= 0 or not tr.polys or not kfs:
        return None
    geoms = [_tilt_geom(pl[0]) if len(pl) == 1 else None for pl in tr.polys]
    valid = [i for i, g in enumerate(geoms) if g is not None]
    if len(valid) < max(2, 0.6 * len(geoms)) or not any(abs(geoms[i]["theta"]) >= tilt_deg for i in valid):
        return None
    K = max(_tilt_k(geoms[i]) for i in valid)
    boxes = {i: _tilt_boxes(geoms[i], K) for i in valid}
    flat = {i: [bd] + cv for i, (bd, cv) in boxes.items()}

    def nearest_valid(t):
        return min(valid, key=lambda i: abs(tr.frames[i][0] - t))

    def at(t):
        c = nearest_valid(t)
        pos = valid.index(c)
        if pos == 0 or pos == len(valid) - 1:               # dau/cuoi: giu dung khung (trung vi 2 khung se lech nua buoc)
            return list(flat[c])
        near = [flat[valid[q]] for q in (pos - 1, pos, pos + 1)]
        return [tuple(statistics.median(nb[j][d] for nb in near) for d in range(4)) for j in range(K + 1)]

    idx = min(valid, key=lambda i: _boxdiff(tr.frames[i][1], main))
    return flat[idx], [(t, at(t)) for t, _ in kfs]


def format_srtpx(tracks, width, height, step_sec, kf_tol=6.0, stable_sec=0.5, med_win=5,
                 min_move_sec=0.1, report=False, move_tol=10.0, pad_ratio=0.0, join_gap=0.0, tilt_deg=0.0):
    tracks = sorted(tracks, key=lambda tr: (tr.start, tr.frames[0][1][2]))
    ends = join_ends(tracks, step_sec, join_gap)
    entries = []

    def entry(text, start, end, box, kfs=()):
        lines = [
            str(len(entries) + 1),
            f"{seconds_to_srt_ts(start)} --> {seconds_to_srt_ts(end)}",
            text,
            f"Độ rộng: {_i(box[0])}px - {_i(box[1])}px",
            f"Vị trí: {_i(box[2])}px - {_i(box[3])}px",
        ]
        for t, b in kfs:
            lines.append(f"KF {t:.2f}s: {_i(b[0])} {_i(b[1])} {_i(b[2])} {_i(b[3])}")
        entries.append("\r\n".join(lines))

    for n, tr in enumerate(tracks, start=1):
        end_t = ends[n - 1]
        main, kfs = summarize(tr, step_sec, kf_tol, stable_sec, med_win, min_move_sec, move_tol, end_t=end_t)
        if report:
            print(f"#{n:>3} {tr.text()[:12]:<12} -> {classify_motion(tr, step_sec, move_tol, med_win, min_move_sec)[3]}",
                  file=sys.stderr)
        rh = tr.row_h()
        padb = lambda b: pad_box(b, rh, pad_ratio, width, height)
        tilt = None if kfs else _tilt_for_track(tr, main, tilt_deg)
        if tilt:                                    # chu nghieng: hop chinh = dai ngang giua, them hop che doc duong cheo
            band, covers = tilt
            entry(tr.text(), tr.start, end_t, padb(band))
            for cv in covers:                       # block khong co chu: chi ve hop den
                entry("", tr.start, end_t, padb(cv))
            if report:
                print(f"      chu nghieng -> 1 hop chinh + {len(covers)} hop che", file=sys.stderr)
            continue
        dyn = _tilt_dynamic(tr, main, kfs, tilt_deg) if kfs else None
        if dyn:                                     # chu nghieng/xoay + chuyen dong: moi hop co KF rieng
            main_boxes, kf_boxes = dyn
            for j, mb in enumerate(main_boxes):
                entry(tr.text() if j == 0 else "", tr.start, end_t, padb(mb),
                      [(t, padb(bs[j])) for t, bs in kf_boxes])
            if report:
                print(f"      chu xoay + dong -> 1 hop chinh + {len(main_boxes) - 1} hop che, {len(kf_boxes)} KF",
                      file=sys.stderr)
            continue
        main = padb(main)
        kfs = [(t, padb(b)) for t, b in kfs]
        entry(tr.text(), tr.start, end_t, main, kfs)
    return f"#res {width}x{height}\r\n\r\n" + "\r\n\r\n".join(entries)


def write_srtpx(tracks, out_path, width, height, step_sec, kf_tol=6.0, stable_sec=0.5, med_win=5,
                min_move_sec=0.1, report=False, move_tol=10.0, pad_ratio=0.0, join_gap=0.0, tilt_deg=0.0):
    content = format_srtpx(tracks, width, height, step_sec, kf_tol, stable_sec, med_win, min_move_sec,
                           report, move_tol, pad_ratio, join_gap, tilt_deg)
    with open(out_path, "wb") as f:   # ghi nhi phan de giu dung CRLF tren moi he dieu hanh
        f.write(content.encode("utf-8"))


# --------------------------------------------------------------------------
# 6) ANH DEBUG
# --------------------------------------------------------------------------

def save_debug_frame(frame, roi_px, blocks, out_path):
    img = frame.copy()
    rx0, ry0, rx1, ry1 = roi_px
    cv2.rectangle(img, (rx0, ry0), (rx1 - 1, ry1 - 1), (255, 200, 0), 1)   # vung ROI (xanh)
    for b in blocks:
        x_min, x_max, y_min, y_max = b["bbox"]
        cv2.rectangle(img, (round(x_min), round(y_min)), (round(x_max), round(y_max)),
                      (0, 0, 255), 2)                                       # chu tim thay (do)
    cv2.imwrite(out_path, img)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def parse_roi(spec, w, h):
    x1, y1, x2, y2 = (float(v) for v in spec.split(","))
    return (round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h))


def main():
    ap = argparse.ArgumentParser(description="Bóc hardsub tiếng Trung từ video ra file .srtpx")
    ap.add_argument("video", help="Đường dẫn file video đầu vào")
    ap.add_argument("-o", "--output", required=True, help="File .srtpx đầu ra")
    ap.add_argument("--fps", type=float, default=30.0, help="FPS lấy mẫu khung hình (mặc định 30)")
    ap.add_argument("--roi", default="0,0,1.0,1.0",
                    help="Vùng quét, phân số x1,y1,x2,y2 (mặc định toàn khung hình)")
    ap.add_argument("--engine", choices=["tesseract", "easyocr", "paddleocr"], default="tesseract")
    ap.add_argument("--lang", default="chi_sim",
                    help="tesseract='chi_sim'/'chi_tra', paddleocr='ch'/'chinese_cht', easyocr='ch_sim'/'ch_tra'")
    ap.add_argument("--scale", type=float, default=2.0, help="Phóng to ROI trước khi OCR")
    ap.add_argument("--min-conf", type=float, default=0.6, help="Ngưỡng tin cậy OCR tối thiểu (0..1)")
    ap.add_argument("--min-height", type=float, default=0.035,
                    help="Chỉ lấy chữ cao ít nhất tỉ lệ này so với chiều cao video (mặc định 0.035 = 3.5%%); "
                         "chữ nhỏ li ti trong bảng/giao diện bị bỏ. 0 = tắt")
    ap.add_argument("--min-chars", type=int, default=2,
                    help="Một khối chữ phải có ít nhất ngần này chữ mới được lấy (mặc định 2)")
    ap.add_argument("--keep-non-cjk", action="store_true",
                    help="Giữ cả chữ không phải chữ Hán (mặc định bỏ để tránh dính số/logo)")
    ap.add_argument("--similarity", type=float, default=0.6,
                    help="Ngưỡng giống nhau để coi 2 khung là cùng 1 câu (0..1)")
    ap.add_argument("--merge-sim", type=float, default=0.5,
                    help="Ngưỡng nối các mảnh câu bị đứt do OCR/hiệu ứng (0..1)")
    ap.add_argument("--split-sim", type=float, default=0.85,
                    help="2 doan text on dinh ke nhau trong 1 cau giong nhau < so nay -> tach thanh 2 cau (0..1; 0 = tat)")
    ap.add_argument("--min-run-sec", type=float, default=0.3,
                    help="Mot noi dung phai on dinh it nhat so giay nay moi tinh la 1 cau rieng khi tach cau")
    ap.add_argument("--max-gap-frames", type=int, default=2,
                    help="Số khung OCR trống liên tiếp tối đa vẫn coi là cùng 1 câu")
    ap.add_argument("--min-frames", type=int, default=2, help="Số khung tối thiểu để 1 câu được tính")
    ap.add_argument("--kf-tol", type=float, default=6.0,
                    help="Câu ĐÃ là động: khung lệch quá số pixel này thì thêm 1 dòng KF")
    ap.add_argument("--move-tol", type=float, default=10.0,
                    help="Quyết định tĩnh/động: cả 2 mép khung phải lệch quá số px này (và >=15%% chiều cao chữ)")
    ap.add_argument("--med-win", type=int, default=5,
                    help="Cửa sổ lọc trung vị (khung) để xoá nhiễu đột biến 1-2 khung; 1 = tắt")
    ap.add_argument("--min-move-sec", type=float, default=0.1,
                    help="Chuyển động phải kéo dài ít nhất số giây này mới tính là động")
    ap.add_argument("--report", action="store_true",
                    help="In ra stderr từng câu được xếp là tĩnh/động và lý do")
    ap.add_argument("--stable-sec", type=float, default=0.5,
                    help="Khung giữ yên ít nhất số giây này mới coi là khung ổn định chính")
    ap.add_argument("--pad", type=float, default=0.05,
                    help="No hop den ra moi phia = so nay x chieu cao 1 dong chu, toi thieu 2px (mac dinh 0.05: hop sat chu), 0 = tat")
    ap.add_argument("--join-gap", type=float, default=0.5,
                    help="2 cau lien tiep cach nhau <= so giay nay thi noi duoi cau truoc vao dau cau sau, 0 = tat")
    ap.add_argument("--tilt", type=float, default=4.0,
                    help="Chu nghieng tu so do nay tro len thi thay hop den to bang chuoi hop nho doc theo duong cheo "
                         "(chi cho chu dung yen, can goc da giac cua OCR: paddleocr/easyocr), 0 = tat")
    ap.add_argument("--no-refine", action="store_true",
                    help="Tat buoc tinh chinh moc bat dau/ket thuc theo tung khung hinh goc (mac dinh bat: lui moc dau "
                         "ve dung khung chu bat dau hien, tranh chu hien truoc roi 1 khung sau moi co hop den)")
    ap.add_argument("--refine-reach", type=int, default=None,
                    help="So khung goc toi da xet lui/toi moi dau cau khi tinh chinh (mac dinh max(buoc lay mau, 4))")
    ap.add_argument("--debug-dir", default=None, help="Thư mục lưu ảnh debug đã kẻ khung")
    ap.add_argument("--debug-every", type=int, default=15, help="Lưu debug mỗi N frame đã xử lý")
    args = ap.parse_args()

    try:
        info = video_info(args.video, args.fps)
    except RuntimeError as e:
        sys.exit(str(e))
    w, h, step_sec = info["width"], info["height"], info["step_sec"]
    roi_px = parse_roi(args.roi, w, h)
    rx0, ry0, rx1, ry1 = roi_px

    if args.debug_dir:
        os.makedirs(args.debug_dir, exist_ok=True)

    engine = OcrEngine(engine=args.engine, lang=args.lang, min_conf=args.min_conf)

    samples = []
    processed = 0
    for t, frame in iter_frames(args.video, args.fps):
        roi_img = frame[ry0:ry1, rx0:rx1]
        if args.scale != 1.0:
            roi_img = cv2.resize(roi_img, None, fx=args.scale, fy=args.scale,
                                 interpolation=cv2.INTER_CUBIC)
        blocks = detect_frame_blocks(engine, roi_img, (rx0, ry0), args.scale,
                                     cjk_only=not args.keep_non_cjk, min_h=args.min_height * h,
                                     min_chars=args.min_chars)
        samples.append((t, blocks))

        if args.debug_dir and processed % args.debug_every == 0:
            save_debug_frame(frame, roi_px, blocks,
                             os.path.join(args.debug_dir, f"f_{processed:06d}.jpg"))
        processed += 1
        if processed % 100 == 0:
            print(f"...đã xử lý {processed} frame (t={t:.1f}s)", file=sys.stderr)

    tracks = build_tracks(samples, step_sec, similarity=args.similarity,
                          max_gap_frames=args.max_gap_frames, min_frames=args.min_frames,
                          merge_sim=args.merge_sim, split_sim=args.split_sim, min_run_sec=args.min_run_sec)
    if not args.no_refine:
        n_ref = refine_edges(args.video, tracks, info["native_fps"], info["step"], w, h, reach=args.refine_reach)
        print(f"Tinh chinh moc thoi gian theo khung goc: doi {n_ref} moc", file=sys.stderr)
    write_srtpx(tracks, args.output, w, h, step_sec, args.kf_tol, args.stable_sec,
                args.med_win, args.min_move_sec, args.report, args.move_tol,
                args.pad, args.join_gap, args.tilt)
    print(f"Xong: {len(tracks)} câu phụ đề -> {args.output}")


if __name__ == "__main__":
    main()
