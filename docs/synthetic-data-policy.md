# Office Intelligence Automation Platform Synthetic-Data Policy

## 1. Purpose

This policy defines how synthetic documents are designed, reviewed, stored, used, and removed for the Office Intelligence Automation Platform (OIAP) Company Knowledge RAG MVP. Its purpose is to enable realistic engineering and evaluation without exposing real company, employee, client, or confidential information.

## 2. Scope

The policy applies to source Markdown, YAML metadata, evaluation questions, fake identities and contacts, processed chunks, embeddings, indexes, logs, screenshots, demos, exports, and backups used in the MVP. It applies to developers, reviewers, demonstrators, and automated tooling. It does not authorize use of real company data.

## 3. Policy principles

- Synthetic-only means invented content with no source-specific confidential copying.
- Every source and demonstration must make the synthetic nature visible.
- Source Markdown is the authority; chunks and embeddings are derived artifacts.
- Data is minimized, access is deny-by-default, and risky actions remain human-controlled.
- Synthetic and future real data are separated by storage, configuration, approval, and audit boundaries.
- Plausibility must never make invented content appear to represent a real company or person.

## 4. Allowed synthetic data

Allowed content includes invented policies, procedures, handbooks, guides, standards, directories, FAQs, departments, job roles, dates, amounts, contacts, and scenarios created solely for the demo. It may simulate internal, restricted, confidential, departmental, managerial, HR, and administrator access if all content complies with this policy.

## 5. Prohibited data

The following are prohibited:

- real names, employee records, client information, or company-identifying operational details;
- real phone numbers, real email addresses, personal addresses, or live messaging identifiers;
- credentials, tokens, secrets, private keys, connection strings, or usable authentication material;
- real contracts, invoices, bank details, tax identifiers, payroll records, or financial accounts;
- copied confidential company text or lightly altered confidential source material;
- personal, health, biometric, disciplinary, or legally sensitive facts about a real person;
- production logs, prompts, screenshots, exports, or backups containing real data; and
- third-party material the project is not authorized to reuse.

Public facts are not automatically suitable: if their use could imply a real organization or person, replace them with invented values.

## 6. Naming rules

Use clearly fictitious organization, department, role, and person labels. Do not use a real company's name, trademark, domain, product identifier, office address, or recognizable employee naming pattern. Person references should use role-based labels such as “HR Manager” or obviously fictional test identifiers such as `Employee Alpha`; avoid realistic full names.

Filenames use uppercase domain/type identifiers, a sequence, and a lowercase descriptive slug:

- `HR-POL-001-annual-leave-policy.md`
- `HR-POL-002-remote-work-policy.md`
- `IT-POL-001-information-security-policy.md`
- `ENG-STD-001-software-development-standard.md`
- `OPS-GDE-001-customer-escalation-guide.md`

The filename prefix and YAML `document_id` must agree. Renaming requires review of links, manifests, evaluation cases, and audit references.

## 7. Document labeling rules

Every document must visibly state near the beginning, after the title:

> **Synthetic demo content:** This document is fictional and is used only to test the Office Intelligence Automation Platform. It does not describe a real company, person, policy, entitlement, obligation, or contact channel.

The label must remain in rendered Markdown, retrieved source views, demo exports, and screenshots. Metadata alone is insufficient. A parser or reviewer must reject a missing, obscured, or ambiguous label.

## 8. Required YAML metadata

Every MVP source must begin with this structure and all listed fields:

```markdown
---
document_id: HR-POL-001
title: Annual Leave Policy
document_type: policy
department: Human Resources
version: "1.0"
status: active
effective_date: 2026-01-01
review_date: 2027-01-01
owner: HR Manager
access_level: all_employees
confidentiality: internal
synthetic: true
language: en
tags:
  - annual-leave
  - employee-benefits
  - hr-policy
---

# Annual Leave Policy

**Synthetic demo content:** This document is fictional and is used only to test the Office Intelligence Automation Platform. It does not describe a real company, person, policy, entitlement, obligation, or contact channel.

## Purpose

...
```

Mandatory fields are `document_id`, `title`, `document_type`, `department`, `version`, `status`, `effective_date`, `review_date`, `owner`, `access_level`, `confidentiality`, `synthetic`, `language`, and `tags`.

Valid controlled example values are:

| Field | Valid values |
|---|---|
| `document_type` | `policy`, `procedure`, `handbook`, `guide`, `standard`, `directory`, `faq` |
| `status` | `draft`, `active`, `archived`, `superseded` |
| `access_level` | `all_employees`, `department_only`, `managers_only`, `hr_only`, `administrators_only` |
| `confidentiality` | `internal`, `restricted`, `confidential` |

`synthetic` must always be Boolean `true` for MVP documents. Dates use ISO `YYYY-MM-DD`, version is a quoted string, language uses an approved code such as `en`, and tags are normalized lowercase slugs. Department and owner must use approved fictional taxonomy values. A schema change requires a documented decision, parser update, migration plan, and regression review.

## 9. Markdown content rules

Use one level-one title matching YAML `title`, followed by the visible synthetic label. Level-two and deeper headings must represent meaningful semantic sections, not formatting fragments. Content must be coherent with metadata, dates, status, audience, department, and version. Tables and lists need descriptive headings. Links must be inert examples or approved repository-relative references; no link may expose or trigger a real service. Hidden text, executable code, active macros, and instructions aimed at overriding RAG controls are prohibited except in explicitly isolated security test fixtures.

## 10. Fake company structure rules

Define a small, documented fictional structure sufficient for access and routing tests. Departments may include Human Resources, Finance, Engineering, IT, Operations, and company-wide functions. Do not reproduce a real organization's org chart, reporting line, location map, or internal terminology. Cross-document department names must use the same controlled values.

## 11. Fake employee rules

Prefer roles or stable synthetic identifiers over human-like full names. A fake employee record may contain an invented identifier, department, role, manager flag, and access-test attributes only when a scenario requires them. It must not derive from a real employee, combine recognizable traits, or include protected or sensitive personal details. Synthetic identity fixtures remain separate from document sources.

## 12. Fake contact-information rules

Do not use real phone numbers or email addresses. Use reserved documentation domains such as `example.com`, non-dialable placeholders, and explicit labels such as `synthetic-contact@example.com`. Do not create or test delivery to those addresses. URLs must use reserved/example hosts or local non-routable test endpoints. Contact strings are validated before Git inclusion and demos.

## 13. Fake financial-information rules

Amounts, budgets, cost centers, and invoice scenarios must be invented and visibly contextualized as synthetic. Never use real bank accounts, payment cards, tax identifiers, salary records, client transactions, or authentic invoice layouts containing recognizable counterparties. Use non-payable placeholders. The MVP must not initiate a payment or other financial action.

## 14. Synthetic document versioning

Each logical document has a stable `document_id`; each material content or applicability change increments the quoted `version`. Metadata values that define identity and ownership remain consistent across versions unless an approved change record explains the migration. Effective and review dates must be coherent. Only one version is normally active for a document ID. Previous active versions become `superseded`, never silently overwritten.

## 15. Synthetic document review

An author and a separate human reviewer should confirm that content is invented, internally consistent, clearly labelled, schema-valid, access-appropriate, non-actionable outside the demo, and useful for intended evaluation cases. Review evidence records document ID/version, reviewer role, date, findings, and disposition. Automated validation supports but does not replace human approval.

## 16. Access-level simulation

The five allowed `access_level` values exercise deterministic authorization behavior. `department_only` requires exact approved department membership; `managers_only`, `hr_only`, and `administrators_only` require explicit attributes or roles. Access is deny-by-default and filtered before retrieval content reaches the LLM. Administrator infrastructure access does not automatically grant content access unless the policy says so.

## 17. Confidentiality-label simulation

`internal`, `restricted`, and `confidential` simulate increasingly constrained handling; company-approved definitions must precede real-data use. A confidentiality label can add controls but cannot broaden `access_level`. Tests cover leakage through citations, titles, errors, logs, counts, and model output. Synthetic labels do not claim alignment with a legal or industry classification standard.

## 18. Separation from real company data

MVP repositories, storage roots, databases, indexes, provider projects, configuration, backups, logs, and evaluation datasets must contain synthetic data only. Do not paste real text into a synthetic template, temporarily upload real documents, or mix synthetic and real embeddings. The later real-data environment requires separate credentials, authorization, storage, index namespace, and approval records.

## 19. Storage rules

Planned repository-relative structure:

```text
data/
  synthetic/
    company-wide/
    hr/
    finance/
    engineering/
    it/
    operations/
  processed/
  evaluation/
```

Source-of-truth Markdown belongs under `data/synthetic/`. `data/processed/` contains generated chunks, manifests, or embedding exports only if repository policy explicitly permits them. `data/evaluation/` contains synthetic evaluation inputs and expected results. Filesystem permissions and application path checks prevent traversal outside approved roots.

## 20. Git rules

Before commit, reviewers must check diffs for prohibited data, live contacts, secrets, and accidental generated artifacts. Secret scanners and targeted patterns supplement manual review. Large indexes, databases, provider caches, runtime logs, and local configuration must be ignored unless an explicit reviewed policy says otherwise. Git history is not a secure deletion mechanism; an accidental real-data or secret commit triggers incident handling and credential rotation where applicable.

## 21. Testing restrictions

Tests use only synthetic fixtures created for the scenario. Do not copy production samples, emails, call transcripts, contracts, employee records, or real support messages into tests. Network and communication adapters are mocked or directed to non-delivery sandboxes. Security test documents containing prompt injection or malicious text are isolated and prominently labelled.

## 22. Logging restrictions

Logs must not contain credentials, full source documents, unrestricted prompts, embeddings, or unnecessary personal-style fields. Use correlation IDs, document IDs/versions, status, timing, and bounded error categories. Query or excerpt logging is off by default and requires an approved, redacted evaluation mode. Log access and retention remain company decisions before real data.

## 23. Demo restrictions

Every demo opening and result view states that the company, users, documents, and outcomes are synthetic. Demonstrators must not imply production readiness, legal compliance, live company integration, or permission to rely on the fictional policies. Email, WhatsApp, voice, payment, or other externally visible actions are simulated and cannot be sent. Screenshots and recordings follow the same policy.

## 24. Replacement with real documents

Synthetic sources are never relabelled as real. Approved real documents enter a separate controlled environment, receive new source records and classification review, and are processed into new chunks and embeddings. The architecture may reuse interfaces and pipelines, but permissions, evaluation, and operational approval are repeated against real-data characteristics.

## 25. Real-document approval workflow

1. A named business/data owner identifies the authoritative source and allowed purpose.
2. Security and privacy/legal reviewers assess classification, personal/client data, provider use, retention, and regional requirements.
3. A content owner confirms accuracy, version, effective dates, audience, and conflicts.
4. An access owner maps role, department, document, `access_level`, and `confidentiality` rules.
5. Engineering validates format, extraction, chunking, citations, deletion, and rollback in isolation.
6. Evaluation and adversarial access tests pass approved thresholds.
7. A named company authority records Go/No-Go approval before activation.

Approval of one document or corpus does not authorize unrelated sources or communication workflows.

## 26. Re-ingestion and re-indexing

A source or parser, chunker, embedding-model, metadata, or access-policy change creates a versioned processing run. Re-ingestion is idempotent and creates candidate artifacts. Counts and fingerprints are reconciled before atomic activation. Old artifacts remain only for approved rollback/retention, and evaluation is rerun when retrieval behavior may change.

## 27. Deletion and cleanup

Synthetic content is deleted when no longer required, incorrectly labelled, policy-violating, or superseded beyond approved retention. Cleanup covers source files, processed chunks, vectors, caches, exports, logs, demo captures, and backups according to documented capabilities. Deletion is authorized and audited. If real data is found, stop processing, isolate access, notify the named owner, preserve only required incident evidence, and follow company incident instructions.

## 28. Audit requirements

Record source creation/import, validation, reviewer approval, activation, version change, superseding, archiving, re-ingestion, index activation, access-policy change, export, exception, and deletion. Records identify actor or system, time, document/version, action, reason, outcome, and correlation ID without copying unnecessary content. Retention and tamper-evidence controls require company approval.

## 29. Human approval

A human content owner approves each source version before active retrieval. A human security/data authority approves any transition to real documents. A human reviewer controls exceptions and future externally visible actions. AI-assisted drafting or review does not transfer accountability from the responsible human.

## 30. Exceptions

No exception may permit secrets, credentials, unapproved real company data, or autonomous risky actions in the MVP. Other exceptions require a written purpose, exact data and environment scope, owner, risk assessment, safeguards, expiry date, review date, and approval by the data/security owner. Expired exceptions fail closed and are removed or renewed explicitly.

## 31. Policy review checklist

- [ ] File path and name follow the planned taxonomy.
- [ ] All mandatory YAML fields exist, parse, and use valid values.
- [ ] `synthetic` is Boolean `true`.
- [ ] Title, `document_id`, filename, department, owner, dates, status, access, confidentiality, and version agree.
- [ ] The visible synthetic-demo label appears immediately after the title.
- [ ] No real names, contacts, clients, credentials, contracts, employee records, confidential text, or actionable financial identifiers appear.
- [ ] Markdown headings form meaningful semantic sections.
- [ ] Content is internally consistent and does not imitate a real organization.
- [ ] Cross-version metadata and lifecycle changes are traceable.
- [ ] Superseded documents are excluded from normal retrieval.
- [ ] Archived documents are excluded unless explicitly requested for testing.
- [ ] Access and confidentiality cases have positive and negative tests.
- [ ] Processed chunks and embeddings are treated as generated artifacts, not source-of-truth documents.
- [ ] Human author/reviewer evidence and approval are recorded.
- [ ] Demo, logging, Git, cleanup, and exception requirements are satisfied.
