# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities via GitHub Security Advisories:
https://github.com/wgsim/natural_language_base_file_finder_in_terminal/security/advisories/new

**Do not** report security vulnerabilities through public GitHub issues.

## Security Scanning

### Automated Dependency Scanning

This project uses `pip-audit` for automated CVE scanning.

**Install:**
```bash
pip install pip-audit
```

**Run scan:**
```bash
pip-audit -r requirements.txt
```

**Expected output (no vulnerabilities):**
```
No known vulnerabilities found
```

### Regular Maintenance

1. **Weekly:** Run `pip-audit` to check for new CVEs
2. **Monthly:** Review and update pinned dependency versions
3. **On release:** Audit all dependencies before tagging

### Dependency Update Process

1. Check for updates:
   ```bash
   pip list --outdated
   ```

2. Test updates in a virtual environment:
   ```bash
   python -m venv test-env
   source test-env/bin/activate  # or test-env\Scripts\activate on Windows
   pip install -e ".[dev]"
   pytest
   ```

3. Run security audit:
   ```bash
   pip-audit
   ```

4. Update `requirements.txt` with new pinned versions:
   ```bash
   pip freeze | grep -E '^(httpx|rich|prompt-toolkit|keyring|tomli-w|httpcore|h11|certifi|idna|anyio|sniffio)==' > requirements.txt.new
   ```

5. Commit updates with clear changelog

## Known Security Considerations

### LLM Integration
- User queries are sent to configured LLM API endpoint
- API keys stored in system keychain (via `keyring` library)
- No query content is logged or cached
- Maximum query length: 1000 characters

### File System Access
- Reads files within specified root directory
- Symlink following disabled for content reads
- File size limits enforced (10MB for content scanning)
- No write operations performed

### Network Communication
- HTTPS required for API endpoints (HTTP blocked for production)
- TLS certificate verification enabled by default
- SSRF protection: RFC 1918 private IPs blocked for base_url

## Security Audit Results

Last comprehensive audit: 2025-02-06
- **Critical issues:** 0
- **High issues:** 0
- **Medium issues:** 0
- **Low issues:** 2 (tracked in REMAINING_ISSUES.md)

Security rating: **9.5/10**

For detailed audit findings, see `REMAINING_ISSUES.md`.
