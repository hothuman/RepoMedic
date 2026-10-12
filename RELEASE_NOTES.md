# RepoMedic v1.0.0 — Developer Pro

First stable-release **candidate** of RepoMedic, a local-first, open-source project diagnostics tool. The Windows portable package is built and attached only after CI passes.

## Highlights

- Developer Pro dashboard with official red shield, skull and sword identity.
- Local folder and public GitHub repository diagnostics without executing checked project code.
- Static checks for Python, Node.js, Docker, Git and GitHub Actions.
- Local scan history, RU/EN interface, dark/light theme and TXT/JSON/HTML export.
- Command-line analyzer for scripts and CI.
- Windows x64 portable package with SHA-256 checksum; no Python required by the end user.

## Important limitations

- Results and Health Score are **heuristics**, not proof of security, correctness or successful execution.
- The GitHub importer is for **public** repositories and downloads a ZIP when you request a scan.
- This is an **unsigned** portable app unless the maintainers sign it separately; no code-signing certificate is included.
- Automatic telemetry is not used. Local history may contain project paths and finding texts.

Consult `README.md` / `README_RU.md` and `docs/RELEASE_CHECKLIST.md`. Do not publish before completing the clean-Windows manual acceptance checklist.
