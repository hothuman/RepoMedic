# Security policy

RepoMedic v1.0 checks a bounded subset of project configuration for suspicious patterns but is **not** an antivirus or formal security/vulnerability audit. A passing score does not certify safety.

No untrusted repository code is executed as part of scanning. GitHub ZIP imports require user action and have size/path limits; malformed and unknown inputs may still reveal bugs. Please avoid scanning sensitive files on shared devices, as local history and exported reports may contain paths and finding texts.

**Security reports:** Do not publish exploit details, secrets, passwords or private repository contents in issues. If the host repository enables private vulnerability reporting, use GitHub's private security advisory reporting. Otherwise request a private reporting channel from the maintainer without publishing details.

There are no automatic security fixes, code signing or malware protection claims. Please do not disable endpoint protection to launch unsigned builds.
