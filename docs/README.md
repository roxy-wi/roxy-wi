# Documentation in this repository

These guides are versioned with the implementation. Update the relevant guide
and support matrix whenever a workflow, endpoint, deployment requirement or
compatibility boundary changes. Website documentation is maintained separately;
adding a Markdown file here does not publish it to roxy-wi.org.

- [Request-path diagnostics and probe boundaries](proxy-diagnostics.md)
- [Reviewed HA node maintenance and recovery](ha-maintenance.md)
- [Shared Keepalived/Pacemaker readiness and evidence](ha-readiness.md)
- [Managed Docker/Podman components, adoption and witness lifecycle](managed-containers.md)
- [External certificate providers and CertWarden](certificate-sources.md)
- [Roxy-WI controller deployment with Podman Quadlet](podman-controller.md)
- [HA technologies, platforms, Docker and SYN protection](ha-support.md)
- [Corosync/Pacemaker administration and HTTP API](corosync-pacemaker.md)
- [Guided witness conversion and recovery](corosync-pacemaker-witness-migration.md)
- [Exporter and daemon Auto Start](corosync-pacemaker-monitoring.md)
- [Planned custom transport migration](corosync-pacemaker-transport-migration.md)
- [GUI/component audit and remaining gaps](corosync-pacemaker-gui-audit.md)
- [Standalone Docker quorum witness](corosync-pacemaker-witness-docker.md)
- [Agent discovery, metadata forms and package management](corosync-pacemaker-agents.md)
- [Control reference, examples and recovery procedures](corosync-pacemaker-controls.md)
- [Reproducing automated and live workflow tests](corosync-pacemaker-testing.md)
- [Verification scope and remaining limits](corosync-pacemaker-verification.md)
- [Annotated UI screenshots](screenshots/corosync-pacemaker/README.md)
- [Project setup and deployment entry points](../README.md#deployment-choices)
- [Release notes](../CHANGELOG.md)
