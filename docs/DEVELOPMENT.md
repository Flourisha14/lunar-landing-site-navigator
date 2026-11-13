# Development Workflow

## Project Management

Development tasks are tracked using ClickUp.

Every feature branch, commit, and pull request
should reference its associated ClickUp ticket.

## Branching Strategy

The `main` branch contains validated project code.

Changes should be developed on feature branches.

Examples:

```text
feature/DEVOPS-002-github-actions
feature/BACKEND-001-spice-integration
feature/FRONTEND-001-moon-rendering
```

## Creating a Feature Branch

```bash
git switch main
git pull origin main
git switch -c feature/TICKET-ID-description
```

## Commit Convention

Use:

`TICKET-ID: Description`

Example:

```text
DEVOPS-002: Configure backend CI
```

## Pull Request Workflow

1. Push the feature branch.
2. Open a GitHub pull request.
3. Include the ClickUp ticket identifier.
4. Describe implementation and testing.
5. Allow automated checks to run.
6. Request peer review.
7. Merge after validation.

## Code Quality

Backend contributions must pass:

- Ruff
- Mypy
- Pytest

Scientific modules require appropriate unit tests.

## Scientific Verification

Scientific implementation must document:

- Reference data source
- Coordinate reference frame
- Units
- Numerical tolerances
- Assumptions
- Validation results

## Data Policy

Large NASA datasets, SPICE kernels, and
generated simulation outputs must not enter Git history.

Dataset sources and acquisition instructions
must be documented.

## Pull Request Merge Strategy

Prefer squash merging.

## Submission Deadline

November 15, 2026.