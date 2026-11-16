# Instagram Unified Login

Goal: connect an owned tester Instagram account from Telepipe using the Meta app already configured.

Use the existing Next.js OAuth state/ownership boundary and encrypted token storage. Replace Instagram Login with config_id-based Facebook Login for Business. Discover assigned Instagram accounts explicitly; fail safely if selection is ambiguous. Store the client business/config IDs and token type. Non-expiring SUAT tokens must never be passed to Instagram's legacy refresh endpoint. Worker uses graph.facebook.com with the stored Instagram account ID. Keep replies off until the owner enables them.

- [ ] Add regression tests for the login URL, code exchange, account discovery and worker URLs.
- [ ] Migrate OAuth, schema, token handling and connection guidance.
- [ ] Configure server-only Meta credentials on Vercel; migrate DB.
- [ ] Validate web/worker, commit and push; deploy web and worker.
- [ ] Verify production login entry without granting/connecting on the user's behalf.

Reference: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-unified-login/get-started
