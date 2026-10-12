# Windows-only launcher check. Tests start/quit, not complete GUI behavior.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$exe = Join-Path (Get-Location) 'dist\RepoMedic\RepoMedic.exe'
if (-not (Test-Path $exe)) { throw 'Run scripts\build_windows.ps1 first' }
$process = Start-Process -FilePath $exe -PassThru
try {
    Start-Sleep -Seconds 4
    $process.Refresh()
    if ($process.HasExited) { throw "Application exited early with code $($process.ExitCode)" }
    Write-Host 'Executable launched and remained running for 4 seconds.' -ForegroundColor Green
} finally {
    $process.Refresh()
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
}
