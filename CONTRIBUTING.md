# Contributing to Roxy-WI

This guide applies to **Roxy-WI 9.1 and later**. Contributions to documentation,
tests, accessibility and application code are welcome.

For a bug, use the [bug report form](https://github.com/roxy-wi/roxy-wi/issues/new/choose)
and include a minimal reproduction. For a substantial feature, discuss the user
problem in an issue before investing in an implementation. Report security
issues [privately](SECURITY.md).

## Development setup

Use Python 3.10–3.12, matching the test matrix. From your checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. Some integration tests
require Linux, Docker or SSH; the regular suite skips tests whose explicit runtime
requirements are not enabled. See the [Tests workflow](.github/workflows/tests.yml)
for the Linux checks and the [LE guide](docs/letsencrypt.md#release-verification)
for running the certificate deployment test.

To inspect the UI, use the [Compose quick start](docs/quick-start.md). Use test
servers and isolated application data for development.

## Prepare a pull request

Describe the problem, the resulting behavior and how you verified it. For a UI
change, include a screenshot with private data removed. Keep the change focused
and explain database migrations or operational requirements.

- Inspect the existing code and preserve API compatibility unless the change
  explicitly calls for a breaking interface.
- Add a regression test for a bug fix. Exercise failure and retry paths for
  background work, and group/role isolation for access changes.
- Keep secrets out of logs, screenshots, fixtures and reports.
- Update the relevant guide and [release notes](CHANGELOG.md) for user-visible changes.
- Review the diff and run the checks appropriate to the affected paths.

Check documentation links with `python tools/check_docs.py`. Container changes
should also pass the [Container workflow](.github/workflows/container.yml).
Pull requests should explain any required check that could not be run locally.

By contributing, you agree that your contribution is provided under the
repository's [Apache 2.0 license](LICENSE).
