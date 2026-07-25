# Origin Security Architecture Specification

Origin is designed to store architectural context, decisions, and long-term project memory for AI agents. Because AI agents both read from and write to Origin artifacts—and because these artifacts are executed in CI/CD pipelines—Origin incorporates multiple defense-in-depth security layers.

---

## 1. Threat Model & Key Risks

| Threat Category | Vulnerability Risk | Mitigation Strategy |
| :--- | :--- | :--- |
| **Credential Leakage** | Agents or developers committing API keys / secrets into `.origin/` YAML files | Domain-level **Secrets Guard** scanning during writes |
| **Remote Code Execution (RCE)** | Unsafe YAML deserialization of untrusted PR branches | Mandatory `yaml.safe_load()` across all read operations |
| **Branch Poisoning in CI** | Untrusted PR branch code executing in workflows with write tokens | **Trusted-Branch CI Sandboxing** (`pull_request_target`) |
| **Command Injection** | Filenames or parameters passed into shell commands | Subprocess argument list parameterization (`shell=False`) |
| **Denial of Service (DoS)** | Excessive API calls or infinite polling loops in GitHub Actions | Selective HTTP status retry with exponential backoff & time cap |

---

## 2. Domain-Level Secrets Guard

Origin incorporates a pre-commit domain filter (`detect_secret_patterns` in `src/origin/domain/secrets.py`) that evaluates all free-text fields before writing to disk.

### 2.1 Detection Algorithms
1. **AWS Credential Scanner:** Detects 20-character Key IDs matching `AKIA[0-9A-Z]{16}` or `ASIA[0-9A-Z]{16}`.
2. **PEM Private Key Scanner:** Detects RSA, EC, or OpenSSH private key headers (`-----BEGIN ... PRIVATE KEY-----`).
3. **Generic Secret Assignments:** Identifies key names like `api_key`, `secret`, `token`, `password`, `passwd` followed by an assignment operator (`=`, `:`, `=>`) and a high-entropy string ($\ge 16$ chars).
4. **Shannon Entropy Analysis:** Computes entropy on all delimited string tokens of length $\ge 32$. Tokens exceeding a $4.3$ entropy threshold are flagged.

### 2.2 Exclusions & False Positive Controls
To ensure legitimate development assets are not blocked, the scanner explicitly excludes:
* URLs (`http://`, `https://`).
* Git commit SHAs (40 hex characters).
* Origin artifact ULIDs (`dec_`, `mem_`, `evt_` prefixes).

---

## 3. Safe YAML Deserialization Policy

PyYAML's default `yaml.load()` parser can instantiate arbitrary Python objects using custom tags (`!!python/object`), creating a remote code execution path if a crafted file is checked out.

* **Policy Enforcement:** All codebase YAML reads use `yaml.safe_load()`.
* **CI Verification:** The `origin-doctor` workflow includes an automated static scan (`pip-audit` and safe-load checks) verifying zero unsafe loads.

---

## 4. Trusted-Branch CI Sandboxing Model

GitHub Action workflows handling PR comments (`origin-context-bot.yml` and `origin-pr-comment.yml`) use a sandboxed execution architecture:

```
        +------------------------------------------------------+
        |         GitHub Event (pull_request_target)           |
        +--------------------------+---------------------------+
                                   |
                                   v
        +------------------------------------------------------+
        | 1. Checkout 'main' (Trusted Code Repository)          |
        | 2. Global PIP Install from trusted source             |
        +--------------------------+---------------------------+
                                   |
                                   v
        +------------------------------------------------------+
        | 3. Clone PR Branch to 'pr-data' directory            |
        | 4. Run Trusted CLI against 'pr-data' as a string path|
        |    (PR branch Python code is NEVER imported or run) |
        +------------------------------------------------------+
```

### Key Security Properties:
* **Isolation:** The code executing in the runner is guaranteed to originate from the default branch (`main`).
* **Direct Path Argument:** The PR workspace is passed strictly as a filesystem path parameter (`pr-data`). The PR's own codebase is never added to `sys.path` or executed.
* **Permission Enforcement:** Command comment triggers (`/origin accept`, `/origin reject`) verify collaborator permissions via GitHub API prior to execution.
