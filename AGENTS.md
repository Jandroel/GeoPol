# Development conventions

- Keep geographic decisions in `backend/geopol/domain`, independent of HTTP and persistence.
- Never commit institutional datasets, credentials, generated exports, or local databases.
- Preserve source rows. A missing reference is different from a completed search without matches.
- Every result must retain method, provenance, spatial precision, evidence, and revision.
- Run backend tests and frontend type checks/build before committing relevant changes.
- Use Conventional Commits, with a scope when useful. Do not rewrite existing history.
- Use synthetic fixtures for tests and demos. No public geocoding or remote basemap by default.

## Design Context

- GeoPol serves INEI operators and reviewers processing large PNP/SIDPOL Excel datasets. The main jobs are loading source/reference files, safely resolving locations automatically, reviewing exceptions, and exporting traceable results.
- The user chose a clear institutional identity: INEI navy, cyan and white, a restrained tone, readable data, minimal repeated information, and quick review workflows. Keep this context across UI changes.
- For all UI/UX work, read `frontend/DESIGN.md` first. It is the project's design source of truth, with the four user-requested references: UI UX Pro Max, Refactoring UI, Anthropic Frontend Design and Impeccable. Consult their relevant guidance during design, implementation, review and polish.
- Follow this order: UX and system → hierarchy and spacing → visual direction → final polish. Resolve conflicts in favor of the user's context, accessibility, data integrity and the existing INEI identity. Do not apply a skill's example palette, marketing layout or font preference mechanically.
- Validate affected interactions and inspect desktop/mobile output. Use real states and accessible alternatives to chart interaction; motion must respect reduced-motion preferences. Record material design decisions and verification in `frontend/DESIGN.md` and `frontend/QA.md`.
