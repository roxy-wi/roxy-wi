# Unit tests

Group tests by the subsystem they exercise. Keep feature-specific templates,
JavaScript helpers, migrations and Ansible role tests with that feature.

| Directory | Scope |
| --- | --- |
| `admin/` | Administration settings, tools and action menus |
| `backup/` | Backup transfer, scheduling and administration UI |
| `certificates/` | SSL UI and Let's Encrypt transport and migrations |
| `change_center/` | Changes, approvals, APIs, automation and operations |
| `common/` | Shared utilities |
| `config/` | Configuration files, viewer, deployment policy and section generation |
| `database/` | Database access and migrations without a dedicated feature suite |
| `deployment/` | Containers and Helm release packaging, quickstart and Terraform API |
| `notifications/` | Notification delivery, RabbitMQ and Socket.IO |
| `observability/` | Log viewer, service status and diagnostics |
| `runtime/` | Application startup, health, heartbeats and worker shutdown |
| `ui/` | Shared navigation and UI controls |
| `waf/` | WAF paths, rules, installation, configuration transactions and SPOA |

Run commands from the repository root:

```sh
python -m pytest tests/unit -q
python -m pytest tests/unit/waf -q
python -m pytest tests/unit/config tests/unit/change_center -q
```

Pytest and CI discover these directories recursively. Shared application fixtures
remain in `tests/conftest.py`; add a subsystem `conftest.py` only when fixtures
need to be shared within that subsystem. Keep descriptive, unique `test_*.py`
filenames across the test tree to avoid collisions in pytest's default import mode.

Integration, security, product and browser tests remain in their existing suites.
