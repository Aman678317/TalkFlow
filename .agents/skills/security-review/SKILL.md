---
name: security-review
description: "Security and OWASP vulnerability review. Audits authentication, RBAC, input validation, injection, SSRF, CORS/CSRF, session handling, rate limiting, and secret protection."
---

# Security & OWASP Review Mode

Comprehensive application security and threat model audit.

## Threat Assessment Categories (OWASP Top 10 + API Top 10)
1. **Broken Object-Level Authorization (BOLA / IDOR)**: Verify every tenant/resource lookup checks the authenticated user's organization and permissions.
2. **Broken Authentication**: Token hashing, refresh rotation, brute-force / credential stuffing rate limits, timing attack safe comparisons.
3. **Injection Vectors**: SQL parameterization, shell command escaping, template injection, LLM prompt injection barriers.
4. **SSRF & Unsafe Network Requests**: Validation of outbound webhooks, URLs, protocol restrictions, private IP blocking (127.0.0.1, 169.254.169.254, RFC 1918).
5. **Data Exposure & Secret Leaks**: Inspect logs, error responses, stack traces, and client bundles for credentials, API keys, or PII.
6. **File Upload Security**: MIME validation, extension whitelisting, file size limits, safe storage paths outside document roots.
7. **Transport & Headers**: HSTS, CORS origin regex validation, Content-Security-Policy, secure cookies.
