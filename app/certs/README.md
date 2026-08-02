# TLS certificates

TLS private keys must not be committed to this repository. Install a certificate and private key outside the web root:

- `/etc/roxy-wi/certs/roxy-wi.crt`
- `/etc/roxy-wi/certs/roxy-wi.key` (mode `0600`)

The supplied Apache virtual-host configurations use these paths.
