#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Cần cài Python 3.10/3.11 từ python.org"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
if [ ! -f .venv/installed.flag ]; then
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install "numpy<2" opencv-python-headless pillow pytesseract
  .venv/bin/pip install "paddlepaddle>=2.6,<3" "paddleocr>=2.7,<3" && touch .venv/installed.flag
fi
.venv/bin/python hardsub_gui.py
