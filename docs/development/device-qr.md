# Connecting a device with the QR code

Open the user menu → Add a device while signed in. The QR connects an API client as that account; it does not create a child, user, inventory record, or browser login session. Choose a caregiver/read-only account with the permissions and child access the device needs.

## Payload

The decoded text starts with the exact prefix `BABYBUDDY-LOGIN:` followed by one JSON object. Example values below are placeholders, not working credentials:

```text
BABYBUDDY-LOGIN:{"url":"https://example.com/babybuddy/","api_key":"REPLACE_WITH_SCANNED_KEY","session_cookies":{}}
```

| Field             | Meaning                                                                                                                                                                           |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `url`             | Absolute application root, including its mount path and trailing slash.                                                                                                           |
| `api_key`         | The signed-in user's persistent DRF API token. It is a credential, not a one-time code.                                                                                           |
| `session_cookies` | Usually `{}`. A detected Home Assistant ingress request can include `ingress_session` so the client can pass through that proxy. This is not a Baby Buddy browser-session cookie. |

The implementation is `UserAddDevice` in `babybuddy/views.py` and `babybuddy/templates/babybuddy/login_qr_code.txt`. Correct external host/proxy configuration is required for the generated absolute URL to be reachable from the device.

## Client flow

1. Verify the prefix, parse JSON, and validate that `url` is a trusted HTTP(S) application address. Require HTTPS outside local development. Ask the device user to confirm the server address before sending credentials.
2. Preserve the supplied base path when joining API routes. For example, append `api/children/` to `https://example.com/babybuddy/`; do not replace the path with `/api/children/`.
3. Send `Authorization: Token REPLACE_WITH_SCANNED_KEY`. Use the `Token` scheme, not `Bearer`. A first read of `api/children/` verifies permitted access; follow the API's pagination when listing records.
4. Send supplied ingress cookies only to the explicitly approved ingress host/path when required. Do not forward credentials or cookies across redirects to another origin. An expired ingress session needs a fresh proxy login; a valid Baby Buddy token alone cannot bypass the proxy.
5. Handle authentication failures, permission denials, expired account access, validation errors, and rate limits. The server rechecks model permissions and child restrictions on requests. Possessing a QR does not grant administrator rights.

Token-authenticated API requests do not need the browser's CSRF token. Session-authenticated browser writes still require CSRF protection. This mechanism is separate from calendar subscription links and does not set up Home Assistant by itself.

## Storage and revocation

Keep the decoded payload out of screenshots, analytics, crash reports, URL query strings, and ordinary logs. Store the token in the client platform's credential storage. Treat ingress cookies as credentials too; do not place either credential in the app's offline-entry database.

The account uses one API token, so multiple connected devices may share it. Regenerating the key from Add a device invalidates the old token for all those devices; reconnect each device afterward. There is no per-device token revocation in this payload format. Disabling the account or changing its permissions also affects API access. Rotating a Baby Buddy token does not revoke a separate Home Assistant ingress session.

The QR should only be scanned by a client the user trusts. It authenticates API requests; it is not single sign-on for the website.
