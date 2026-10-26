# Contributing to pyverge

Thank you for considering contributing to pyverge! This document outlines the
process for contributing code, documentation, and ideas.

## Getting started

1. **Fork the repository** and clone it locally.
2. **Create a virtual environment** and install dependencies:
   ```bash
   uv sync --dev
   ```
3. **Run the tests** to ensure everything works:
   ```bash
   uv run pytest
   ```

## How to contribute

### Reporting issues

- Use the issue tracker to report bugs, request features, or ask questions.
- Do **not** report security vulnerabilities publicly. See
  [SECURITY.md](SECURITY.md).
- For bugs, include:
  - A minimal reproducible example
  - Expected vs. actual behavior
  - Python version and pyverge version
  - Stack traces if applicable

### Submitting code

1. **Open an issue first** using the bug or feature template. Every non-trivial
   change needs a ticket so it can be triaged, scoped, and linked from commits.
   Small fixes such as typos may proceed without one.

2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** following the existing code style.

4. **Write tests** for new functionality. Aim for high coverage.

5. **Run checks** before committing:
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run pytest
   uv run ty check src/pyverge
   ```

6. **Commit** with a clear message following [Conventional Commits](https://www.conventionalcommits.org/),
   scoped by issue number:
   ```bash
   git commit -m "feat(#56): add new migration hook type"
   ```
   The scope is the issue the work addresses, so the history links commits to
   their issue (e.g. `fix(#62): ...`).

7. **Push** and open a pull request. Link the issue with `Closes #...`.

### Documentation

Documentation lives in `docs/` and follows two external guides:

- [Diátaxis](https://diataxis.fr/) — every page is one of `tutorials`,
  `how-to`, `reference`, or `explanation`.
- [Google developer documentation style](https://developers.google.com/style) —
  address the reader as **you**, use active voice and present tense, sentence
  case headings, and code font for commands, paths, and identifiers.

Structure:

```text
docs/
  tutorials/     # learning-oriented walkthroughs
  how-to/        # task-oriented instructions
  reference/     # API, formats, CLI
  explanation/   # concepts, architecture, trade-offs
```

Guidelines:

- Do not mix documentation types on one page.
- Start how-to titles with a verb.
- Keep reference pages neutral and structured for lookup.
- Include runnable examples and test them.
- Update links when moving pages.
- Update the changelog if applicable.

Validate the docs before committing:

```bash
uv run mkdocs build --strict
```

### How-to page template

Task-oriented pages use this shape:

```markdown
# Verb-led task title

One-sentence outcome.

## Prerequisites

## Steps

## Verify

## Troubleshooting

## See also
```

Keep reference facts out of how-tos; link to `docs/reference/` instead.

## Docs analytics and feedback

Selected provider: **Plausible**.

- Privacy-friendly and cookieless.
- Tracks page views, referrers, and custom events.
- Requires a project domain in the Plausible account before enabling.

Events to track:

```text
search
zero-result-search
copy-code
docs-feedback
```

Feedback uses GitHub Issues rather than a hosted feedback widget. Add a
prefilled issue link to a page when collecting targeted feedback:

```text
https://github.com/JoHa-HQ/pyverge/issues/new?labels=docs
```

Do not add a third-party feedback widget until ownership and privacy review are
complete.

## Code style

- **Formatting**: `ruff format` (Black-compatible)
- **Linting**: `ruff check`
- **Type checking**: `ty check`
- **Testing**: `pytest` with `-vv` for verbose output

Follow existing patterns in the codebase. When in doubt, match the surrounding
code.

## Pull request process

1. **CI must pass** — all checks (ruff, ty, pytest) must be green.
2. **Review** — at least one maintainer must approve.
3. **Squash** — if your branch has multiple commits, squash them into logical
   units before merging.
4. **Merge** — maintainers will merge your PR once approved.

## Release process

Releases use two channels:

| Channel | Tag | Registry | Approval |
| --- | --- | --- | --- |
| Dev | `vX.Y.Z.devN` | TestPyPI | `testpypi` environment |
| Stable | `vX.Y.Z` | PyPI | `pypi` environment |

Commit messages determine the next stable version:

- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `fix!:` → major version bump
- a `BREAKING CHANGE:` footer also marks the change as breaking

With the issue scope, the form is `type(#issue)!: description`, for example
`feat(#56)!: replace the manager registration API`.

### Dev releases

1. Merge a reviewed PR to `main`.
2. CI must pass.
3. The `Publish Dev (TestPyPI)` workflow requests approval from the `testpypi` environment.
4. After approval, the workflow computes the next dev version
   (`X.Y.Z.devN`), builds the artifact, publishes it to TestPyPI, updates the
   deployment record, verifies the install, and creates the dev tag.
5. Dev releases do not modify `CHANGELOG.md`.

### Stable release promotion

1. Choose a TestPyPI-validated dev tag.
2. Run the `Promote Release` workflow with that dev tag.
3. The promotion verifies the tag points to `main`, CI passed, and the matching
   TestPyPI version exists.
4. `Promote Release` requests approval from the `pypi` environment.
5. After approval, the workflow computes the stable version, prepares the
   release commit and changelog, builds the artifact, publishes it to PyPI,
   updates the deployment record, verifies the install, pushes the stable tag,
   and creates the GitHub Release.
6. The stable tag is created only after PyPI verification succeeds.

### Release invariants

- TestPyPI dev releases run independently and never trigger PyPI automatically.
- PyPI promotion is an explicit human decision followed by `pypi` approval.
- No tag is created before environment approval and successful publication.
- No stable changelog entry reaches `main` before the PyPI release succeeds.
- One stable release runs at a time.


## Community

- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Governance](GOVERNANCE.md)
- [Security Policy](SECURITY.md)

## Questions?

- Open an issue for discussion.
- Check existing issues and PRs for similar topics.
- Read the [documentation](docs/) for usage guidance.
