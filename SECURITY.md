# Security Policy

## Overview

HEPHAESTUS is an educational simulation project that demonstrates an event-driven multi-agent system with synthetic data.  
While it is not a production industrial system, security considerations are still taken seriously, especially for the deployed demo environment.

---

## Supported Codebase

Security updates are applied only to the latest state of the `main` branch.

| Branch / Version | Support Status |
|------------------|----------------|
| main             | Active development (security fixes applied here) |
| older commits    | Not supported |

---

## Scope

This security policy applies to:

- Code in this repository
- Publicly deployed demo application
- API endpoints exposed via FastAPI

Out of scope:

- Third-party dependencies
- External hosting platform (Railway)
- User-modified forks

---

## Reporting a Vulnerability

If you discover a security issue, please report it responsibly.

### Preferred contact method
- GitHub repository contact:
  https://github.com/nagasaitankasala2000-spec/hephaestus-agentic-ai

### Please include:
- Clear description of the issue
- Steps to reproduce
- Affected component (API, simulator, dashboard, etc.)
- Potential impact assessment

---

## Response Timeline

- Initial acknowledgment: within 48–72 hours
- Investigation and validation: within 3–7 days
- Fix or mitigation (if applicable): depends on severity and complexity

---

## Responsible Disclosure

Please do not publicly disclose vulnerabilities until a fix has been implemented or coordinated disclosure has been agreed upon.

---

## Notes

This project is intended for learning and demonstration purposes.  
Security practices are implemented at a best-effort level appropriate for a portfolio system, not a production-critical industrial environment.
