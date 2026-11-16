#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hardsub_extract.py
===================

Bóc hardsub (chữ cứng/burned-in) tiếng Trung từ video ra file .srtpx
(giống định dạng file test.srtpx mẫu: SRT + 2 dòng toạ độ pixel
"Độ rộng" và "Vị trí", có thêm nhánh "(cuối câu: ...)" khi khung chữ
thay đổi từ lúc câu vừa xuất hiện tới lúc câu "chốt" (ổn định).

NGUYÊN LÝ HOẠT ĐỘNG (đúng như yêu cầu):
  1. Tách khung hình video theo FPS mục tiêu (mặc định 30fps).
  2. Với mỗi khung hình, cắt vùng chứa phụ đề (ROI) rồi chạy OCR để
     tìm xem CHỮ NẰM Ở ĐÂU (toạ độ) và NỘI DUNG là gì.
  3. Gộp các khung hình liên tiếp có cùng nội dung chữ thành 1 "câu"
     phụ đề (xác định mốc thời gian bắt đầu/kết thúc).
  4. Với mỗi câu, so khung chữ lúc MỚI XUẤT HIỆN và lúc CHỐT CÂU; nếu
     lệch nhau -> ghi cả 2 khung (khung chính + "cuối câu: ..."); nếu
     không đổi -> chỉ ghi 1 khung.
  5. Ghi ra file .srtpx đúng format mẫu. Có thể xuất thêm các khung
     hình debug đã "kẻ bảng" (vẽ khung đỏ quanh chữ phát hiện được)
     để kiểm tra ROI/OCR có đúng không.

CÀI ĐẶT (chạy ở máy có internet, máy chạy sandbox này KHÔNG có mạng
nên không tự tải được model OCR tiếng Trung):
  pip install opencv-python-headless numpy pillow
  # OCR engine (chọn 1, khuyên dùng paddleocr cho tiếng Trung):
  pip install paddleocr paddlepaddle          # tốt nhất cho CJK
  # hoặc:
  pip install easyocr
  # hoặc dùng tesseract có sẵn + cài gói ngôn ngữ Trung:
  #   Ubuntu: sudo apt install tesseract-ocr-chi-sim tesseract-ocr-chi-tra

VÍ DỤ CHẠY:
  python3 hardsub_extract.py video.mp4 -o ketqua.srtpx \
      --engine paddleocr --lang ch --fps 30 \
      --roi 0,0.75,1.0,1.0 --debug-dir debug_frames --debug-every 20
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
# 1) TÁCH KHUNG HÌNH THEO FPS MỤC TIÊU
# --------------------------------------------------------------------------

def iter_frames(video_path, target_fps):
    """Sinh ra (thoi_gian_giay, frame_BGR) lấy mẫu theo target_fps.

    Luôn duyệt qua toàn bộ frame gốc của video để tính đúng mốc thời
    gian thực (time = frame_index_goc / fps_goc), chỉ *chạy OCR* trên
    những frame rơi đúng vào bước lấy mẫu để không phải xử lý thừa.
    """
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
            t = frame_idx / native_fps
            yield t, frame
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
# 2) OCR: TÌM CHỮ + TOẠ ĐỘ TRONG VÙNG ROI
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
            self._backend = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
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


def detect_frame_text(engine, roi_img, roi_offset, scale):
    """Chạy OCR trên 1 frame đã crop ROI, trả về (text_gop, bbox) với
    bbox đã quy đổi về toạ độ pixel GỐC của frame đầy đủ (chưa crop,
    chưa scale). Nếu không thấy chữ -> (None, None)."""
    boxes = engine.detect(roi_img)
    if not boxes:
        return None, None

    # Gộp mọi box phát hiện được trong frame thành 1 khối phụ đề:
    # sắp theo thứ tự đọc (trên->dưới, trái->phải), nối text lại,
    # bbox tổng = hợp (union) của mọi box con.
    boxes.sort(key=lambda b: (round(b["y_min"] / 10), b["x_min"]))
    text = "".join(b["text"] for b in boxes) if any(_is_cjk(b["text"]) for b in boxes) \
        else " ".join(b["text"] for b in boxes)

    x_min = min(b["x_min"] for b in boxes)
    x_max = max(b["x_max"] for b in boxes)
    y_min = min(b["y_min"] for b in boxes)
    y_max = max(b["y_max"] for b in boxes)

    ox, oy = roi_offset
    bbox = (
        x_min / scale + ox,
        x_max / scale + ox,
        y_min / scale + oy,
        y_max / scale + oy,
    )
    return text, bbox


def _is_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


# --------------------------------------------------------------------------
# 3) GHÉP CÁC FRAME LIÊN TIẾP THÀNH TỪNG "CÂU" PHỤ ĐỀ
# --------------------------------------------------------------------------

Segment = collections.namedtuple("Segment", "text start_t end_t boxes")


def build_segments(samples, similarity=0.72, max_gap_frames=2, min_frames=2):
    """samples: list[(t, text_or_None, bbox_or_None)] theo thứ tự thời gian.
    Trả về list[Segment]."""
    segments = []
    cur_texts = []     # text của từng frame trong câu hiện tại
    cur_boxes = []      # bbox của từng frame trong câu hiện tại
    cur_times = []
    empty_streak = 0

    def flush():
        if len(cur_times) >= min_frames and cur_texts:
            rep_text = collections.Counter(cur_texts).most_common(1)[0][0]
            segments.append(Segment(rep_text, cur_times[0], cur_times[-1], list(cur_boxes)))

    for t, text, bbox in samples:
        if text is None:
            empty_streak += 1
            if cur_times and empty_streak > max_gap_frames:
                flush()
                cur_texts, cur_boxes, cur_times = [], [], []
            continue
        empty_streak = 0

        if not cur_texts:
            cur_texts, cur_boxes, cur_times = [text], [bbox], [t]
            continue

        ref = collections.Counter(cur_texts).most_common(1)[0][0]
        ratio = difflib.SequenceMatcher(None, ref, text).ratio()
        if ratio >= similarity:
            cur_texts.append(text)
            cur_boxes.append(bbox)
            cur_times.append(t)
        else:
            flush()
            cur_texts, cur_boxes, cur_times = [text], [bbox], [t]

    flush()
    return segments


# --------------------------------------------------------------------------
# 4) TÍNH KHUNG TOẠ ĐỘ (Độ rộng / Vị trí) + PHÁT HIỆN "cuối câu"
# --------------------------------------------------------------------------

def _robust_range(boxes, idx_lo, idx_hi):
    """Trung vị của x_min/x_max (hoặc y_min/y_max) trong 1 cửa sổ frame,
    để đỡ bị nhiễu bởi vài frame OCR đọc lệch."""
    xs_min = [b[idx_lo] for b in boxes]
    xs_max = [b[idx_hi] for b in boxes]
    return statistics.median(xs_min), statistics.median(xs_max)


def summarize_box(boxes, edge_frac=0.3, max_edge_frames=3, shift_tolerance_px=6):
    """boxes: list[(x_min,x_max,y_min,y_max)] theo thứ tự thời gian của 1 câu.
    Trả về dict:
      width_main=(a,b); pos_main=(a,b)
      width_end=(a,b) hoặc None; pos_end=(a,b) hoặc None  (nhánh 'cuối câu')
    """
    n = len(boxes)
    k = max(1, min(max_edge_frames, round(n * edge_frac)))

    w0_a, w0_b = _robust_range(boxes[:k], 0, 1)
    p0_a, p0_b = _robust_range(boxes[:k], 2, 3)
    w1_a, w1_b = _robust_range(boxes[-k:], 0, 1)
    p1_a, p1_b = _robust_range(boxes[-k:], 2, 3)

    changed = (abs(w0_a - w1_a) > shift_tolerance_px or abs(w0_b - w1_b) > shift_tolerance_px or
               abs(p0_a - p1_a) > shift_tolerance_px or abs(p0_b - p1_b) > shift_tolerance_px)

    if changed:
        return dict(width_main=(w0_a, w0_b), pos_main=(p0_a, p0_b),
                     width_end=(w1_a, w1_b), pos_end=(p1_a, p1_b))

    w_a, w_b = _robust_range(boxes, 0, 1)
    p_a, p_b = _robust_range(boxes, 2, 3)
    return dict(width_main=(w_a, w_b), pos_main=(p_a, p_b), width_end=None, pos_end=None)


# --------------------------------------------------------------------------
# 5) GHI FILE .srtpx ĐÚNG ĐỊNH DẠNG MẪU
# --------------------------------------------------------------------------

def write_srtpx(segments, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            info = summarize_box(seg.boxes)
            f.write(f"{i}\n")
            f.write(f"{seconds_to_srt_ts(seg.start_t)} --> {seconds_to_srt_ts(seg.end_t)}\n")
            f.write(f"{seg.text}\n")

            wa, wb = info["width_main"]
            line_w = f"Độ rộng: {round(wa)}px - {round(wb)}px"
            if info["width_end"]:
                ea, eb = info["width_end"]
                line_w += f" (cuối câu: {round(ea)}px - {round(eb)}px)"
            f.write(line_w + "\n")

            pa, pb = info["pos_main"]
            line_p = f"Vị trí: {round(pa)}px - {round(pb)}px"
            if info["pos_end"]:
                ea, eb = info["pos_end"]
                line_p += f" (cuối câu: {round(ea)}px - {round(eb)}px)"
            f.write(line_p + "\n")

            f.write("\n")


# --------------------------------------------------------------------------
# 6) XUẤT FRAME DEBUG ĐÃ "KẺ BẢNG" QUANH CHỮ PHÁT HIỆN ĐƯỢC
# --------------------------------------------------------------------------

def save_debug_frame(frame, roi_px, bbox_full, out_path):
    img = frame.copy()
    rx0, ry0, rx1, ry1 = roi_px
    cv2.rectangle(img, (rx0, ry0), (rx1, ry1), (255, 200, 0), 1)  # vùng ROI
    if bbox_full:
        x_min, x_max, y_min, y_max = bbox_full
        cv2.rectangle(img, (round(x_min), round(y_min)), (round(x_max), round(y_max)),
                      (0, 0, 255), 2)  # khung chữ phát hiện được
    cv2.imwrite(out_path, img)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------

def parse_roi(spec, w, h):
    """spec dạng 'x1,y1,x2,y2' là PHÂN SỐ 0..1 của khung hình
    (mặc định '0,0,1.0,1.0' = toàn bộ khung hình)."""
    x1, y1, x2, y2 = (float(v) for v in spec.split(","))
    return (round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h))


def main():
    ap = argparse.ArgumentParser(description="Bóc hardsub tiếng Trung từ video ra file .srtpx")
    ap.add_argument("video", help="Đường dẫn file video đầu vào")
    ap.add_argument("-o", "--output", required=True, help="File .srtpx đầu ra")
    ap.add_argument("--fps", type=float, default=30.0, help="FPS lấy mẫu khung hình (mặc định 30)")
    ap.add_argument("--roi", default="0,0,1.0,1.0",
                     help="Vùng chứa phụ đề, phân số x1,y1,x2,y2 (mặc định toàn khung hình)")
    ap.add_argument("--engine", choices=["tesseract", "easyocr", "paddleocr"], default="tesseract")
    ap.add_argument("--lang", default="chi_sim",
                     help="Mã ngôn ngữ OCR: tesseract='chi_sim'/'chi_tra', easyocr/paddleocr='ch'")
    ap.add_argument("--scale", type=float, default=2.0, help="Phóng to ROI trước khi OCR (giúp đọc chữ nhỏ)")
    ap.add_argument("--min-conf", type=float, default=0.4, help="Ngưỡng tin cậy OCR tối thiểu (0..1)")
    ap.add_argument("--similarity", type=float, default=0.72,
                     help="Ngưỡng giống nhau giữa 2 frame để coi là cùng 1 câu (0..1)")
    ap.add_argument("--max-gap-frames", type=int, default=2,
                     help="Số frame OCR trống liên tiếp tối đa vẫn coi là cùng 1 câu")
    ap.add_argument("--min-frames", type=int, default=2, help="Số frame tối thiểu để 1 câu được tính")
    ap.add_argument("--debug-dir", default=None, help="Thư mục lưu ảnh debug đã kẻ khung")
    ap.add_argument("--debug-every", type=int, default=15, help="Lưu debug mỗi N frame đã xử lý")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"Không mở được video: {args.video}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
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
        text, bbox = detect_frame_text(engine, roi_img, (rx0, ry0), args.scale)
        samples.append((t, text, bbox))

        if args.debug_dir and processed % args.debug_every == 0:
            save_debug_frame(frame, roi_px, bbox, os.path.join(args.debug_dir, f"f_{processed:06d}.jpg"))
        processed += 1
        if processed % 100 == 0:
            print(f"...đã xử lý {processed} frame (t={t:.1f}s)", file=sys.stderr)

    segments = build_segments(samples, similarity=args.similarity,
                               max_gap_frames=args.max_gap_frames, min_frames=args.min_frames)
    write_srtpx(segments, args.output)
    print(f"Xong: {len(segments)} câu phụ đề -> {args.output}")


if __name__ == "__main__":
    main()
