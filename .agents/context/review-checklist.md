# Review Checklist

Use this before the final answer.

## Scope

- Did the change solve the requested problem and nothing broader?
- Is the implementation the simplest correct version you can defend in review?
- Did you avoid unrelated refactors?

## Consistency

- Do README, `AGENTS.md`, context files, `Makefile`, and CI agree?
- Do documented commands match `pyproject.toml` and the lockfile?
- Did config changes update `config.example.toml`?

## Quality

- Were tests added for production-code behavior changes?
- Did tests prove behavior rather than merely execute code?
- Did you run the relevant validation commands?
- Did you record validation failures accurately?
- Did you run `git diff --check`?

## Security

- Does the change preserve local-first behavior?
- Are email bodies, attachment content, and LLM outputs treated as untrusted?
- Are SMTP allowlists, attachment fences, rate limits, and audit logging preserved?
- Did you avoid committing secrets, credentials, private mail, or machine-local data?

## Handoff

- Did you list created and updated files?
- Did you list validation results and skipped checks?
- Did you call out remaining risks and next improvements?
