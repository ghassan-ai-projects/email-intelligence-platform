# Round 2 Plan

1. Freeze the clean baseline and source/test inventory.
2. Obtain four independent read-only review reports covering every Python file.
3. Consolidate only verified, substantive findings and coverage gaps.
4. Process source files one at a time in descending source line count, pairing
   each file with its focused tests and recording a four-lens outcome. Shared
   contract changes are completed first only when a larger file depends on
   them; this round's security/import prerequisite slice is recorded as such.
5. Run focused tests and the coverage gate after each meaningful file slice.
6. Commit each accepted slice with a Conventional Commit; do not commit a
   file before its review findings and focused tests are resolved.
7. Repeat the four-lens review over changed areas, then run the final repository
   gates and record the evidence.

The target is 90% or higher combined branch coverage. Existing lint and format
checks are regression gates only; style-only changes are explicitly excluded.
