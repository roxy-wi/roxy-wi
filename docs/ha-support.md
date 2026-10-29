# HA technologies and deployment support

Open **HA Cluster** and select **HA technology**. Keepalived/VRRP provides virtual
IP failover; Corosync/Pacemaker provides quorum, fencing, dependencies and resource
orchestration. The selector opens the appropriate existing management workflow.
It does not convert a running Keepalived cluster into a Pacemaker cluster, merge
their database records or change the subscription/access checks of Keepalived HA.

For Pacemaker installation, adoption and a qnetd-only host, use
**Installation → Corosync / Pacemaker**. Day-to-day management is also available
under **Services → Corosync / Pacemaker**. Its standard service submenu opens
Overview, Resources, Configuration, Quorum/witness, Logs, Monitoring and Versions.
Each submenu item opens its own URL and retains the selected cluster. Installation
options and SYN-flood tuning are confined to Installation. Operator-only links are hidden from viewers; opening a section does not apply
configuration changes or automatically load a credential-bearing CIB into the editor.

## Why offer both HA technologies?

Keepalived remains useful for VRRP virtual-address failover, LVS and health
tracking. It supports health checks and synchronization groups; this integration
does not remove or replace those workflows. VRRP election alone does not provide
a general application dependency graph or prove that an unreachable peer has
stopped serving a shared resource.

Corosync supplies cluster membership and quorum. Pacemaker uses resource agents
to start, stop and monitor applications, and applies ordering, colocation and
recovery policies. A qdevice with an independent qnetd witness adds a tie-breaking
vote to a two-node cluster. Fencing is still required to isolate a failed or
unreachable member before safely recovering exclusive resources.

This is a full management alternative because installation, adoption, resources,
constraints, quorum, diagnostics, monitoring and planned maintenance are available
through the web interface. It is not an automatic conversion of Keepalived
configuration. Pacemaker adds operational complexity, and neither quorum nor
resource management automatically replicates application data. Qualify the actual
workload, storage and fencing design before deployment.

See the upstream [Keepalived configuration reference](https://www.keepalived.org/documentation/keepalived-conf/)
and [Pacemaker resource documentation](https://github.com/ClusterLabs/pacemaker/blob/main/doc/sphinx/Pacemaker_Explained/resources.rst).

## Controller OS and target OS are different

The Roxy-WI Web/Scheduler/Operations deployment can use the existing package,
Docker Compose or Helm deployment. Cluster commands execute over SSH on the
registered target hosts. The controller therefore does not need the target's
package manager, Pacemaker binaries, systemd or access to the Docker socket.

Automatic target installation uses a detected `/etc/os-release` profile:

| Target | Automatic installation | Package manager | Live qualification in this change |
| --- | --- | --- | --- |
| Debian 11 and later | Cluster, qdevice, qnetd | apt | Debian 13.7, Corosync 3.1.9, Pacemaker 3.0.0 |
| Ubuntu 20.04 and later | Cluster, qdevice, qnetd | apt | Not performed; profile/package-selection tests only |
| Rocky Linux 9.8 | Cluster, qdevice, qnetd | dnf | Corosync 3.1.10, Pacemaker 2.1.10, qnetd 3.0.4; SELinux enforcing |
| Other RHEL-compatible EL 8/9 profiles, including RHEL, Rocky, AlmaLinux, CentOS Stream and Oracle Linux | Cluster, qdevice, qnetd | dnf | Not performed; profile/package-selection tests only |
| Other Linux distributions | Manual installation followed by compatible-cluster adoption | — | Not qualified |

**An implemented installation profile is not equivalent to live qualification or
vendor certification.** The supported OS list for installing Roxy-WI itself does
not guarantee that the distribution ships a compatible cluster stack.

The target needs Python 3.8 or newer available as `python3`, systemd, non-interactive sudo and available native
packages. Enable the distribution's HA repositories and entitlements beforehand;
Roxy-WI does not enable paid repositories, disable SELinux or disable a firewall.
Allow sufficient memory or swap for native package transactions. In the Rocky
qualification, a 1 GB VM ran out of memory while DNF resolved HA plus EPEL packages;
the same clean installation succeeded with 2 GB. Roxy-WI does not create swap or
change VM memory automatically.
On EL 8, the original Python 3.6 is insufficient for CIB canonicalization;
provide a compatible `python3` interpreter before using this module.
On Ubuntu, package selection handles both the legacy `resource-agents` package
and the split `resource-agents-base`/`resource-agents-extra` packages. Required
Pacemaker CLI tools are checked after installation.

Use **Check target platforms** or the witness's **Check platform** before
installing. Unsupported automatic profiles are refused before provisioning.
Adoption is based on compatible cluster tools/output and paths rather than the
controller's OS. It requires a readable CIB, `crm_mon --output-as=xml`, Corosync's
nodelist/CMAP, `/etc/corosync/corosync.conf` and matching node identities; it is not
a guarantee for every historic Pacemaker release. See the
[administration guide](corosync-pacemaker.md) for adoption and transport limitations.

## Container component support

| Component | Supported workflow |
| --- | --- |
| Roxy-WI controller in Docker | Existing image and Compose roles: Web, Scheduler, Operations and Service Events; remote nodes are managed over SSH |
| Managed HAProxy/NGINX/Apache, including Keepalived HA | Native/Docker/Podman runtime choices; Podman provisioning and explicit rootless adoption are described in the [managed component guide](managed-containers.md); new Podman VM qualification pending |
| A containerized Pacemaker workload | `ocf:heartbeat:docker` or `ocf:heartbeat:podman` in the resource form; advanced bundles through the complete CIB editor |
| Corosync/Pacemaker daemons inside a generic Docker container | Automatic provisioning is refused; run the cluster daemons on the systemd hosts |
| Standalone qnetd in Docker on an independent registered host | Installation → Install witness only → Runtime: Docker; managed image build, persistent CA, TLS signing and native cluster qdevice clients; see the [Docker witness guide](corosync-pacemaker-witness-docker.md) |
| Standalone qnetd in Podman on an independent registered host | Runtime: Podman; managed image/NSS identity, systemd supervisor, reviewed native conversion, update/trust/recovery; new Podman VM qualification pending |
| qnetd inside the Roxy-WI application container | Not installed by this module; choose a separate host service through its registered SSH credentials |

For a container workload, install the runtime and matching OCF agent on every
eligible cluster node. Provide the image, volumes and networking appropriate to
the application. An example resource-form parameter object is:

```json
{"image":"registry.example.test/team/application:release","run_opts":"--network=host"}
```

The container runtime is a prerequisite, not installed by the cluster bootstrap.
CIB validation/simulation remains mandatory. Bundle controls target the bundle
rather than its implicit per-replica resources. Existing externally managed
containers are not automatically adopted as Pacemaker resources.

For the Roxy-WI container deployment, retain a persistent database and encryption
key, use the same configuration/secrets for every role, and make SSH targets
reachable from Web and Operations. Do not use `localhost` to refer to another VM
or to the container's physical host. A qnetd service on the Roxy-WI host is
independent of the application container and must remain outside both cluster
nodes' failure domains. See [deployment entry points](../README.md#deployment-choices).

## Optional SYN-flood protection

The new-cluster installation offers an explicit **SYN-flood protection** checkbox.
It defaults to off. When selected, bootstrap applies these host TCP settings and
persists them in `/etc/sysctl.d/90-roxywi-syn-flood.conf`:

- `net.ipv4.tcp_syncookies = 1`
- `net.ipv4.tcp_synack_retries = 3`
- `net.ipv4.tcp_max_syn_backlog` is raised to at least 4096; a larger existing value is retained.

Only these keys are applied; unrelated sysctl files are not reloaded and strict
reverse-path filtering is not enabled. The setting is retained for subsequently
added nodes. This is TCP SYN-cookie/backlog tuning, not general DDoS mitigation.
It is separate from quorum, fencing and container application settings.

The checkbox configures a new installation. It does not silently retune adopted
hosts. Unchecking it later does not restore earlier kernel values or delete
administrator settings; inspect the managed file and perform an explicit host
configuration change if rollback is required.

## Optional Proxmox fencing agent and RPM packaging repair

In new-cluster Installation, **Install Proxmox fencing agent** defaults to off.
When selected, the same native package transaction installs `fence-agents-pve`;
older apt releases fall back to their combined `fence-agents` package. EL needs
an enabled repository supplying the agent, typically EPEL. Roxy-WI does not enable
that repository automatically. The setting is retained for subsequently added
nodes. Installing the agent does not create a fence device, grant hypervisor
permissions or supply fencing credentials.

During bootstrap/new-node preparation, an installed `fence_pve` is checked even
when the optional checkbox is off. The known EPEL packaging defect leaves exactly
`sys.path.append("@FENCEAGENTSLIBDIR@")` in the executable. If that exact defect is
present and `/usr/share/fence/fencing.py` exists, preparation preserves the original
under `/var/lib/roxy-wi/fence-agents/fence_pve.<sha256>.orig`, replaces only the
unexpanded path and preserves file mode/owner and SELinux context. Agent metadata
must then load successfully. A repaired bootstrap node has an audit event.
Unknown placeholders or missing libraries cause refusal; already working agents
are verified without rewriting. A package reinstall can reintroduce the vendor
bug, so check metadata after package upgrades as part of host maintenance.

This repair is confined to preparing new managed nodes. Adoption never patches
an existing host. Existing clusters must have their agent packaging reconciled
explicitly. Configure an appropriate STONITH resource and test real fencing
before relying on automatic recovery; never disable fencing to hide agent errors.
Agent parameter names can differ between package releases: inspect the installed
agent's metadata rather than copying another release's options blindly.

## Qualification and documentation maintenance

The Debian and Rocky 9.8 labs cover native cluster administration, adoption, an independent
qnetd host, membership changes, TLS qdevice, real fencing and configuration
transactions. Automated tests cover apt/dnf profile selection, unsupported
platform refusal, typed SYN options, container resource generation, permissions
and bundle action targets. Docker verification includes a fresh final controller image build/startup check;
earlier container qualification also ran backend and live cluster tests. See the
[verification record](corosync-pacemaker-verification.md) for exact counts, scope
and skipped checks, including which tests used the fresh image.

When extending a platform, add its package/release fixtures, qualify it on real
VMs, record the tested stack versions in this table and update the administration
guide and release notes in the same change. Preserve a clear distinction between
implemented, live-tested and unsupported combinations.

## Upstream references

- [Roxy-WI deployment and OS documentation](https://roxy-wi.org/installation)
- [Pacemaker container bundles](https://projects.clusterlabs.org/w/projects/pacemaker/bundle_walk-through/)
- [Corosync qdevice/qnetd](https://github.com/corosync/corosync-qdevice)
- [Linux IP sysctls](https://docs.kernel.org/networking/ip-sysctl.html)
