# Bugfix Prompt

Use this when fixing a defect in mailintel.

1. Reproduce or narrow the failing behavior.
2. Identify the smallest affected module boundary.
3. Write or update a test that fails without the fix when feasible.
4. Fix the root cause, not only the symptom.
5. Run the narrowest relevant test first, then `make ci-check` when the change is ready.
6. Call out any skipped checks or security-sensitive impact.
