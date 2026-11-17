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
                             y_min=min(ys), y_max=max(ys), conf=conf))
        return out

    def _detect_easyocr(self, img_bgr):
        out = []
        for box, text, conf in self._backend.readtext(img_bgr):
            if conf < self.min_conf or not text.strip():
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(dict(text=text.strip(), x_min=min(xs), x_max=max(xs),
                             y_min=min(ys), y_max=max(ys), conf=conf))
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
    """Noi chu cua 1 khoi: theo hang (tren->duoi), trong hang (trai->phai)."""
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
            a, b = boxes[i], boxes[j]
            h = max(a["y_max"] - a["y_min"], b["y_max"] - b["y_min"], 1)
            vgap = max(a["y_min"], b["y_min"]) - min(a["y_max"], b["y_max"])
            hgap = max(a["x_min"], b["x_min"]) - min(a["x_max"], b["x_max"])
            if vgap <= 0.8 * h and hgap <= 1.5 * h:
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
            row_h=statistics.median(b["y_max"] - b["y_min"] for b in g)))
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
        boxes.append(dict(text=b["text"], conf=b["conf"],
                          x_min=b["x_min"] / scale + ox, x_max=b["x_max"] / scale + ox,
                          y_min=y_min, y_max=y_max))
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
        self.score = collections.defaultdict(float)
        self.score[block["text"]] += block["conf"]
        self.last_t = t

    def add(self, t, block):
        self.frames.append((t, block["bbox"]))
        self.texts.append(block["text"])
        self.row_hs.append(block.get("row_h", block["bbox"][3] - block["bbox"][2]))
        self.score[block["text"]] += block["conf"]
        self.last_t = t

    @property
    def start(self):
        return self.frames[0][0]

    def text(self):
        return max(self.score, key=lambda k: (self.score[k], len(k)))

    def row_h(self):
        """Chieu cao 1 dong chu (trung vi), dung lam don vi de dem vien cho hop."""
        return statistics.median(self.row_hs)

    def absorb(self, other):
        pairs = sorted(list(zip(self.frames, self.texts)) + list(zip(other.frames, other.texts)),
                       key=lambda p: p[0][0])
        self.frames = [p[0] for p in pairs]
        self.texts = [p[1] for p in pairs]
        self.row_hs = sorted(self.row_hs + other.row_hs)
        for k, v in other.score.items():
            self.score[k] += v
        self.last_t = max(self.last_t, other.last_t)


def build_tracks(samples, step_sec, similarity=0.6, max_gap_frames=2,
                 min_frames=2, merge_sim=0.5):
    """samples: list[(t, blocks)] theo thu tu thoi gian -> list[Track]."""
    active, done = [], []
    eps = 1e-6
    for t, blocks in samples:
        pairs = []
        for bi, b in enumerate(blocks):
            for ti, tr in enumerate(active):
                r = similar(tr.text(), b["text"])
                if r >= similarity:
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

    # Noi cac manh bi OCR doc lech/hieu ung xuat hien lam dut thanh nhieu cau
    done.sort(key=lambda tr: tr.start)
    merged = []
    for tr in done:
        best, best_r = None, 0.0
        for prev in merged:
            gap = tr.start - (prev.last_t + step_sec)
            if gap < -eps or gap > (max_gap_frames + 1) * step_sec + eps:
                continue
            r = similar(prev.text(), tr.text())
            if r >= merge_sim and r > best_r and _near(prev.frames[-1][1], tr.frames[0][1]):
                best, best_r = prev, r
        if best:
            best.absorb(tr)
        else:
            merged.append(tr)
    return [tr for tr in merged if len(tr.frames) >= min_frames]


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
    ends = [tr.last_t + step_sec for tr in tracks]
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


def format_srtpx(tracks, width, height, step_sec, kf_tol=6.0, stable_sec=0.5, med_win=5,
                 min_move_sec=0.1, report=False, move_tol=10.0, pad_ratio=0.0, join_gap=0.0):
    tracks = sorted(tracks, key=lambda tr: (tr.start, tr.frames[0][1][2]))
    ends = join_ends(tracks, step_sec, join_gap)
    entries = []
    for n, tr in enumerate(tracks, start=1):
        end_t = ends[n - 1]
        main, kfs = summarize(tr, step_sec, kf_tol, stable_sec, med_win, min_move_sec, move_tol, end_t=end_t)
        if report:
            print(f"#{n:>3} {tr.text()[:12]:<12} -> {classify_motion(tr, step_sec, move_tol, med_win, min_move_sec)[3]}",
                  file=sys.stderr)
        rh = tr.row_h()
        main = pad_box(main, rh, pad_ratio, width, height)
        kfs = [(t, pad_box(b, rh, pad_ratio, width, height)) for t, b in kfs]
        lines = [
            str(n),
            f"{seconds_to_srt_ts(tr.start)} --> {seconds_to_srt_ts(end_t)}",
            tr.text(),
            f"Độ rộng: {_i(main[0])}px - {_i(main[1])}px",
            f"Vị trí: {_i(main[2])}px - {_i(main[3])}px",
        ]
        for t, b in kfs:
            lines.append(f"KF {t:.2f}s: {_i(b[0])} {_i(b[1])} {_i(b[2])} {_i(b[3])}")
        entries.append("\r\n".join(lines))
    return f"#res {width}x{height}\r\n\r\n" + "\r\n\r\n".join(entries)


def write_srtpx(tracks, out_path, width, height, step_sec, kf_tol=6.0, stable_sec=0.5, med_win=5,
                min_move_sec=0.1, report=False, move_tol=10.0, pad_ratio=0.0, join_gap=0.0):
    content = format_srtpx(tracks, width, height, step_sec, kf_tol, stable_sec, med_win, min_move_sec,
                           report, move_tol, pad_ratio, join_gap)
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
    ap.add_argument("--pad", type=float, default=0.25,
                    help="No hop den ra moi phia = so nay x chieu cao 1 dong chu (che het vien chu), 0 = tat")
    ap.add_argument("--join-gap", type=float, default=0.3,
                    help="2 cau lien tiep cach nhau <= so giay nay thi noi duoi cau truoc vao dau cau sau, 0 = tat")
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
                          merge_sim=args.merge_sim)
    write_srtpx(tracks, args.output, w, h, step_sec, args.kf_tol, args.stable_sec,
                args.med_win, args.min_move_sec, args.report, args.move_tol,
                args.pad, args.join_gap)
    print(f"Xong: {len(tracks)} câu phụ đề -> {args.output}")


if __name__ == "__main__":
    main()
