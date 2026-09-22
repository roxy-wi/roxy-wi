# Maintainer guide

This checklist applies to **Roxy-WI 9.1 and later**.

## Prepare a release

1. Update [release notes](../CHANGELOG.md) with user-visible outcomes, required
   deployment actions and any verified limitations. Keep application, package and
   chart version metadata consistent with the intended release.
2. Run Tests, Container and CodeQL on the release revision. Inspect the Linux LE
   deployment result and the quick-start HTTPS login/restart result. Complete the
   public-domain staging checks described in [LE](letsencrypt.md#release-verification).
3. Confirm installation, restart and restore on the deployment modes being shipped.
   Review package metadata and the intended release tag.
4. Re-run documentation link checks. Try the README commands from a clean checkout
   on a machine with Docker, and verify the demo link and credentials.
5. Publish the approved release tag and inspect the
   [native package workflow](../.github/workflows/native-packages.yml), which builds,
   signs, publishes and verifies the packages. Its manual dispatch also publishes
   packages. Create the GitHub release with the operator-facing changes and links
   to the relevant guides.

## Repository presentation

Keep GitHub's About section, topics and social preview aligned with the README.
Suggested About description:

> Self-hosted management for HAProxy, NGINX, Apache and Keepalived. Review changes, coordinate deployments, manage certificates and track service health.

Use `https://roxy-wi.org` as the website. Suggested topics: `haproxy`, `nginx`,
`apache`, `keepalived`, `load-balancer`, `reverse-proxy`, `configuration-management`,
`monitoring`, `self-hosted` and `devops`.

For the social preview, use the Roxy-WI logo, one short value statement and a real
UI screenshot with demonstration data. Update screenshots when the interface
changes; avoid screenshots containing customer hosts, credentials or license data.

These are repository settings managed in GitHub; changing this guide does not
publish a release or update those settings.
