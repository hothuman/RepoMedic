# RepoMedic v1.0 — manual release acceptance checklist

A green CI run is **necessary but not sufficient**. Have a Windows 11 tester verify:

- [ ] CI matrix passes Windows and Linux unit tests, and GUI smoke test passes on Windows.
- [ ] The portable `release/RepoMedic-Windows-x64-v1.0.0.zip` is created; SHA-256 matches `SHA256SUMS.txt`.
- [ ] On a **different clean Windows 11 machine**, unzip the ZIP, start `RepoMedic.exe` without installing Python, and confirm the icon and fonts render.
- [ ] Dashboard and every tab works: Scanner, History, Reports, Settings.
- [ ] Local folder scan works (Python + Node + Docker samples); no project files change.
- [ ] Public GitHub import works; invalid/private URLs show useful errors and don't freeze the GUI.
- [ ] TXT/JSON/HTML save and open successfully; malicious-looking file names render as plain text in HTML.
- [ ] RU/EN and dark/light theme persist through app restart.
- [ ] History is retained and can be deleted; disabling history prevents new entries.
- [ ] Very long paths, narrow screen width, Windows 125%/150% display scaling, poor network and corrupt input handled gracefully.
- [ ] Temporary GitHub downloads are cleaned up after closing/re-running.
- [ ] Windows Defender/SmartScreen results reviewed. **Do not tell users to turn off AV.** Unsigned app may prompt warnings.
- [ ] Confirm LICENSE, screenshots, issue and security links before publishing.

**Do not push a `v1.0.0` tag until this manual acceptance checklist is complete.** CI will attempt publication on a matching pushed tag. Tag is an explicit publication action, not required to run the source locally.
