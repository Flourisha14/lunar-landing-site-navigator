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

## Single-Developer Hackathon Workflow

This project follows a lightweight development workflow
optimized for NASA Space Apps Challenge 2026.

### Branching

- `main` is the primary branch.
- All development occurs on short-lived feature branches.
- No `develop` branch is used.

### Pull Requests

- Each feature branch is merged through a pull request.
- Pull requests reference their ClickUp ticket identifiers.
- GitHub Actions CI must pass before merging.
- No human approval is required.
- AI code review is optional and not required.

### Merge Strategy

Squash merging is preferred.

Feature branches should be deleted after merging.

### Scientific Quality

Scientific calculations must include:

- Documented reference frames.
- Explicit coordinate conventions.
- Units and numerical tolerances.
- Scientific assumptions.
- Appropriate automated tests.
- Independent reference values where available.

### Repository Protection

The `main` branch is protected against:

- Force pushes.
- Branch deletion.
- Merging changes with failing required CI checks.

## Submission Deadline

November 15, 2026.