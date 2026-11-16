@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Boc hardsub - lan dau se cai dat, vui long doi

where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Chua co Python. Hay tai Python 3.10 hoac 3.11 tai https://www.python.org/downloads/
  echo Nho TICH vao o "Add python.exe to PATH" khi cai, roi bam lai file nay.
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Tao moi truong rieng...
  %PY% -m venv .venv || (echo Loi tao moi truong & pause & exit /b 1)
)

if not exist ".venv\installed.flag" (
  echo [2/3] Cai thu vien - lan dau mat vai phut, can co mang...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install "numpy<2" opencv-python-headless pillow pytesseract
  ".venv\Scripts\python.exe" -m pip install "paddlepaddle>=2.6,<3" "paddleocr>=2.7,<3"
  if errorlevel 1 (echo Cai that bai. Kiem tra mang roi chay lai. & pause & exit /b 1)
  echo ok> ".venv\installed.flag"
)

echo [3/3] Mo chuong trinh...
".venv\Scripts\python.exe" hardsub_gui.py
