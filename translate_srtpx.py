#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dich noi dung file .srtpx (chu Trung) sang tieng Viet bang Gemini API.

Giu nguyen: #res, thoi gian, "Do rong", "Vi tri", cac dong KF.
Chi thay cac dong noi dung chu nam giua dong thoi gian va dong "Do rong".

- Nhieu key: dat GEMINI_API_KEYS="key1,key2,key3" (phan cach bang dau phay hoac xuong dong).
  Key het quota (429) -> doi sang key ke tiep. Key bi tu choi (400/401/403) -> loai key do.
- Loi tam thoi (429 o tat ca key, 5xx, mat mang, sai dinh dang): thu lai den khi duoc.
- Het key hop le, hoac sai ten model (404): dung ngay, thoat ma != 0.
- Chi ghi file ket qua khi DA DICH XONG toan bo (ghi qua file tam roi doi ten).

Dung:
    GEMINI_API_KEY=... python translate_srtpx.py video.srtpx
    python translate_srtpx.py video.srtpx -o video_vi.srtpx --keep-original video.zh.srtpx
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
KEY_REJECTED_HTTP = {400, 401, 403}  # key sai / bi khoa -> loai key do
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} --> ")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WIDTH_PREFIX = "Độ rộng"

PROMPT = (
    "Bạn là dịch giả phụ đề video. Dịch các câu phụ đề tiếng Trung dưới đây sang "
    "tiếng Việt tự nhiên, ngắn gọn, giữ đúng ý và giọng điệu. Các câu thuộc cùng một "
    "video và đang theo thứ tự thời gian, hãy dùng ngữ cảnh để dịch nhất quán. "
    "Giữ nguyên số và tên riêng nếu không cần dịch. "
    "Chỉ trả về một mảng JSON gồm các chuỗi, đúng {n} phần tử, đúng thứ tự, "
    "không thêm bất cứ thứ gì khác."
)


def log(msg):
    print(msg, flush=True)


CONFIG_EXIT = 2  # loi cau hinh (sai model, het key...): workflow KHONG duoc thu lai


def fatal(msg):
    print(msg, flush=True)
    sys.exit(CONFIG_EXIT)


class KeyPool:
    """Danh sach nhieu API key, xoay vong khi het quota hoac key bi tu choi."""

    def __init__(self, keys):
        self.keys = keys
        self.dead = set()
        self.i = 0

    def current(self):
        return self.keys[self.i]

    def alive(self):
        return [k for k in self.keys if k not in self.dead]

    def rotate(self):
        n = len(self.keys)
        for step in range(1, n + 1):
            j = (self.i + step) % n
            if self.keys[j] not in self.dead:
                self.i = j
                return

    def kill_current(self, why):
        self.dead.add(self.keys[self.i])
        if not self.alive():
            fatal("[LOI CAU HINH] Tat ca API key deu bi tu choi. Loi cuoi: %s" % why)
        self.rotate()


def load_keys():
    """Doc key tu GEMINI_API_KEYS (moi dong 1 key, vd secret GitHub), GEMINI_API_KEY,
    hoac file keys.txt canh script (chay tren may, moi dong 1 key)."""
    raw = os.environ.get("GEMINI_API_KEYS", "") + "\n" + os.environ.get("GEMINI_API_KEY", "")
    kf = os.environ.get("GEMINI_KEYS_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "keys.txt")
    if os.path.isfile(kf):
        with open(kf, "r", encoding="utf-8-sig") as f:
            raw += "\n" + f.read()
    keys = []
    for k in re.split(r"[,\s;]+", raw):
        if k and k not in keys:
            keys.append(k)
    return keys


def parse(text):
    """Tra ve (lines, cues). cue = (start, end) chi so dong noi dung (end khong tinh)."""
    lines = text.splitlines()
    cues = []
    i = 0
    while i < len(lines):
        if TIME_RE.match(lines[i]):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(WIDTH_PREFIX):
                j += 1
            if j > i + 1 and j < len(lines):
                cues.append((i + 1, j))
            i = j
        else:
            i += 1
    return lines, cues


def call_gemini(key, model, texts, timeout):
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": PROMPT.format(n=len(texts)) + "\n\n"
                       + json.dumps(texts, ensure_ascii=False)}],
        }],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        API.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    parts = data["candidates"][0]["content"]["parts"]
    raw = "".join(p.get("text", "") for p in parts).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def translate_chunk(pool, model, texts, timeout, label=""):
    attempt = 0
    bad_format = 0
    streak = 0  # so lan 429 lien tiep
    while True:
        attempt += 1
        try:
            out = call_gemini(pool.current(), model, texts, timeout)
            if (isinstance(out, list) and len(out) == len(texts)
                    and all(isinstance(x, str) and x.strip() for x in out)):
                return [x.strip() for x in out]
            raise ValueError("sai dinh dang / sai so phan tu")
        except urllib.error.HTTPError as e:
            detail = ""
            if e.code == 404 or e.code in KEY_REJECTED_HTTP:
                detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404:
                fatal("[LOI CAU HINH] Gemini tra ve 404: %s\n"
                      "Kiem tra ten model (GEMINI_MODEL)." % detail)
            if e.code == 400 and not re.search(r"api[ _]key", detail, re.I):
                fatal("[LOI CAU HINH] Gemini tra ve 400 (khong phai loi key, khong loai key nao): %s\n"
                      "Kiem tra ten model (GEMINI_MODEL) / noi dung gui." % detail)
            if e.code in KEY_REJECTED_HTTP:
                log("   %sKey #%d bi tu choi (%d), loai khoi danh sach" % (
                    label, pool.keys.index(pool.current()) + 1, e.code))
                pool.kill_current("%d %s" % (e.code, detail))
                continue
            if e.code == 429:
                pool.rotate()
                streak += 1
                if streak < len(pool.alive()):
                    log("   %sKey het quota (429), doi sang key khac" % label)
                    continue
                streak = 0  # tat ca key deu dang bi gioi han -> cho roi thu lai
            reason = "HTTP %d" % e.code
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
            bad_format += 1
            reason = "tra ve khong dung (%s)" % e
            if len(texts) > 1 and bad_format >= 2:
                mid = len(texts) // 2
                log("   %schia nho %d cau thanh 2 phan" % (label, len(texts)))
                return (translate_chunk(pool, model, texts[:mid], timeout, label)
                        + translate_chunk(pool, model, texts[mid:], timeout, label))
            if len(texts) == 1 and bad_format >= 8:
                log("   %sCANH BAO: khong dich duoc cau nay, giu nguyen ban goc: %r"
                    % (label, texts[0]))
                return texts
        except Exception as e:  # mat mang, timeout, ...
            reason = repr(e)
        wait = min(5 * 2 ** min(attempt - 1, 5), 60)
        log("   %sLoi lan %d (%s), thu lai sau %ds..." % (label, attempt, reason, wait))
        time.sleep(wait)


def main():
    ap = argparse.ArgumentParser(description="Dich .srtpx Trung -> Viet bang Gemini")
    ap.add_argument("input", help="File .srtpx can dich")
    ap.add_argument("-o", "--output", help="File dau ra (mac dinh ghi de len file vao)")
    ap.add_argument("--keep-original", help="Luu ban chua dich vao duong dan nay")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    ap.add_argument("--chunk", type=int, default=40, help="So cau moi lan goi API")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    keys = load_keys()
    if not keys:
        fatal("[LOI] Chua co API key: dat secret/bien GEMINI_API_KEYS (moi dong 1 key) hoac file keys.txt")
    pool = KeyPool(keys)

    with open(args.input, "r", encoding="utf-8-sig", newline="") as f:
        original = f.read()
    lines, cues = parse(original)

    # Chi dich cau co chu Han; cau khac (so, logo...) giu nguyen
    todo = []  # (chi so cue, noi dung)
    for n, (s, e) in enumerate(cues):
        t = " ".join(x.strip() for x in lines[s:e] if x.strip())
        if t and CJK_RE.search(t):
            todo.append((n, t))
    log("[DICH] %d cau, model %s, %d key" % (len(todo), args.model, len(keys)))

    translated = {}
    for k in range(0, len(todo), args.chunk):
        part = todo[k:k + args.chunk]
        label = "[%d-%d/%d] " % (k + 1, k + len(part), len(todo))
        res = translate_chunk(pool, args.model, [t for _, t in part], args.timeout, label)
        for (n, _), vi in zip(part, res):
            translated[n] = vi
        log("   %sxong" % label)

    # Ghep lai, di tu cuoi len de chi so dong khong bi lech
    for n in sorted(translated, reverse=True):
        s, e = cues[n]
        lines[s:e] = [translated[n]]

    out_text = "\r\n".join(lines) + ("\r\n" if original.endswith("\n") else "")
    dest = args.output or args.input
    if args.keep_original:
        shutil.copyfile(args.input, args.keep_original)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(out_text)
    os.replace(tmp, dest)
    log("[OK] Da dich xong %d cau -> %s" % (len(translated), dest))


if __name__ == "__main__":
    main()
