# Planned Corosync transport migration

Open **Services → Corosync / Pacemaker → Quorum → Planned migration to managed
Corosync transport**. This explicitly converts an adopted/custom configuration to
the generated authenticated knet configuration and enables Roxy-WI membership
management. It is a maintenance workflow with application downtime.

1. Choose the token timeout and **Review transport migration**. Roxy-WI reads all
   Corosync files, requires identical configuration and matching existing default
   authentication-key digests, and syntax-checks the proposed configuration on
   every member. Compare the complete current/proposed files in the web editors.
   Custom transport options are replaced by the displayed managed configuration.
2. Select **Quiesce applications** and type the cluster name. Roxy-WI records which
   nodes were previously available, puts all members into standby and waits for
   managed application resources to stop. Unmanaged resources, maintenance mode,
   disabled fencing, offline/unclean members or lack of quorum block this workflow.
   Standby is a real resource drain; maintenance mode alone would not stop workloads.
3. Review again and **Apply reviewed transport**, confirming the cluster name.
   The worker rechecks the plan and stopped applications, prepares private backups
   on every node, and arms independent **240-second** host recovery timers before
   stopping any cluster daemon. Authentication keys and the CIB are retained.
4. Pacemaker/qdevice/Corosync stop cleanly on all nodes before any new transport
   file is installed. Corosync starts on every member; each must report all members
   and quorum before Pacemaker starts. The existing TLS witness/votes are verified.
   Nodes and application resources remain in standby. Only then is the migration
   committed and managed membership enabled.
5. Inspect cluster health and use **Resume previous nodes**, with confirmation, to
   restore only the node availability changed by this maintenance operation.
   Previously standby nodes remain standby. Inspect application status afterward.

An existing net witness is mapped to an enabled registered server at its actual
IP and keeps its CA/client certificates. Complete a witness trust migration in its
own installer first when changing CA or host. The managed transport wizard does
not combine those two independent changes.

## Interrupted migration

**Recover original transport** restores the original file on every node. Recovery
checks the registered membership and SSH identities, stops Pacemaker everywhere,
restores Corosync, and proves every original member has quorum before starting
Pacemaker. Nodes stay in standby until **Resume previous nodes** is confirmed.
Other mutating cluster operations are blocked while transport recovery is pending.

If the controller disappears after the switch, each host timer restores its local
original configuration and starts Corosync, while leaving Pacemaker stopped. It
never starts application workloads independently. Use GUI recovery to finish the
coordinated recovery. A late timer cannot undo a committed change.

Private backups and recovery programs reside under
`/var/lib/roxy-wi/transport/<id>`; the controller stores the pending identity and
previous registration settings. Loss of the hosts/backups or revoked SSH access
requires external host recovery.

The wizard retains the existing membership, cluster name and default
`/etc/corosync/authkey`. Custom key locations/inline keys must be reconciled before
using this managed profile; it does not silently substitute unknown key material.
Different node files, unsupported witness models or non-TLS witness configurations
are refused. Arbitrary multi-ring transport design and application deployment
remain separate configuration work, rather than inferred from a single address.
