## What and why

<!-- A short description of the change and the motivation. -->

## Checklist

- [ ] `ruff check backend tests scripts` passes
- [ ] `pytest -m "not integration"` passes; new behaviour has tests
- [ ] No secrets, patient data, or real clinical images added
- [ ] Docs / README / `.env.example` updated if config or API changed
- [ ] Nothing in the change implies clinical validation or diagnostic use
