@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Kiem tra thong tin con thieu - hardsub

rem ====== CAU HINH (khop voi Apps Script va workflow) ======
set "OWNER=banminhduc33-source"
set "REPO=hardsub-extract-tool"
set "WF=hardsub.yml"
set "REF=main"
set "REMOTE=gdrive"
set "REPORT=%~dp0bao_cao_hardsub.txt"
set "MISSING=0"

> "%REPORT%" echo BAO CAO KIEM TRA - %date% %time%
call :log "Thu muc dang kiem tra: %~dp0"
call :log ""

rem ================= [1] GIT =================
call :log "===== [1] GIT / REPO ====="
where git >nul 2>&1
if errorlevel 1 (
  call :miss "Chua cai git. Cai: winget install Git.Git"
  goto :sec2
)
set "RURL="
for /f "delims=" %%U in ('git remote get-url origin 2^>nul') do set "RURL=%%U"
if "%RURL%"=="" (
  call :miss "Thu muc nay chua phai repo git hoac chua co remote origin. Hay dat file bat vao thu muc goc repo."
) else (
  call :ok "Remote origin: %RURL%"
)
set "BR="
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BR=%%B"
if not "%BR%"=="" (
  call :log "Nhanh hien tai: %BR%"
  if /i not "%BR%"=="%REF%" call :miss "Nhanh hien tai la %BR% nhung CONFIG.REF trong Apps Script la %REF%. Sua cho khop."
)

:sec2
rem ================= [2] FILE TRONG REPO =================
call :log ""
call :log "===== [2] FILE TRONG REPO ====="

if exist "requirements-ci.txt" (
  call :ok "Co requirements-ci.txt"
) else (
  call :miss "Thieu requirements-ci.txt - buoc setup-python se loi. Da tao file goi y: requirements-ci.txt.goi_y"
  > "requirements-ci.txt.goi_y" (
    echo paddlepaddle
    echo paddleocr
    echo opencv-python-headless
    echo numpy
    echo rem Day chi la goi y. Hay sua theo cac import trong hardsub_extract.py roi doi ten thanh requirements-ci.txt
  )
)

if exist "hardsub_extract.py" (
  call :ok "Co hardsub_extract.py"
  for %%A in (--engine --lang --fps --roi --debug-dir --debug-every) do (
    findstr /c:"%%A" "hardsub_extract.py" >nul 2>&1
    if errorlevel 1 (
      call :miss "hardsub_extract.py chua thay tham so %%A"
    ) else (
      call :ok "hardsub_extract.py co tham so %%A"
    )
  )
  set "HASO=0"
  findstr /c:"'-o'" "hardsub_extract.py" >nul 2>&1 && set "HASO=1"
  findstr /c:"\"-o\"" "hardsub_extract.py" >nul 2>&1 && set "HASO=1"
  if "%HASO%"=="1" (
    call :ok "hardsub_extract.py co tham so -o"
  ) else (
    call :miss "hardsub_extract.py chua thay tham so -o"
  )
) else (
  call :miss "Thieu hardsub_extract.py o thu muc goc repo"
)

if exist "output\" (
  call :ok "Co thu muc output"
) else (
  mkdir output >nul 2>&1
  > "output\.gitkeep" echo.
  call :log "[DA TAO] Thu muc output kem .gitkeep - nho git add va push"
)

set "WFP=.github\workflows\%WF%"
if exist "%WFP%" (
  call :ok "Co workflow %WFP%"
  findstr /c:"workflow_dispatch" "%WFP%" >nul 2>&1
  if errorlevel 1 (call :miss "Workflow thieu workflow_dispatch - Apps Script se bi loi 404 hoac 422") else (call :ok "Workflow co workflow_dispatch")
  findstr /c:"*.m4v" "%WFP%" >nul 2>&1
  if errorlevel 1 call :miss "Lenh find trong workflow thieu m4v va wmv - video duoi nay se khong duoc xu ly"
  findstr /c:"--ignore-case" "%WFP%" >nul 2>&1
  if errorlevel 1 call :miss "rclone lsf chua co --ignore-case - file viet hoa nhu VIDEO.MP4 se bi bo sot"
) else (
  call :miss "Khong thay %WFP% - sua bien WF o dau file bat neu ten khac"
)

rem Kiem tra phien ban paddleocr de biet thu muc cache model
set "PV="
for /f "tokens=2" %%V in ('pip show paddleocr 2^>nul ^| findstr /b /c:"Version"') do set "PV=%%V"
if "%PV%"=="" (
  call :log "[INFO] May nay chua cai paddleocr nen khong biet phien ban. Tu kiem tra requirements-ci.txt."
) else (
  call :log "[INFO] paddleocr phien ban %PV%"
  set "PV1=%PV:~0,1%"
  if "%PV1%"=="3" call :miss "PaddleOCR 3.x luu model o ~/.paddlex - doi path cache trong workflow tu ~/.paddleocr sang ~/.paddlex"
)

rem ================= [3] RCLONE / DRIVE =================
call :log ""
call :log "===== [3] RCLONE / GOOGLE DRIVE ====="
set "RCFG="
where rclone >nul 2>&1
if errorlevel 1 (
  call :miss "Chua cai rclone. Cai: winget install Rclone.Rclone  roi chay: rclone config  de tao remote ten %REMOTE%"
  goto :sec4
)
for /f "delims=" %%P in ('rclone config file 2^>nul ^| findstr /i "rclone.conf"') do set "RCFG=%%P"
call :log "File cau hinh rclone: %RCFG%"
if "%RCFG%"=="" (
  call :miss "Khong tim thay rclone.conf. Chay: rclone config"
  goto :sec4
)
if not exist "%RCFG%" (
  call :miss "File rclone.conf chua ton tai. Chay: rclone config"
  goto :sec4
)

rclone listremotes 2>nul | findstr /i /b /c:"%REMOTE%:" >nul 2>&1
if errorlevel 1 (
  call :miss "Trong rclone.conf khong co remote ten %REMOTE%. Cac remote hien co:"
  rclone listremotes
  goto :sec4
) else (
  call :ok "Co remote %REMOTE%"
)

rem Hien thong tin remote nhung khong in token
call :log "Thong tin remote - da an token:"
rclone config show %REMOTE% 2>nul | findstr /i /b /c:"type" /c:"scope" /c:"root_folder_id" /c:"service_account_file" >> "%REPORT%"
rclone config show %REMOTE% 2>nul | findstr /i /b /c:"type" /c:"scope" /c:"root_folder_id" /c:"service_account_file"
rclone config show %REMOTE% 2>nul | findstr /i /c:"scope = drive.file" >nul 2>&1
if not errorlevel 1 call :miss "scope la drive.file - se khong thay thu muc srtpx. Doi sang scope drive"
rclone config show %REMOTE% 2>nul | findstr /i /b /c:"scope" >nul 2>&1
if errorlevel 1 call :log "[INFO] Khong thay dong scope. Neu dung service account thi can chia se thu muc srtpx cho email cua no."

rclone lsd "%REMOTE%:srtpx" >nul 2>&1
if errorlevel 1 (
  call :miss "Khong vao duoc %REMOTE%:srtpx - kiem tra thu muc srtpx o goc My Drive"
) else (
  call :ok "Vao duoc %REMOTE%:srtpx"
)
rclone lsd "%REMOTE%:srtpx/in" >nul 2>&1
if errorlevel 1 (
  call :miss "Khong vao duoc %REMOTE%:srtpx/in - tao thu muc in ben trong srtpx"
) else (
  call :ok "Vao duoc %REMOTE%:srtpx/in"
  set "NV=0"
  set "NS=0"
  for /f %%N in ('rclone lsf "%REMOTE%:srtpx/in" --ignore-case --include "*.{mp4,mkv,avi,mov,flv,webm,m4v,ts,wmv}" 2^>nul ^| find /c /v ""') do set "NV=%%N"
  for /f %%N in ('rclone lsf "%REMOTE%:srtpx/in" --ignore-case --include "*.srtpx" 2^>nul ^| find /c /v ""') do set "NS=%%N"
  call :log "Trong srtpx/in: %NV% video, %NS% file srtpx"
)
set "NF=0"
for /f %%N in ('rclone lsf "%REMOTE%:" --dirs-only 2^>nul ^| findstr /i /x /c:"srtpx/" ^| find /c /v ""') do set "NF=%%N"
if not "%NF%"=="1" if not "%NF%"=="0" call :miss "Co %NF% thu muc srtpx trung ten o goc Drive - chi giu 1"

:sec4
rem ================= [4] GITHUB SECRET RCLONE_CONF =================
call :log ""
call :log "===== [4] SECRET RCLONE_CONF TREN GITHUB ====="
where gh >nul 2>&1
if errorlevel 1 (
  call :log "[INFO] Chua cai GitHub CLI gh - cai bang: winget install GitHub.cli  roi: gh auth login"
  call :log "Cach thu cong: GitHub, Settings, Secrets and variables, Actions, New repository secret, ten RCLONE_CONF, noi dung la file rclone.conf"
  if not "%RCFG%"=="" if exist "%RCFG%" (
    choice /c YN /t 20 /d N /m "Copy noi dung rclone.conf vao clipboard de dan vao secret"
    if not errorlevel 2 (
      clip < "%RCFG%"
      call :log "Da copy rclone.conf vao clipboard. NHO xoa clipboard sau khi dan."
    )
  )
  goto :sec5
)
gh auth status >nul 2>&1
if errorlevel 1 (
  call :miss "gh chua dang nhap. Chay: gh auth login"
  goto :sec5
)
call :ok "gh da dang nhap"
set "HAS_SECRET=0"
gh secret list -R %OWNER%/%REPO% 2>nul | findstr /b /c:"RCLONE_CONF" >nul 2>&1 && set "HAS_SECRET=1"
if "%HAS_SECRET%"=="1" (
  call :ok "Secret RCLONE_CONF da co tren repo"
) else (
  call :miss "Repo chua co secret RCLONE_CONF"
  if not "%RCFG%"=="" if exist "%RCFG%" (
    choice /c YN /t 20 /d N /m "Tai rclone.conf len GitHub thanh secret RCLONE_CONF ngay bay gio"
    if not errorlevel 2 (
      gh secret set RCLONE_CONF -R %OWNER%/%REPO% < "%RCFG%"
      if errorlevel 1 (call :log "[LOI] Khong tao duoc secret") else (call :log "[DA TAO] Secret RCLONE_CONF")
    )
  )
)
for /f "delims=" %%D in ('gh api repos/%OWNER%/%REPO% --jq .default_branch 2^>nul') do set "DEFBR=%%D"
if not "%DEFBR%"=="" call :log "Nhanh mac dinh tren GitHub: %DEFBR%"
gh workflow list -R %OWNER%/%REPO% 2>nul | findstr /i /c:"%WF%" >nul 2>&1
if errorlevel 1 (
  gh workflow list -R %OWNER%/%REPO% 2>nul | findstr /i /c:"Boc hardsub" >nul 2>&1
  if errorlevel 1 call :miss "GitHub chua nhan workflow %WF% - nho commit va push thu muc .github"
) else (
  call :ok "GitHub da nhan workflow"
)

:sec5
rem ================= [5] KIEM TRA TOKEN GITHUB =================
call :log ""
call :log "===== [5] KIEM TRA GITHUB TOKEN CHO APPS SCRIPT ====="
where curl >nul 2>&1
if errorlevel 1 (
  call :log "[INFO] Khong co curl - bo qua kiem tra token"
  goto :sec6
)
set "TOKEN="
echo Dan GitHub token de kiem tra, hoac nhan Enter de bo qua.
echo Token chi dung trong cua so nay, khong duoc ghi vao bao cao.
set /p "TOKEN=Token: "
if "%TOKEN%"=="" (
  call :miss "Chua kiem tra token. Tao token: GitHub, Settings, Developer settings, Personal access tokens"
  goto :sec6
)
set "HF=%TEMP%\gh_head.txt"
curl -s -D "%HF%" -o nul -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/%OWNER%/%REPO%/actions/workflows/%WF%"
set "CODE="
for /f "tokens=2" %%C in ('findstr /b /i "HTTP/" "%HF%"') do set "CODE=%%C"
call :log "GitHub tra ve ma: %CODE%"
if "%CODE%"=="200" (
  call :ok "Token doc duoc workflow %WF%"
) else if "%CODE%"=="401" (
  call :miss "Token sai hoac het han"
) else if "%CODE%"=="404" (
  call :miss "Token khong thay repo hoac workflow. Fine-grained token phai chon dung repo va cap Actions Read and write"
) else (
  call :miss "Ma khong mong doi %CODE% - xem lai token"
)
findstr /i /b /c:"x-oauth-scopes" "%HF%" >> "%REPORT%"
findstr /i /b /c:"x-oauth-scopes" "%HF%"
del "%HF%" >nul 2>&1

if "%CODE%"=="200" (
  echo.
  echo Quyen ghi Actions chi xac nhan duoc bang cach gui lenh chay that.
  choice /c YN /t 20 /d N /m "Gui lenh chay workflow that de thu token"
  if not errorlevel 2 (
    set "DC="
    for /f %%C in ('curl -s -o nul -w "%%{http_code}" -X POST -H "Authorization: Bearer %TOKEN%" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" -d "{\"ref\":\"%REF%\"}" "https://api.github.com/repos/%OWNER%/%REPO%/actions/workflows/%WF%/dispatches"') do set "DC=%%C"
    if "%DC%"=="204" (
      call :ok "Dispatch thanh cong ma 204 - workflow dang chay"
    ) else (
      call :miss "Dispatch that bai ma %DC% - token thieu quyen Actions Read and write hoac REF sai"
    )
  )
)

:sec6
rem ================= [6] TAO APPS SCRIPT DA DIEN SAN =================
call :log ""
call :log "===== [6] TAO APPS SCRIPT DA DIEN SAN VA COPY VAO CLIPBOARD ====="
if "%TOKEN%"=="" (
  echo.
  echo Dan GitHub token de dien vao saveToken, hoac Enter de de nguyen DAN_TOKEN_VAO_DAY.
  set /p "TOKEN=Token: "
)
set "AS_OWNER=%OWNER%"
set "AS_REPO=%REPO%"
set "AS_WF=%WF%"
set "AS_REF=%REF%"
if not "%BR%"=="" set "AS_REF=%BR%"
if not "%DEFBR%"=="" set "AS_REF=%DEFBR%"
set "AS_URL=%RURL%"
set "AS_TOKEN=%TOKEN%"
set "AS_SELF=%~f0"
set "AS_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:AS_SELF | Where-Object {$_ -like '::PS::*'} | ForEach-Object {$_.Substring(6)}; iex ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($l -join ''))))"
if errorlevel 1 (
  call :miss "Khong tao duoc Apps Script"
) else (
  call :ok "Da copy Apps Script vao clipboard - mo Apps Script, Ctrl+A, Ctrl+V, Luu"
)
set "TOKEN="
set "AS_TOKEN="

:done
call :log ""
call :log "===== TONG KET ====="
if "%MISSING%"=="0" (
  call :log "Khong phat hien thieu sot nao."
) else (
  call :log "Con %MISSING% muc can xu ly - xem cac dong THIEU o tren."
)
echo.
echo Bao cao da luu tai: %REPORT%
echo Cac viec can lam thu cong khac:
echo   - Dan code tu clipboard vao Apps Script, Luu, chay saveToken roi XOA token khoi code
echo   - Chay installTrigger trong Apps Script mot lan
echo   - Dat OAuth app o che do In production neu dung token Google loai Testing
echo.
pause
exit /b 0

rem ================= HAM PHU =================
:log
echo %~1
>> "%REPORT%" echo %~1
exit /b 0

:ok
echo [OK]    %~1
>> "%REPORT%" echo [OK]    %~1
exit /b 0

:miss
set /a MISSING+=1
echo [THIEU] %~1
>> "%REPORT%" echo [THIEU] %~1
exit /b 0

rem ===== DU LIEU NHUNG SAN - KHONG SUA PHIA DUOI =====
::PS::JEVycm9yQWN0aW9uUHJlZmVyZW5jZSA9ICdTdG9wJwokZGlyID0gJGVudjpBU19ESVIKJGxpbmVzID0gR2V0LUNvbnRlbnQgLUxp
::PS::dGVyYWxQYXRoICRlbnY6QVNfU0VMRiB8IFdoZXJlLU9iamVjdCB7ICRfIC1saWtlICc6OkdTOjoqJyB9IHwgRm9yRWFjaC1PYmpl
::PS::Y3QgeyAkXy5TdWJzdHJpbmcoNikgfQokdGV4dCA9IFtUZXh0LkVuY29kaW5nXTo6VVRGOC5HZXRTdHJpbmcoW0NvbnZlcnRdOjpG
::PS::cm9tQmFzZTY0U3RyaW5nKCgkbGluZXMgLWpvaW4gJycpKSkKJG93bmVyID0gJGVudjpBU19PV05FUgokcmVwbyAgPSAkZW52OkFT
::PS::X1JFUE8KJHdmICAgID0gJGVudjpBU19XRgokcmVmICAgPSAkZW52OkFTX1JFRgokdG9rZW4gPSAkZW52OkFTX1RPS0VOCiR1cmwg
::PS::ICA9ICRlbnY6QVNfVVJMCmlmICgkdXJsIC1tYXRjaCAnZ2l0aHViXC5jb21bOi9dKFteL10rKS8oW14vXSs/KShcLmdpdCk/Lz8k
::PS::JykgeyAkb3duZXIgPSAkTWF0Y2hlc1sxXTsgJHJlcG8gPSAkTWF0Y2hlc1syXSB9CiR3ZkRpciA9IEpvaW4tUGF0aCAkZGlyICcu
::PS::Z2l0aHViXHdvcmtmbG93cycKaWYgKFRlc3QtUGF0aCAkd2ZEaXIpIHsKICAgIGlmICgtbm90IChUZXN0LVBhdGggKEpvaW4tUGF0
::PS::aCAkd2ZEaXIgJHdmKSkpIHsKICAgICAgICAkZiA9IEdldC1DaGlsZEl0ZW0gJHdmRGlyIC1GaWxlIHwgV2hlcmUtT2JqZWN0IHsg
::PS::JF8uRXh0ZW5zaW9uIC1pbiAnLnltbCcsICcueWFtbCcgfSB8IFNlbGVjdC1PYmplY3QgLUZpcnN0IDEKICAgICAgICBpZiAoJGYp
::PS::IHsgJHdmID0gJGYuTmFtZSB9CiAgICB9Cn0KJHRleHQgPSAkdGV4dC5SZXBsYWNlKCdfX09XTkVSX18nLCAkb3duZXIpLlJlcGxh
::PS::Y2UoJ19fUkVQT19fJywgJHJlcG8pLlJlcGxhY2UoJ19fV0ZfXycsICR3ZikuUmVwbGFjZSgnX19SRUZfXycsICRyZWYpCiRoYXNU
::PS::b2tlbiA9IC1ub3QgW3N0cmluZ106OklzTnVsbE9yV2hpdGVTcGFjZSgkdG9rZW4pCmlmICgkaGFzVG9rZW4pIHsKICAgICRzYWZl
::PS::ID0gJHRva2VuLlRyaW0oKS5SZXBsYWNlKCdcJywgJ1xcJykuUmVwbGFjZSgiJyIsICJcJyIpCiAgICAkY2xpcCA9ICR0ZXh0LlJl
::PS::cGxhY2UoJ19fVE9LRU5fXycsICRzYWZlKQp9IGVsc2UgewogICAgJGNsaXAgPSAkdGV4dC5SZXBsYWNlKCdfX1RPS0VOX18nLCAn
::PS::REFOX1RPS0VOX1ZBT19EQVknKQp9ClNldC1DbGlwYm9hcmQgLVZhbHVlICRjbGlwCldyaXRlLUhvc3QgJycKV3JpdGUtSG9zdCAn
::PS::RGEgZGllbiB2YW8gQXBwcyBTY3JpcHQ6JwpXcml0ZS1Ib3N0ICIgIE9XTkVSICAgICAgICAgPSAkb3duZXIiCldyaXRlLUhvc3Qg
::PS::IiAgUkVQTyAgICAgICAgICA9ICRyZXBvIgpXcml0ZS1Ib3N0ICIgIFdPUktGTE9XX0ZJTEUgPSAkd2YiCldyaXRlLUhvc3QgIiAg
::PS::UkVGICAgICAgICAgICA9ICRyZWYiCmlmICgkaGFzVG9rZW4pIHsgV3JpdGUtSG9zdCAnICBHSVRIVUJfVE9LRU4gID0gZGEgZGll
::PS::biB0cm9uZyBjbGlwYm9hcmQnIH0gZWxzZSB7IFdyaXRlLUhvc3QgJyAgR0lUSFVCX1RPS0VOICA9IGNodWEgY28sIHZhbiBsYSBE
::PS::QU5fVE9LRU5fVkFPX0RBWScgfQpXcml0ZS1Ib3N0ICcnCldyaXRlLUhvc3QgJ1RvYW4gYm8gY29kZSBBcHBzIFNjcmlwdCBkYSBu
::PS::YW0gdHJvbmcgY2xpcGJvYXJkLicKZXhpdCAwCg==
::GS::Ly8vID09PT09PSBD4bqkVSBIw4xOSCA9PT09PT0KY29uc3QgQ09ORklHID0gewogIE9XTkVSOiAnX19PV05FUl9fJywKICBSRVBP
::GS::OiAnX19SRVBPX18nLAogIFdPUktGTE9XX0ZJTEU6ICdfX1dGX18nLCAgIC8vIHTDqm4gZmlsZSB0cm9uZyAuZ2l0aHViL3dvcmtm
::GS::bG93cy8gKHPhu61hIG7hur91IGtow6FjKQogIFJFRjogJ19fUkVGX18nLCAgICAgICAgICAgICAgICAgICAgLy8gbmjDoW5oIGNo
::GS::4bupYSB3b3JrZmxvdyAobWFpbiBob+G6t2MgbWFzdGVyKQogIFJPT1RfRk9MREVSOiAnc3J0cHgnLCAgICAgICAgICAgLy8gdGjG
::GS::sCBt4bulYyBn4buRYyB0csOqbiBEcml2ZQogIElOX0ZPTERFUjogJ2luJywgICAgICAgICAgICAgICAgLy8gdmlkZW8gdsOgbyDE
::GS::kcOieSwgZmlsZSAuc3J0cHggY8WpbmcgxJHGsOG7o2MgdHLhuqMgduG7gSDEkcOieQogIFZJREVPX0VYVDogWydtcDQnLCAnbWt2
::GS::JywgJ2F2aScsICdtb3YnLCAnZmx2JywgJ3dlYm0nLCAnbTR2JywgJ3RzJywgJ3dtdiddLAogIE1JTl9BR0VfTVM6IDIgKiA2MCAq
::GS::IDEwMDAsICAgICAgICAgIC8vIGLhu48gcXVhIGZpbGUgbeG7m2kgc+G7rWEgPCAyIHBow7p0ICjEkWFuZyB1cGxvYWQgZOG7nykK
::GS::ICBSRVRSWV9BRlRFUl9NUzogNyAqIDYwICogNjAgKiAxMDAwLCAvLyBzYXUgNyBnaeG7nSB24bqrbiBjaMawYSBjw7Mga+G6v3Qg
::GS::cXXhuqMgdGjDrCBn4buNaSBs4bqhaQp9OwoKLy8gPT09PT09IEPDgEkgxJDhurZUIChjaOG6oXkgMSBs4bqnbiBt4buXaSBow6Bt
::GS::KSA9PT09PT0KCi8vIFThuqFvIHRyaWdnZXIgcXXDqXQgbeG7l2kgcGjDunQKZnVuY3Rpb24gaW5zdGFsbFRyaWdnZXIoKSB7CiAg
::GS::U2NyaXB0QXBwLmdldFByb2plY3RUcmlnZ2VycygpLmZvckVhY2godCA9PiB7CiAgICBpZiAodC5nZXRIYW5kbGVyRnVuY3Rpb24o
::GS::KSA9PT0gJ2NoZWNrTmV3VmlkZW9zJykgU2NyaXB0QXBwLmRlbGV0ZVRyaWdnZXIodCk7CiAgfSk7CiAgU2NyaXB0QXBwLm5ld1Ry
::GS::aWdnZXIoJ2NoZWNrTmV3VmlkZW9zJykudGltZUJhc2VkKCkuZXZlcnlNaW51dGVzKDEpLmNyZWF0ZSgpOwogIExvZ2dlci5sb2co
::GS::J8SQw6MgdOG6oW8gdHJpZ2dlciBxdcOpdCBt4buXaSAxIHBow7p0LicpOwp9CgovLyBMxrB1IHRva2VuIEdpdEh1YiAoZMOhbiB0
::GS::b2tlbiB2w6BvLCBjaOG6oXkgeG9uZyB0aMOsIFjDk0EgdG9rZW4ga2jhu49pIGNvZGUpCmZ1bmN0aW9uIHNhdmVUb2tlbigpIHsK
::GS::ICBQcm9wZXJ0aWVzU2VydmljZS5nZXRTY3JpcHRQcm9wZXJ0aWVzKCkuc2V0UHJvcGVydHkoJ0dJVEhVQl9UT0tFTicsICdfX1RP
::GS::S0VOX18nKTsKfQoKLy8gPT09PT09IEjDgE0gQ0jDjU5IID09PT09PQpmdW5jdGlvbiBjaGVja05ld1ZpZGVvcygpIHsKICBjb25z
::GS::dCBsb2NrID0gTG9ja1NlcnZpY2UuZ2V0U2NyaXB0TG9jaygpOwogIGlmICghbG9jay50cnlMb2NrKDEwMDAwKSkgcmV0dXJuOwog
::GS::IHRyeSB7CiAgICBjb25zdCByb290ID0gZ2V0Rm9sZGVyXyhudWxsLCBDT05GSUcuUk9PVF9GT0xERVIpOwogICAgaWYgKCFyb290
::GS::KSByZXR1cm4gTG9nZ2VyLmxvZygnS2jDtG5nIHRo4bqleSB0aMawIG3hu6VjICcgKyBDT05GSUcuUk9PVF9GT0xERVIpOwogICAg
::GS::Y29uc3QgaW5GID0gZ2V0Rm9sZGVyXyhyb290LCBDT05GSUcuSU5fRk9MREVSKTsKICAgIGlmICghaW5GKSByZXR1cm4gTG9nZ2Vy
::GS::LmxvZygnS2jDtG5nIHRo4bqleSB0aMawIG3hu6VjICcgKyBDT05GSUcuSU5fRk9MREVSKTsKCiAgICAvLyBMxrDhu6N0IDE6IGdv
::GS::bSBjw6FjIC5zcnRweCDEkcOjIGPDsyB0cm9uZyBpbi8KICAgIGNvbnN0IGRvbmUgPSB7fTsKICAgIGNvbnN0IGFsbCA9IGluRi5n
::GS::ZXRGaWxlcygpOwogICAgd2hpbGUgKGFsbC5oYXNOZXh0KCkpIHsKICAgICAgY29uc3QgbiA9IGFsbC5uZXh0KCkuZ2V0TmFtZSgp
::GS::OwogICAgICBpZiAobi50b0xvd2VyQ2FzZSgpLmVuZHNXaXRoKCcuc3J0cHgnKSkgZG9uZVtuXSA9IHRydWU7CiAgICB9CgogICAg
::GS::Y29uc3QgcHJvcHMgPSBQcm9wZXJ0aWVzU2VydmljZS5nZXRTY3JpcHRQcm9wZXJ0aWVzKCk7CiAgICBjb25zdCBzZW50ID0gSlNP
::GS::Ti5wYXJzZShwcm9wcy5nZXRQcm9wZXJ0eSgnZGlzcGF0Y2hlZCcpIHx8ICd7fScpOwogICAgY29uc3Qgbm93ID0gRGF0ZS5ub3co
::GS::KTsKCiAgICAvLyBMxrDhu6N0IDI6IHTDrG0gdmlkZW8gY2jGsGEgY8OzIC5zcnRweCBj4bqhbmggbsOzCiAgICBjb25zdCBwZW5k
::GS::aW5nID0gW107CiAgICBjb25zdCBzdGlsbFRoZXJlID0ge307CiAgICBjb25zdCBmaWxlcyA9IGluRi5nZXRGaWxlcygpOwogICAg
::GS::d2hpbGUgKGZpbGVzLmhhc05leHQoKSkgewogICAgICBjb25zdCBmID0gZmlsZXMubmV4dCgpOwogICAgICBjb25zdCBuYW1lID0g
::GS::Zi5nZXROYW1lKCk7CiAgICAgIGNvbnN0IGRvdCA9IG5hbWUubGFzdEluZGV4T2YoJy4nKTsKICAgICAgaWYgKGRvdCA8IDApIGNv
::GS::bnRpbnVlOwogICAgICBjb25zdCBleHQgPSBuYW1lLnNsaWNlKGRvdCArIDEpLnRvTG93ZXJDYXNlKCk7CiAgICAgIGNvbnN0IHN0
::GS::ZW0gPSBuYW1lLnNsaWNlKDAsIGRvdCk7CiAgICAgIGlmIChDT05GSUcuVklERU9fRVhULmluZGV4T2YoZXh0KSA8IDApIGNvbnRp
::GS::bnVlOwogICAgICBpZiAoZG9uZVtzdGVtICsgJy5zcnRweCddKSBjb250aW51ZTsgICAgICAgICAgICAgICAgICAgICAgICAgICAg
::GS::ICAgICAgIC8vIMSRw6MgY8OzIGvhur90IHF14bqjCiAgICAgIGlmIChub3cgLSBmLmdldExhc3RVcGRhdGVkKCkuZ2V0VGltZSgp
::GS::IDwgQ09ORklHLk1JTl9BR0VfTVMpIGNvbnRpbnVlOyAgLy8gxJFhbmcgdXBsb2FkCiAgICAgIHN0aWxsVGhlcmVbZi5nZXRJZCgp
::GS::XSA9IHRydWU7CiAgICAgIGNvbnN0IGxhc3QgPSBzZW50W2YuZ2V0SWQoKV07CiAgICAgIGlmIChsYXN0ICYmIG5vdyAtIGxhc3Qg
::GS::PCBDT05GSUcuUkVUUllfQUZURVJfTVMpIGNvbnRpbnVlOyAgICAgICAgICAgICAgLy8gxJHDoyBn4buNaSwgxJFhbmcgY2jhu50K
::GS::ICAgICAgcGVuZGluZy5wdXNoKHsgaWQ6IGYuZ2V0SWQoKSwgbmFtZTogbmFtZSB9KTsKICAgIH0KCiAgICAvLyBE4buNbiBi4bqj
::GS::biBnaGkgY+G7p2EgZmlsZSDEkcOjIHhvbmcgLyDEkcOjIGLhu4sgeMOzYQogICAgT2JqZWN0LmtleXMoc2VudCkuZm9yRWFjaChp
::GS::ZCA9PiB7IGlmICghc3RpbGxUaGVyZVtpZF0pIGRlbGV0ZSBzZW50W2lkXTsgfSk7CgogICAgaWYgKHBlbmRpbmcubGVuZ3RoID4g
::GS::MCkgewogICAgICBMb2dnZXIubG9nKCdWaWRlbyBt4bubaTogJyArIHBlbmRpbmcubWFwKHAgPT4gcC5uYW1lKS5qb2luKCcsICcp
::GS::KTsKICAgICAgaWYgKGRpc3BhdGNoV29ya2Zsb3dfKCkpIHBlbmRpbmcuZm9yRWFjaChwID0+IHNlbnRbcC5pZF0gPSBub3cpOwog
::GS::ICAgfQogICAgcHJvcHMuc2V0UHJvcGVydHkoJ2Rpc3BhdGNoZWQnLCBKU09OLnN0cmluZ2lmeShzZW50KSk7CiAgfSBmaW5hbGx5
::GS::IHsKICAgIGxvY2sucmVsZWFzZUxvY2soKTsKICB9Cn0KCi8vID09PT09PSBIw4BNIFBI4bukID09PT09PQpmdW5jdGlvbiBnZXRG
::GS::b2xkZXJfKHBhcmVudCwgbmFtZSkgewogIGNvbnN0IGl0ID0gcGFyZW50ID8gcGFyZW50LmdldEZvbGRlcnNCeU5hbWUobmFtZSkg
::GS::OiBEcml2ZUFwcC5nZXRGb2xkZXJzQnlOYW1lKG5hbWUpOwogIHJldHVybiBpdC5oYXNOZXh0KCkgPyBpdC5uZXh0KCkgOiBudWxs
::GS::Owp9CgpmdW5jdGlvbiBkaXNwYXRjaFdvcmtmbG93XygpIHsKICBjb25zdCB0b2tlbiA9IFByb3BlcnRpZXNTZXJ2aWNlLmdldFNj
::GS::cmlwdFByb3BlcnRpZXMoKS5nZXRQcm9wZXJ0eSgnR0lUSFVCX1RPS0VOJyk7CiAgaWYgKCF0b2tlbikgeyBMb2dnZXIubG9nKCdD
::GS::aMawYSBjw7MgR0lUSFVCX1RPS0VOIChow6N5IGNo4bqheSBzYXZlVG9rZW4pJyk7IHJldHVybiBmYWxzZTsgfQogIGNvbnN0IHVy
::GS::bCA9ICdodHRwczovL2FwaS5naXRodWIuY29tL3JlcG9zLycgKyBDT05GSUcuT1dORVIgKyAnLycgKyBDT05GSUcuUkVQTyArCiAg
::GS::ICAgICAgICAgICAgJy9hY3Rpb25zL3dvcmtmbG93cy8nICsgQ09ORklHLldPUktGTE9XX0ZJTEUgKyAnL2Rpc3BhdGNoZXMnOwog
::GS::IGNvbnN0IHJlcyA9IFVybEZldGNoQXBwLmZldGNoKHVybCwgewogICAgbWV0aG9kOiAncG9zdCcsCiAgICBjb250ZW50VHlwZTog
::GS::J2FwcGxpY2F0aW9uL2pzb24nLAogICAgaGVhZGVyczogewogICAgICBBdXRob3JpemF0aW9uOiAnQmVhcmVyICcgKyB0b2tlbiwK
::GS::ICAgICAgQWNjZXB0OiAnYXBwbGljYXRpb24vdm5kLmdpdGh1Yitqc29uJywKICAgICAgJ1gtR2l0SHViLUFwaS1WZXJzaW9uJzog
::GS::JzIwMjItMTEtMjgnLAogICAgfSwKICAgIHBheWxvYWQ6IEpTT04uc3RyaW5naWZ5KHsgcmVmOiBDT05GSUcuUkVGIH0pLAogICAg
::GS::bXV0ZUh0dHBFeGNlcHRpb25zOiB0cnVlLAogIH0pOwogIGNvbnN0IGNvZGUgPSByZXMuZ2V0UmVzcG9uc2VDb2RlKCk7CiAgTG9n
::GS::Z2VyLmxvZygnR2l0SHViIHRy4bqjIHbhu4EgJyArIGNvZGUgKyAnICcgKyAoY29kZSA9PT0gMjA0ID8gJycgOiByZXMuZ2V0Q29u
::GS::dGVudFRleHQoKSkpOwogIHJldHVybiBjb2RlID09PSAyMDQ7Cn0K
