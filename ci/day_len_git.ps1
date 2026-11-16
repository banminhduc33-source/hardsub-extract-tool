# Day code len Git: bam dup 1 lan la xong, khong hoi gi (tru dang nhap GitHub lan dau)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# ===== CAU HINH (co the sua) =====
$RepoName   = "hardsub-extract-tool"   # ten repo se tu tao tren GitHub
$Visibility = "--private"              # doi thanh --public neu muon cong khai
$RemoteUrl  = ""                       # neu da co repo san: dan link vao day, vd https://github.com/ban/repo.git
# =================================

function Say($m, $c = "Cyan") { Write-Host $m -ForegroundColor $c }
function Fail($m) { Say $m "Red"; exit 1 }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") + ";C:\Program Files\GitHub CLI;C:\Program Files\Git\cmd" }
function Winget-Install($id) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements
        Refresh-Path
    }
}

# ---- 1. Git ----
Say "=== [1/4] Kiem tra Git ==="
Refresh-Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Say "Dang tu cai Git..." "Yellow"; Winget-Install "Git.Git" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "Khong cai duoc Git. Cai tay tai https://git-scm.com/download/win roi bam lai." }

if (-not (Test-Path (Join-Path $Root ".git"))) { git init -b main | Out-Null }
git branch -M main 2>$null

# ---- 2. Commit (tu dong, khong hoi) ----
Say "=== [2/4] Luu thay doi ==="
$gn = git config user.name;  if (-not $gn) { $gn = "hardsub" }
$ge = git config user.email; if (-not $ge) { $ge = "hardsub@users.noreply.github.com" }
git add -A
if (git status --porcelain) {
    git -c user.name="$gn" -c user.email="$ge" commit -q -m ("Cap nhat " + (Get-Date -Format "yyyy-MM-dd HH:mm"))
    if ($LASTEXITCODE -ne 0) { Fail "Commit that bai." }
    Say "Da commit." "Green"
} else { Say "Khong co thay doi moi." "Yellow" }

# ---- 3. Repo tren GitHub ----
Say "=== [3/4] Ket noi GitHub ==="
$hasOrigin = [bool](git remote get-url origin 2>$null)
if (-not $hasOrigin -and $RemoteUrl) { git remote add origin $RemoteUrl; $hasOrigin = $true }

if (-not $hasOrigin) {
    # Chua co repo: tu tao bang GitHub CLI (dang nhap qua trinh duyet 1 lan)
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { Say "Dang tu cai GitHub CLI..." "Yellow"; Winget-Install "GitHub.cli" }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Fail "Khong cai duoc GitHub CLI. Hay tao repo trong tren web, dan link vao dong `$RemoteUrl trong file ci\day_len_git.ps1 roi bam lai."
    }
    gh auth status 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Say "Se mo trinh duyet de ban dang nhap GitHub (chi lan dau). Lam theo huong dan tren man hinh." "Yellow"
        gh auth login -h github.com -p https -w
        if ($LASTEXITCODE -ne 0) { Fail "Dang nhap GitHub that bai." }
    }
    gh auth setup-git 2>$null | Out-Null
    Say "Dang tao repo '$RepoName' tren GitHub va day code len..." "Cyan"
    gh repo create $RepoName $Visibility --source . --remote origin --push
    if ($LASTEXITCODE -ne 0) { Fail "Tao repo that bai (ten co the da ton tai). Doi `$RepoName trong ci\day_len_git.ps1 roi bam lai." }
    Say "`n*** XONG: da tao repo va day len GitHub ***" "Green"
    gh repo view --web 2>$null | Out-Null
    exit 0
}

# ---- 4. Push ----
Say "=== [4/4] Day len Git ==="
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Say "`nPush that bai. Thuong do: chua dang nhap / khong co quyen ghi / repo tren web da co file san (README...)." "Red"
    exit 1
}
Say "`n*** DA DAY LEN GIT THANH CONG ***" "Green"
