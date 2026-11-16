# Day code len Git bang 1 cai bam dup
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Say($m, $c = "Cyan") { Write-Host $m -ForegroundColor $c }
function Fail($m) { Say $m "Red"; exit 1 }

# ---- 1. Kiem tra git ----
Say "=== [1/5] Kiem tra Git ==="
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Say "May chua co Git. Dang thu tu cai bang winget..." "Yellow"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail "Chua co Git. Hay cai tai https://git-scm.com/download/win roi chay lai file nay."
    }
}
Say (git --version) "Green"

# ---- 2. Khoi tao repo neu chua co ----
Say "=== [2/5] Chuan bi repo ==="
if (-not (Test-Path (Join-Path $Root ".git"))) {
    git init -b main | Out-Null
    Say "Da khoi tao repo moi." "Green"
}
git branch -M main 2>$null

# ---- 3. Ten + email (chi hoi khi chua cau hinh) ----
$name  = (git config user.name)
$email = (git config user.email)
if (-not $name)  { $name  = Read-Host "Nhap ten cua ban (de ghi vao commit)";  git config user.name  $name }
if (-not $email) { $email = Read-Host "Nhap email cua ban (email GitHub/GitLab)"; git config user.email $email }

# ---- 4. Link repo tren GitHub/GitLab ----
Say "=== [3/5] Dia chi repo ==="
$remote = (git remote get-url origin 2>$null)
if (-not $remote) {
    Say "Tao 1 repo TRONG tren GitHub/GitLab truoc (khong tick README), roi dan link vao day." "Yellow"
    Say "Vi du: https://github.com/ten-ban/ten-repo.git" "Yellow"
    $remote = (Read-Host "Dan link repo").Trim()
    if (-not $remote) { Fail "Chua nhap link repo." }
    git remote add origin $remote
}
Say "Repo: $remote" "Green"

# ---- 5. Commit ----
Say "=== [4/5] Luu thay doi (commit) ==="
git add -A
$changes = git status --porcelain
if ($changes) {
    $msg = Read-Host "Ghi chu cho lan cap nhat nay (Enter = mac dinh)"
    if (-not $msg) { $msg = "Cap nhat " + (Get-Date -Format "yyyy-MM-dd HH:mm") }
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) { Fail "Commit that bai." }
} else {
    Say "Khong co thay doi moi, se day cac commit hien co." "Yellow"
}

# ---- 6. Push ----
Say "=== [5/5] Day len Git ==="
Say "Neu hien cua so dang nhap GitHub/GitLab thi hay dang nhap." "Yellow"
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Say "`nPush that bai. Nguyen nhan hay gap:" "Red"
    Say " - Link repo sai hoac chua tao repo tren web." "Red"
    Say " - Chua dang nhap / khong co quyen ghi vao repo." "Red"
    Say " - Repo tren web da co file (README...) nen bi tu choi. Tao lai repo TRONG, hoac nho Claude huong dan." "Red"
    exit 1
}
Say "`n*** DA DAY LEN GIT THANH CONG ***" "Green"
