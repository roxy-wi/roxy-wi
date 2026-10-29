# Local TOTP screenshots

`enabled-light.png` and `enabled-dark.png` come from the real Flask application,
a fresh synthetic SQLite fixture and Chrome browser tests. They show the enabled
state after QR/setup-key fields are cleared and the one-time recovery-code dialog
is closed. No real infrastructure, passwords, OTP setup secret, QR or recovery
codes appear in these captures. The test also verifies the setup/confirmation and
subsequent MFA login flows before/after capture.

Reproduce with `ROXYWI_TEST_BROWSER=1 pytest tests/product/browser/test_local_totp_browser.py --browser chromium --browser-channel chrome --no-cov`.
