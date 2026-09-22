# A configuration change from draft to deployment

> Applies to **Roxy-WI 9.1 and later**.

**Available with Premium.** This walkthrough uses a test HAProxy cluster with a
primary and two replicas. The names below are illustrative; no public demo server
or production configuration needs to be changed to read the tour.

## 1. Prepare the change

Connect your test cluster and open its HAProxy configuration editor. Make a small,
valid change suitable for your test setup. Select **Create change** and give it a
name that describes the intended result, such as “Adjust the test backend timeout”.
Select **Reload**, a rolling deployment, one replica as the canary, and manual
promotion between batches. Enable approval by another administrator if a reviewer
is available in the same group.

The draft captures the proposed configuration and rollout targets. The existing
configuration on each target is saved separately for rollback. Creation does not
apply the candidate to the live service.

## 2. Review and validate

Open the change details and inspect the highlighted diff and selected targets.
Choose **Validate**. Each included target must accept its configuration before the
change can proceed. A validation failure remains visible with that node's output.

If approval is required, a second administrator reviews and approves the validated
change. The author cannot approve their own request.

## 3. Start with the canary

Deploy the approved or validated change. Follow the rollout table and timeline:
the selected replica is updated first, and the configured health checks run.
With manual promotion enabled, the rollout waits before continuing.

Inspect the test service, then select **Promote** to proceed. Remaining replicas
are processed before the primary. The table records the outcome for each target.

## 4. Inspect the result

Open the completed change to review target output, who approved it and the
deployment timeline. Use **Check drift** to compare current configurations with
the deployed baseline. A difference is reported for review; drift detection does
not silently overwrite the server.

## 5. Understand recovery before you need it

When deployment or a configured post-deployment health check fails, the rollout
stops and attempts to restore targets affected by that attempt. Check the final
state: **Auto rolled back** and **Auto rollback failed** mean different things.
The details identify any target that still needs attention.

You can also roll back a completed test deployment. An interrupted operation has
explicit recovery controls; inspect remote state and target output before retrying.

| Question during an incident | Where to look |
| --- | --- |
| What changed? | The candidate diff |
| Who reviewed it? | Approval and audit history |
| Which servers were affected? | The rollout targets and per-node results |
| Did recovery succeed? | Rollback status and target output |
| Has somebody edited it since? | Drift results |

Read the [complete Change Center reference](https://roxy-wi.org/description/change-center)
for scheduling, maintenance windows, webhooks and the status reference.

[Project overview](../README.md) · [Documentation index](README.md)
