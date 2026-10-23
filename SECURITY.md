# Security Policy

## Supported versions

pyverge is pre-1.0. Security fixes target the latest published release.

| Version | Supported |
|---|---|
| Latest 0.x release | Yes |
| Older 0.x releases | No |

## Reporting a vulnerability

Do not report security vulnerabilities through public issues, discussions, or
pull requests.

Use GitHub private vulnerability reporting:

https://github.com/JoHa-HQ/pyverge/security/advisories/new

Include:

- affected version or commit
- affected component: core, CLI, provider adapter, FastMCP, FastStream, or CI
- reproduction steps or proof of concept
- expected and actual impact
- known mitigations, if any

## Response

- acknowledgement target: 3 working days
- initial triage target: 7 working days
- disclosure target: 90 days after acknowledgement

Timelines may change for complex reports or coordinated upstream fixes. We
will keep the reporter informed and credit reporters who want attribution.

## Scope

In scope:

- pyverge package and CLI
- official provider adapters
- official FastMCP and FastStream adapters
- release and CI workflows in this repository

Out of scope:

- vulnerabilities in third-party dependencies; report them upstream, but tell
  us if pyverge needs a mitigation
- issues requiring a compromised maintainer account or GitHub platform access
- denial-of-service reports without a practical impact on normal use
