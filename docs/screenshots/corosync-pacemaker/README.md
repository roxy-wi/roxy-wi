# Corosync/Pacemaker interface

Captured from the running disposable Debian/Rocky lab on 2026-10-27 using the
standard Roxy-WI interface. A read-only presentation proxy replaced private
management addresses, host/cluster names and certificate fingerprints with
example values before rendering. Discovery and status responses came from the
real hosts; the screenshots do not change the actual cluster configuration.
Addresses use documentation ranges. No CIB XML or credentials are shown.

## Cluster overview

![Cluster health, quorum, nodes and resources](overview.png)

## Membership and independent witness

![Discovered node identities and witness configuration](membership.png)

## Reviewed witness lifecycle

![Witness conversion review and attached cluster checks](witness-lifecycle.png)

## Discovery-driven agent parameters

![Installed agent metadata generates required and optional fields](agent-parameters.png)

## Exporter and Prometheus target

![Exporter version, real metrics and example scrape target](exporter.png)
