# Service-map UI evidence

Captured from authenticated Chromium product fixtures after the 31 October 2026 UI alignment and rebase onto upstream e825f433. Registrations, domain and notes are synthetic. The temporary test subscription adapter was used only for testing these PRs. Screenshots are interface evidence, not live infrastructure qualification.

`map.png` shows the light theme; `map-dark-1440.png` and `map-dark-390.png` show the dark theme at desktop and mobile widths. Confirmation screenshots use the upstream responsive jQuery UI dialog. Regenerate with `ROXYWI_TEST_BROWSER=1 ROXYWI_CAPTURE_MAP_DOCS=1` and `tests/product/browser/test_service_map_browser.py`.
