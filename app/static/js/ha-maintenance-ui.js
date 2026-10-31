/* Shared maintenance status and review presentation for HA and Change Center. */
window.RoxywiMaintenance = (() => {
    function node(tag, text) {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        return element;
    }

    function canApprove(plan, userId) {
        return !plan.operation && plan.change_status === 'pending_approval' &&
            plan.approvers.some(user => user.id === userId);
    }

    function status(plan) {
        if (plan.operation) return plan.operation.status === 'running' ? 'Running' : 'Queued';
        if (['reviewed', 'return-reviewed'].includes(plan.status)) {
            const action = plan.status === 'reviewed' ? 'Drain' : 'Return';
            return action + (plan.change_status === 'approved' ? ' approved' : ' awaiting approval');
        }
        return {draft: 'Draft', 'review-failed': 'Checks failed', draining: 'Verifying drain',
            ready: 'Ready for maintenance', unknown: 'State needs verification', resuming: 'Returning node',
            completed: 'Completed', cancelled: 'Cancelled'}[plan.status] || plan.status;
    }

    function nextStep(plan, userId) {
        if (plan.operation) return `Operation #${plan.operation.id}: ${plan.operation.status}. Results update automatically.`;
        if (plan.status === 'draft' || plan.status === 'review-failed') {
            return 'Run drain checks to verify quorum, workload placement and VIP ownership. These checks do not change the node.';
        }
        if (['reviewed', 'return-reviewed'].includes(plan.status)) {
            const returning = plan.status === 'return-reviewed';
            if (plan.change_status === 'approved') return returning
                ? 'Return is approved. Return the node when the maintenance work is complete.'
                : 'Drain is approved. Drain the node and wait for verification before starting maintenance.';
            return canApprove(plan, userId)
                ? 'Review the check results and capacity evidence below, then approve this step.'
                : 'Waiting for another administrator to approve the current check results. This page updates automatically.';
        }
        return {ready: 'The drain is verified. Perform maintenance, then run return checks before bringing the node back.',
            unknown: 'The previous operation could not confirm the node state. Verify the drain or run return checks to recover.',
            draining: 'Verify that resources and connections have left the node before starting maintenance.',
            completed: 'The node has returned and its state has been verified.',
            cancelled: 'This plan was cancelled.'}[plan.status] || '';
    }

    function approval(plan, userId) {
        if (plan.change_status === 'approved') return 'Approved by ' + (plan.approved_by_name || `user #${plan.approved_by}`) + '.';
        if (['completed', 'cancelled'].includes(plan.status)) return '';
        const prefix = plan.user_id === userId ? 'You created this plan and cannot approve it. ' : '';
        return prefix + (plan.approvers.length
            ? 'Eligible approvers: ' + plan.approvers.map(user => user.name).join(', ') + '.'
            : 'No other enabled administrator with HA access is available in this group. Add one in the Admin area before approval.');
    }

    function review(plan) {
        if (!plan.review) return null;
        const details = node('details');
        details.className = 'change-advanced-settings maintenance-review';
        details.dataset.maintenanceDetail = 'review';
        details.open = plan.change_status === 'pending_approval';
        details.append(node('summary', plan.review.returning ? 'Return check results' : 'Drain check results'));
        if (plan.review.reviewed_at) details.append(node('p', 'Checked: ' + new Date(plan.review.reviewed_at).toLocaleString()));
        const view = plan.review.view;
        if (view.quorum) details.append(node('p', `Quorum: ${view.quorum.remaining} votes remain; ${view.quorum.required} required.`));
        if (view.vips) details.append(node('p', 'VIPs: ' + (view.vips.join(', ') || 'None')));
        const list = node('ul');
        if (view.predicted) {
            view.predicted.resources.forEach(resource => {
                if (resource.active === 'true') list.append(node('li', `${resource.id || resource.target_id}: ${resource.nodes.join(', ')}`));
            });
            details.append(node('p', 'Predicted active resource placement:'));
        } else if (view.owners) {
            Object.entries(view.owners).forEach(([vip, owners]) => list.append(node('li', vip + ': ' + owners.map(id =>
                view.nodes.find(member => member.id === id)?.name || `node #${id}`).join(', '))));
            details.append(node('p', 'Observed VIP owners:'));
        }
        if (list.children.length) details.append(list);
        const raw = node('details');
        raw.dataset.maintenanceDetail = 'raw-review';
        raw.append(node('summary', 'Technical details'), node('pre', JSON.stringify(plan.review, null, 2)));
        details.append(raw);
        return details;
    }

    return {node, canApprove, status, nextStep, approval, review};
})();
