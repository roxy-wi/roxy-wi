# Local passkeys screenshots

These images show the real account passkeys page in Chromium, using a synthetic
local test account and a CDP virtual authenticator. The credential name is a
sample. Recovery codes, assertions, private keys and real user/device data are
absent from the captured DOM. They are visual examples, not physical-device
qualification.

- [Light theme](light.png)
- [Dark theme](dark.png)

Reproduce with:

```sh
ROXYWI_TEST_BROWSER=1 python -m pytest tests/product/browser/test_local_passkeys_browser.py --browser chromium --browser-channel chrome --no-cov
```
