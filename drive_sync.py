#!/usr/bin/env python3
"""
Google Drive  srtpx/in  ->  hardsub_extract.py  ->  Google Drive  srtpx/out

- Theo dõi thư mục srtpx/in trên Drive, thấy video mới thì tải về.
- Chạy hardsub_extract.py để bóc hardsub, ra file .srtpx.
- Tải file .srtpx lên srtpx/out (cùng tên với video).
- Video đã xử lý xong được đánh dấu trực tiếp trên Drive (appProperties),
  nên chạy lại hay chạy trên máy khác cũng không bị xử lý trùng.

Cài đặt:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

Chạy:
    python drive_sync.py                 # chạy liên tục, quét mỗi 30 giây
    python drive_sync.py --once          # quét một lần rồi thoát
    python drive_sync.py --extract-args "--engine paddleocr --lang ch --fps 12"
"""
import argparse
import os
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
HERE = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v", ".wmv"}
DONE_KEY = "hardsub_done"
FOLDER_MIME = "application/vnd.google-apps.folder"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get_service(cred_file, token_file):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_file).write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_folder(svc, name, parent):
    safe = name.replace("'", "\\'")
    q = (f"mimeType='{FOLDER_MIME}' and name='{safe}' and trashed=false "
         f"and '{parent}' in parents")
    res = svc.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    # Không có thì tự tạo
    body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
    folder = svc.files().create(body=body, fields="id").execute()
    log(f"Đã tạo thư mục '{name}' trên Drive")
    return folder["id"]


def list_pending(svc, in_id, settle_sec, failed):
    q = (f"'{in_id}' in parents and trashed=false and mimeType!='{FOLDER_MIME}'")
    res = svc.files().list(
        q=q, pageSize=100, orderBy="createdTime",
        fields="files(id,name,size,modifiedTime,appProperties)",
    ).execute()
    now = datetime.now(timezone.utc)
    pending = []
    for f in res.get("files", []):
        if Path(f["name"]).suffix.lower() not in VIDEO_EXT:
            continue
        if (f.get("appProperties") or {}).get(DONE_KEY):
            continue
        if f["id"] in failed:
            continue
        modified = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00"))
        if (now - modified).total_seconds() < settle_sec:
            continue  # có thể file còn đang tải lên
        pending.append(f)
    return pending


def process(svc, f, out_id, script, extract_args):
    name = f["name"]
    stem = Path(name).stem
    ext = Path(name).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{ext}"
        dst = Path(tmp) / "output.srtpx"

        log(f"Tải về: {name}")
        req = svc.files().get_media(fileId=f["id"])
        with open(src, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req, chunksize=32 * 1024 * 1024)
            done = False
            while not done:
                _, done = dl.next_chunk()

        log(f"Đang bóc hardsub: {name}")
        cmd = [sys.executable, str(script), str(src), "-o", str(dst)]
        cmd += shlex.split(extract_args)
        proc = subprocess.run(cmd)
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError(f"hardsub_extract.py lỗi (mã {proc.returncode})")

        log(f"Tải lên srtpx/out: {stem}.srtpx")
        media = MediaFileUpload(str(dst), mimetype="application/octet-stream",
                                resumable=True)
        svc.files().create(
            body={"name": f"{stem}.srtpx", "parents": [out_id]},
            media_body=media, fields="id",
        ).execute()

    svc.files().update(
        fileId=f["id"], body={"appProperties": {DONE_KEY: "1"}}
    ).execute()
    log(f"Xong: {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--credentials", default=str(HERE / "credentials.json"))
    ap.add_argument("--token", default=str(HERE / "token.json"))
    ap.add_argument("--root-name", default="srtpx", help="thư mục gốc trong My Drive")
    ap.add_argument("--in-name", default="in")
    ap.add_argument("--out-name", default="out")
    ap.add_argument("--script", default=str(HERE / "hardsub_extract.py"))
    ap.add_argument("--extract-args", default="--engine paddleocr --lang ch --fps 12",
                    help="tham số truyền thêm cho hardsub_extract.py")
    ap.add_argument("--interval", type=int, default=30, help="giây giữa mỗi lần quét")
    ap.add_argument("--settle", type=int, default=20,
                    help="bỏ qua file vừa sửa trong N giây gần đây (tránh file đang tải lên)")
    ap.add_argument("--once", action="store_true", help="quét một lần rồi thoát")
    args = ap.parse_args()

    svc = get_service(args.credentials, args.token)
    root_id = find_folder(svc, args.root_name, "root")
    in_id = find_folder(svc, args.in_name, root_id)
    out_id = find_folder(svc, args.out_name, root_id)
    log(f"Theo dõi Drive: {args.root_name}/{args.in_name}  ->  "
        f"{args.root_name}/{args.out_name}")

    failed = set()  # file lỗi trong lần chạy này, không thử lại liên tục
    while True:
        try:
            for f in list_pending(svc, in_id, args.settle, failed):
                try:
                    process(svc, f, out_id, args.script, args.extract_args)
                except Exception as e:  # noqa: BLE001
                    failed.add(f["id"])
                    log(f"LỖI với {f['name']}: {e}")
        except Exception as e:  # noqa: BLE001
            log(f"Lỗi khi quét Drive: {e}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
