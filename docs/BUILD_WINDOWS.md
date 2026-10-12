# Building RepoMedic v1.0 for Windows 11

The distributed source archive does **not** contain a tested `.exe`. PyInstaller must run on Windows, not Linux. GitHub Actions also builds it on Windows.

Use Python **3.13 64-bit** for the reproducible release configuration. To preserve your normal development environment (which may use Python 3.15), **copy the project to a clean separate directory** before building. Open PowerShell in that copy and run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_windows.ps1
.\scripts\smoke_exe.ps1
.\scripts\package_windows.ps1
```

If this copied folder already contains `.venv`, remove that **copied environment only** before creating the Python 3.13 environment. Never delete `.venv` from the original project.

Outputs:
- `dist\RepoMedic\RepoMedic.exe` — Windows entrypoint. **Ship the entire folder** `dist\RepoMedic` because the exe depends on bundled files.
- `release\RepoMedic-Windows-x64-v1.0.0.zip` — portable ZIP containing that folder.
- `release\SHA256SUMS.txt` — checksum. Verify with `Get-FileHash -Algorithm SHA256 release\RepoMedic-Windows-x64-v1.0.0.zip`.

The local build script runs unit and GUI smoke tests before building. `smoke_exe.ps1` only checks that the process launches and stays alive briefly; test the UI manually too. On first runs an unsigned build may trigger SmartScreen/antivirus warnings; **do not disable security protection**. For GitHub Releases, push the matching `v1.0.0` tag only after the manual acceptance checklist is complete.

CI uses the pinned Python 3.13 and PyInstaller version in `requirements-build.txt`. If the builder fails due to a new Windows/Qt compatibility issue, fix and retest before tagging.
