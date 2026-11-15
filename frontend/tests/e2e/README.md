# Lunar Intelligence — recommendation browser regression

Adds `frontend/tests/e2e/recommendations.spec.ts` as a single additional Playwright test.

1. Copy `frontend/tests/e2e/recommendations.spec.ts` into your repository's `frontend/tests/e2e` directory.
2. In `frontend` run `npx.cmd playwright test tests/e2e/recommendations.spec.ts --workers=1`.
3. Then run `npm.cmd run typecheck`, `npm.cmd run lint`, `npm.cmd test`, `npm.cmd run test:e2e -- --workers=1`, and `npm.cmd run build`.
4. Review `git status --short` and `git diff --check` before committing; do not stage `.env.local` or `*.li-stage2-backup`.

The fixture covers one end-to-end panel-selection path (request -> backend-shaped response -> recommendation -> Mission Controls -> Cesium selected-site display -> science requests). It does not pixel-verify colored Cesium candidate markers or test direct click picking of candidate entities. Those still require separate tests/manual verification.

All astronomy and recommendation results are explicit TEST FIXTURES, not scientifically calculated data. No CI secrets or real datasets are needed.
