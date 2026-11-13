# Scientific reference validation (QA-002)

No scientific reference tests are included in QA-001. Do not use self-generated
expected results as independent reference truth.

For each QA-002 reference case record: official source URL and product/version,
frame and datum, UTC epoch and time-scale conversion, kernel files and SHA-256,
input location, expected output with units, numerical tolerance and derivation.
Keep compact, licensed test fixtures under version control when allowed.
Large SPICE kernels and DEMs must remain external, with pinned checksums and
clear `pytest.skip` behavior if unavailable. Distinguish numerical error from
physical model uncertainty (e.g., unknown local terrain obstructions).
