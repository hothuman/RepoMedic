# RepoMedic v1.0 - self-contained onedir Windows x64 build.
# Execute in PowerShell after installing requirements-build.txt into .venv.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw 'Missing .venv. Run: py -3.13 -m venv .venv (or use installed compatible Python)'
}
& $python scripts\check_release.py
if ($LASTEXITCODE -ne 0) { throw 'Version check failed.' }
& $python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'Install requirements-build.txt into your .venv.' }
& $python -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed. Refusing to package.' }
& $python scripts\smoke_gui.py
if ($LASTEXITCODE -ne 0) { throw 'GUI smoke test failed. Refusing to package.' }
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name RepoMedic `
    --icon 'assets/repomedic_logo.ico' --add-data 'assets/repomedic_logo.png;assets' main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$exe = Join-Path (Get-Location) 'dist\RepoMedic\RepoMedic.exe'
if (-not (Test-Path $exe)) { throw 'RepoMedic.exe is missing from the output.' }
Write-Host 'Windows onedir build created: dist\RepoMedic\RepoMedic.exe' -ForegroundColor Green
Write-Host 'Ship the complete dist\RepoMedic FOLDER, not only the EXE.' -ForegroundColor Yellow
