# Contributing to OIAP

Thank you for your interest in the Office Intelligence Automation Platform
(OIAP). This is a maintainer-run project, so please open an issue to discuss a
change before investing significant effort in it.

## Development Model

Work flows through short-lived branches and pull requests:

1. **Feature branch** — branch from `dev` using a descriptive name, such as
   `feature/hr-semantic-retrieval`.
2. **Pull request to `dev`** — open a pull request targeting `dev` when the
   change is complete and its checks pass.
3. **Validation and review** — automated checks run on the pull request, and
   the maintainer reviews scope, correctness, tests, and data handling.
4. **`dev` to `main`** — stable, validated changes are promoted from `dev` to
   `main` in a separate pull request. `main` is intended to stay releasable.

Do not push directly to `dev` or `main`.

## Development Setup

See [`README.md`](README.md) for runtime requirements, virtual environment
setup, database and pgvector setup, environment configuration, and how to start
the application. Setup instructions are not duplicated here, so that they do
not drift out of step with the README.

Database integration tests require a disposable PostgreSQL database configured
through `TEST_DATABASE_URL`. That database is upgraded and downgraded by the
test suite, so it must never point at a shared, development, staging, or
production database.

## Quality Requirements

Run the relevant checks locally before opening a pull request, and make sure
they pass.

Backend, from the repository root with the virtual environment active:

```bash
python -m pytest
ruff check .
mypy app
```

Frontend, from the `frontend/` directory:

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

Run the backend checks for any change under `app/`, `tests/`, `scripts/`, or
`migrations/`, and the frontend checks for any change under `frontend/`. A
change that touches both needs both.

New behaviour needs tests. Fixed bugs need a test that fails without the fix.

## Pull Requests

A pull request should have:

- **Focused scope** — one logical change. Split unrelated work into separate
  pull requests.
- **A clear title and description** — what changed, why, and anything a
  reviewer should look at closely.
- **Relevant tests** — covering the new or changed behaviour.
- **No unrelated changes** — no drive-by reformatting, dependency bumps, or
  refactors that are not part of the stated scope.
- **No secrets or private data** — no credentials, API keys, tokens, real
  company or personal data, or machine-specific local paths.
- **Documentation updates where behaviour changes** — if a change alters
  configuration, an endpoint, a command, or a documented limitation, update the
  affected documentation in the same pull request.

## AI-Assisted Contributions

AI assistance is permitted. See [`AI_USAGE.md`](AI_USAGE.md) for how AI tools
have been used in this project and the standards that apply to them.

AI-assisted changes still require human review and validation. You are
responsible for any code you submit: understand it, test it, and be able to
explain why it is correct. Unreviewed generated output is not an acceptable
contribution, and AI-assisted work is held to exactly the same quality and
security standards as everything else.

## Data Policy

Public contributions must use synthetic or approved non-sensitive data only.

Do not add real company documents, employee or customer data, personal data, or
confidential internal material to this repository, including in tests, fixtures,
examples, and screenshots. Synthetic content should be clearly identifiable as
synthetic.

## Security

Do not report a suspected vulnerability in a public issue or pull request. See
[`SECURITY.md`](SECURITY.md) for the private reporting process and the current
security expectations.

## Code of Conduct

Participation in this project is subject to the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

Contributions are submitted under the terms of this repository's Apache License
2.0. By opening a pull request, you confirm that you have the right to submit
the work and that it may be distributed under [`LICENSE`](LICENSE).
