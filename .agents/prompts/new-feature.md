# New Feature Prompt

Use this when adding a feature to mailintel.

1. Define the user-visible outcome and the agent-facing contract.
2. Check whether schema, config, CLI, MCP, docs, or audit logging must change.
3. Prefer safe defaults: no network-only tests, no implicit sending, no unbounded logging.
4. Add tests for the public behavior and important failure paths.
5. Update documentation and examples.
6. Run `make ci-check` before handoff unless the feature is explicitly docs-only.
