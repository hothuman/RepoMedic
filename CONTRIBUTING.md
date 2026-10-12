# Contributing to RepoMedic

Welcome! Please report reproducible bugs or submit small, focused pull requests.

1. Fork the repository and create a descriptive branch.
2. Use Python 3.13+ and install `requirements.txt`.
3. Run `python -m unittest discover -s tests -v` before a pull request.
4. Run `python scripts/smoke_gui.py` on a machine with PySide6 and a graphical environment.
5. Do not add code execution or shell invocation of scanned repositories without discussing a sandbox/security model.
6. Never include private projects, credentials, logs with tokens, or test secrets in public reports.
7. Update `version.py` and changelog only when preparing a release.

Tests and CI need to pass before merging. Please discuss major UI or architecture changes in an issue first.
