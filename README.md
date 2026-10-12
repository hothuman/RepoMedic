# RepoMedic v1.0.0 — Developer Pro

**Free and open-source project diagnostics for Windows and Linux.** RepoMedic statically examines supported Python, Node.js, Docker, Git and GitHub Actions configurations and explains potential issues — without executing repository code. It has a local-first desktop UI, CLI, RU/EN interface, dark/light themes, local scan history and TXT/JSON/HTML export.

![RepoMedic emblem](assets/repomedic_logo.png)

> **Scope:** heuristic static checks, **not** an antivirus, vulnerability scanner or security audit. Health Score is a rough guide, not a guarantee that a project is safe or buildable.

## Windows installation — source

Keep your existing `.venv` when upgrading from v0.9.1 and copy the **contents of the `RepoMedic_v1.0` folder** over the old source directory after making a backup. Settings and history are stored separately in `%LOCALAPPDATA%\RepoMedic`.

```powershell
cd C:\path\to\RepoMedic
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\smoke_gui.py
.\.venv\Scripts\python.exe main.py
```

You may instead create a fresh compatible Python environment. The automated Windows portable `.exe` build uses Python 3.13 and `requirements-build.txt`.

## CLI

```bash
python cli.py ./your-project --format json --output report.json
python cli.py ./your-project --fail-on-warning
```

CLI exit codes: 0 = no ERROR (warnings allowed unless strict), 1 = errors or strict warnings, 2 = invalid input or processing error.

## Windows portable ZIP for users

A release ZIP (`RepoMedic-Windows-x64-v1.0.0.zip`) should contain `RepoMedic/RepoMedic.exe` and its runtime dependencies. Users unzip it and start the EXE; Python isn't required. Do **not** distribute `RepoMedic.exe` alone. Build locally or obtain a Windows CI artifact **after successful tests**, and verify its SHA-256; see [Windows build](docs/BUILD_WINDOWS.md). **The source ZIP is not the compiled Windows application.**

## GitHub release workflow

CI runs Python tests on Ubuntu and Windows, then builds and packages the Windows app. A tag matching `v1.0.0` is checked against `version.py`; if all jobs succeed, the workflow can publish the release with its checksum. **Do not push the tag until the acceptance checklist is complete.**

[Release checklist](docs/RELEASE_CHECKLIST.md) · [Russian guide](README_RU.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · MIT License

## Privacy

No telemetry or automatic project uploads. Scans of local directories are read-only. GitHub downloads occur only on explicit request and are bounded. Local history stores project paths and finding texts, can be disabled or deleted. Review exports before sharing.
