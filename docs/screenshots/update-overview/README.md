# Container update overview qualification

Captured from a local build of upstream master `6ba786294ff9c85d36edb144c6266a252431a422` plus this change on 2026-10-29.
The standard `docker/Dockerfile` and current requirements were used. The application is development version 9.3.0; the latest-release column is test data, not a registry availability check.

| Host | Engine | Coverage |
| --- | --- | --- |
| Debian 13 | Rootful Docker | Real authenticated HTTPS page, host inventory and four engine integration tests |
| Rocky Linux 9.8, SELinux enforcing | Rootful Podman 5.8.2 | Same application image, authenticated HTTPS page, volume label/access and four engine integration tests |

The page runs with a fresh isolated database and synthetic credentials. Metrics and Checker heartbeat rows are fixtures. Small isolated containers provide actual engine metadata and running/stopped states for all six listed components. **These screenshots verify version discovery and display, not the functional operation of the monitoring, Auto Start or exporter daemons.**

Expected versions are Metrics 4.0.0, Checker 5.0.0, Auto Start 3.8 (stopped), Port Scanner 2.0.0 (stopped), Socket 2.0.0 and Prometheus exporter 1.6. SMON has no evidence and is shown as not detected on the inventory host. Seeded Metrics/exporter database values remain 1.0 to reproduce the original issue.

Each platform has a desktop light, desktop dark and narrow-viewport screenshot. The narrow view records the existing wide admin table and horizontal overflow; this change does not redesign that layout. No engine socket, real managed server, production data or production credential is used by the preview.

The additional browser regression covers all six shipped languages and expiration of inventory while a current worker heartbeat remains available.
