# AI Usage Disclosure

AI assistants were used selectively during the development of the Office
Intelligence Automation Platform (OIAP). This document records how they were
used, so that anyone reading the repository can judge the work accurately.

OIAP is an AI engineering project, so it is worth being explicit: using AI
tools to help build it is disclosed here as a matter of transparency, not
treated as a substitute for engineering judgement.

## Tools Used

| Tool | Typical use in this project |
|---|---|
| ChatGPT | Architecture and planning discussion, documentation drafting |
| Codex | Selected code generation and editing support |
| Claude | Code review, debugging, test and validation planning, security and public-release review support |

## Where AI Assistance Was Applied

- Architecture and planning discussion, including trade-off exploration.
- Documentation drafting and refinement.
- Selected code generation and editing support.
- Debugging and review assistance.
- Test and validation planning.
- Git and GitHub workflow guidance.
- Security and public-release readiness review support.

## What AI Assistance Did Not Do

- AI tools did not independently own, approve, or release any part of this
  project.
- No AI tool selected the architecture, decided what shipped, or made a release
  decision on its own.
- No change entered a branch without maintainer review.
- This project does not claim autonomous AI development. Every AI contribution
  passed through a human decision point.

## Maintainer Responsibility

The maintainer reviewed and validated AI-assisted outputs before they entered
the repository, and retains responsibility for:

- system architecture and design decisions;
- implementation correctness;
- testing and validation;
- security posture and public-release decisions; and
- the accuracy of this repository's documentation.

Where any AI-assisted output is wrong, incomplete, or misleading, that is a
maintainer error, not a tooling excuse.

## Standards Applied to AI-Assisted Work

- AI-generated suggestions are not accepted blindly. Generated code is read and
  understood before it is kept, and rejected when it is unclear, unnecessary,
  or wrong.
- AI-assisted changes are held to the same quality and security standards as
  any other change: the same tests, type checking, linting, review, and
  data-handling rules apply.
- Plausible-sounding output is verified against the actual codebase, the
  library documentation, or a test before it is trusted.
- Generated content is never allowed to introduce secrets, credentials, real
  company data, or personal data into the repository.

Contributors should read this document alongside `CONTRIBUTING.md`, which sets
the same expectation for AI-assisted contributions.
