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

- Documentation lives in `docs/`.
- Use reStructuredText or Markdown consistently.
- Include examples for new features.
- Update the changelog if applicable.

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

Releases are automated via [commitizen](https://commitizen-tools.github.io/commitizen/):

1. Commit messages determine the next version:
   - `feat:` → minor version bump
   - `fix:` → patch version bump
   - `feat!:` or `fix!:` → major version bump
   - a `BREAKING CHANGE:` footer also marks the change as breaking

   With the issue scope, the form is `type(#issue)!: description`, for example
   `feat(#56)!: replace the manager registration API`.

2. Merging to `main` runs the `Release` workflow plan job. It computes the
   next version from commits and writes the proposed SHA, version, ticket, and
   changelog to the run summary.

3. The `release` environment requires reviewer approval. Approval applies to
   that exact planned SHA/version.

4. After approval, the workflow bumps the version, creates the tag, builds the
   distribution once, publishes it to PyPI, and creates the GitHub Release.

5. Pre-release tags (`vX.Y.Z-rcN`) or a manual `Publish Dev (TestPyPI)` run
   publish to TestPyPI.

## Questions?

- Open an issue for discussion.
- Check existing issues and PRs for similar topics.
- Read the [documentation](docs/) for usage guidance.
