# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take the security of Origin seriously. If you find a security vulnerability, please do **not** open a public issue. Instead, report it privately to ensure it can be patched before public disclosure.

### How to Report Privately

1. **GitHub Private Vulnerability Reporting**:
   Go to **Security** -> **Vulnerability Advisories** -> **Report a vulnerability**.

2. **Email**:
   Email security reports directly to the maintainer:
   * **Contact**: [soham.mishra206@gmail.com](mailto:soham.mishra206@gmail.com)
   * Please include details such as a proof of concept (PoC), steps to reproduce, and potential impact.

We will acknowledge your report within 48 hours and coordinate a fix.

## Security Architecture

For detailed information on Origin's threat model, automated Secrets Guard, PyYAML safe-loading, and trusted-branch CI sandboxing, see [docs/security.md](docs/security.md).
