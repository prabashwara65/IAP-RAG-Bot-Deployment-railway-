# Security Policy

## Supported Scope

The Office Intelligence Automation Platform (OIAP) is a development and
portfolio project. It is not a public production service, it is not hosted for
public use, and it carries no availability, support, or maintenance commitment.

There are no supported release versions. Security review applies to the current
state of the default branch only.

Because OIAP is not a deployed service, a report here concerns the source code
and its configuration, not a live system.

## Reporting a Vulnerability

Please do not disclose a suspected vulnerability publicly before it has been
reviewed. Do not open a public issue, pull request, or discussion describing
the problem, and do not post working exploit details in a public thread.

Report privately instead:

- Use a private GitHub security advisory ("Report a vulnerability" under the
  repository's Security tab) where that capability is available for this
  repository.
- Otherwise, use the private maintainer contact channel listed on the
  repository owner's GitHub profile.

Reports are reviewed as maintainer availability allows. No response time is
promised for this project.

## What to Include

A useful report generally includes:

- the affected component — for example an API route, a service module, a
  provider adapter, a migration, or a frontend view;
- reproduction steps precise enough to follow;
- the impact, and what an attacker would gain;
- logs, output, or screenshots where these can be shared safely; and
- a suggested remediation, if you have one.

Redact anything sensitive before attaching it. Never include real credentials,
API keys, tokens, or personal data in a report. If a report would require such
material to be understood, describe it rather than paste it.

## Security Expectations

These rules apply to the repository and to every contribution:

- **No secrets in the repository.** API keys, tokens, passwords, connection
  strings, and private keys must never be committed. Configuration is supplied
  through environment variables; `.env.example` holds placeholders only.
- **No real company, employee, or customer data.** Real HR documents, personal
  data, and confidential internal material must not enter this repository.
- **Synthetic data only** unless a specific source has been explicitly approved
  through the project's documented review process.
- **Several security capabilities are not yet production-ready.**
  Authentication, tenant isolation, and rate limiting are not implemented to a
  production standard. The API must not be exposed on an untrusted network in
  its current state, and reports noting their absence are already known
  limitations rather than new findings.
- **Responsible disclosure is expected.** Allow reasonable time for review
  before publishing details, and do not test against systems or accounts you do
  not own.

If you find a committed secret or any real personal data in this repository,
treat it as a security report and use the private route above.
