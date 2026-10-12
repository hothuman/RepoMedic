# Pack a previously built dist\RepoMedic folder and write a SHA256 checksum.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Missing .venv Python' }
$version = (& $python -c 'from version import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid application version' }
$exe = Join-Path (Get-Location) 'dist\RepoMedic\RepoMedic.exe'
if (-not (Test-Path $exe)) { throw 'Build dist\RepoMedic\RepoMedic.exe first' }
New-Item -ItemType Directory -Force release | Out-Null
$filename = "RepoMedic-Windows-x64-v$version.zip"
$zip = Join-Path (Get-Location) "release\$filename"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path 'dist\RepoMedic' -DestinationPath $zip -CompressionLevel Optimal
if (-not (Test-Path $zip)) { throw 'Windows ZIP creation failed' }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
Set-Content -LiteralPath 'release\SHA256SUMS.txt' -Value "$hash  $filename" -Encoding ascii
Write-Host "Package created: release\$filename" -ForegroundColor Green
Write-Host "SHA256: $hash"
