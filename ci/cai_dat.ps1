# Cai dat mot phat: Python (neu thieu) + thu vien + tao shortcut ngoai Desktop
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Say($m, $c = "Cyan") { Write-Host $m -ForegroundColor $c }

# ---- 1. Tim Python 3.9 - 3.12 (PaddleOCR chua ho tro 3.13+) ----
function Find-Python {
    $cands = @(@("py","-3.11"), @("py","-3.10"), @("py","-3.12"), @("py","-3.9"), @("python"))
    foreach ($c in $cands) {
        try {
            $exe = $c[0]; $args2 = @()
            if ($c.Count -gt 1) { $args2 = $c[1..($c.Count-1)] }
            $out = & $exe @args2 -c "import sys;print('%d.%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $v, $path = $out.Trim().Split("|", 2)
                $minor = [int]($v.Split(".")[1])
                if ($v.StartsWith("3.") -and $minor -ge 9 -and $minor -le 12 -and (Test-Path $path)) { return $path }
            }
        } catch { }
    }
    return $null
}

Say "=== [1/5] Kiem tra Python ==="
$py = Find-Python
if (-not $py) {
    Say "Chua co Python phu hop. Dang tu cai Python 3.11 (can mang)..." "Yellow"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Say "May khong co 'winget'. Hay tu cai Python 3.11 tai https://www.python.org/downloads/ (tich 'Add to PATH') roi chay lai file nay." "Red"
        exit 1
    }
    winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
    $py = Find-Python
    if (-not $py) {
        $guess = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
        if (Test-Path $guess) { $py = $guess }
    }
    if (-not $py) { Say "Cai Python xong nhung chua tim thay. Dong cua so nay, bam lai file cai dat 1 lan nua." "Red"; exit 1 }
}
Say "Dung Python: $py" "Green"

# ---- 2. Tao moi truong rieng ----
Say "=== [2/5] Tao moi truong rieng (.venv) ==="
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py -m venv .venv; if ($LASTEXITCODE -ne 0) { Say "Loi tao .venv" "Red"; exit 1 } }

# ---- 3. Cai thu vien ----
Say "=== [3/5] Cai thu vien (lan dau mat vai phut, can mang) ==="
$flag = Join-Path $Root ".venv\installed.flag"
if (-not (Test-Path $flag)) {
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install "numpy<2" opencv-python-headless pillow pytesseract
    if ($LASTEXITCODE -ne 0) { Say "Cai thu vien co ban that bai. Kiem tra mang roi chay lai." "Red"; exit 1 }
    & $venvPy -m pip install "paddlepaddle>=2.6,<3" "paddleocr>=2.7,<3"
    if ($LASTEXITCODE -ne 0) { Say "Cai PaddleOCR that bai. Kiem tra mang roi chay lai." "Red"; exit 1 }
    Set-Content -Path $flag -Value "ok"
} else { Say "Da cai truoc do, bo qua." "Green" }

# ---- 4. Kiem tra nhanh ----
Say "=== [4/5] Kiem tra ==="
& $venvPy -c "import cv2, numpy, paddleocr; print('OK: OpenCV', cv2.__version__)"
if ($LASTEXITCODE -ne 0) { Remove-Item $flag -ErrorAction SilentlyContinue; Say "Kiem tra loi, hay chay lai file cai dat." "Red"; exit 1 }

# ---- 5. Shortcut ngoai Desktop ----
Say "=== [5/5] Tao shortcut ngoai Desktop ==="
try {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Boc Hardsub.lnk"))
    $lnk.TargetPath = Join-Path $Root ".venv\Scripts\pythonw.exe"
    $lnk.Arguments = '"' + (Join-Path $Root "hardsub_gui.py") + '"'
    $lnk.WorkingDirectory = $Root
    $lnk.Description = "Boc hardsub tieng Trung ra .srtpx"
    $lnk.Save()
    Say "Da tao shortcut 'Boc Hardsub' ngoai Desktop." "Green"
} catch { Say "Khong tao duoc shortcut (khong sao, van dung duoc CHAY_WINDOWS.bat)." "Yellow" }

Say "`n*** CAI DAT XONG ***" "Green"
$ans = Read-Host "Mo chuong trinh ngay bay gio? (Y/N)"
if ($ans -match '^[Yy]') { Start-Process (Join-Path $Root ".venv\Scripts\pythonw.exe") -ArgumentList ('"' + (Join-Path $Root "hardsub_gui.py") + '"') -WorkingDirectory $Root }
