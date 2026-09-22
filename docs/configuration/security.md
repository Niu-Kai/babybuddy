# Security

## `ALLOWED_HOSTS`

_Default:_ `""` (empty)

Set this variable to a single host or comma-separated list of hosts.
This should _always_ be set to a specific host or hosts in production deployments.

Do not include schemes ("http" or "https") with this setting.

**Example value**

    baby.example.test, baby.example2.test

**See also**

- [Django's documentation on the ALLOWED_HOSTS setting](https://docs.djangoproject.com/en/5.0/ref/settings/#allowed-hosts)
- [`CSRF_TRUSTED_ORIGINS`](#csrf_trusted_origins)
- [`SECURE_PROXY_SSL_HEADER`](#secure_proxy_ssl_header)

## `CORS_ALLOWED_ORIGINS`

_Default:_ `""` (no cross-origin requests allowed)

Set this variable to a single origin or comma-separated list of origins. Include schemes
("http" or "https") and any non-default ports in each origin.

This allows cross-origin requests to the API from the specified origins.

**Example value**

    https://other-domain.example.com, http://localhost:8888

**See also**

- [MDN article on CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [Making cross origin requests using fetch()](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#making_cross-origin_requests)

## `CSRF_COOKIE_SECURE`

_Default:_ `False`

If this is set to `True`, the browser CSRF cookie will be marked as "secure", which instructs the browser to only send the cookie over an HTTPS connection (never HTTP).

**See also**

- [Django's documentation on the `CSRF_COOKIE_SECURE` setting](https://docs.djangoproject.com/en/5.0/ref/settings/#csrf-cookie-secure)

## `CSRF_TRUSTED_ORIGINS`

_Default:_ `None`

If Baby Buddy is behind a proxy, you may need add all possible origins to this setting
for form submission to work correctly. Separate multiple origins with commas.

Each entry must contain both the scheme (http, https) and fully-qualified domain name.

**Example value**

    https://baby.example.test,http://baby.example2.test,http://babybudy

**See also**

- [Django's documentation on the `CSRF_TRUSTED_ORIGINS` setting](https://docs.djangoproject.com/en/5.0/ref/settings/#std:setting-CSRF_TRUSTED_ORIGINS)
- [`ALLOWED_HOSTS`](#allowed_hosts)
- [`SECURE_PROXY_SSL_HEADER`](#secure_proxy_ssl_header)

## `PROXY_HEADER`

_Default:_ `HTTP_REMOTE_USER`

Sets the header to read the authenticated username from when
`REVERSE_PROXY_AUTH` has been enabled.

Baby Buddy modifies headers in the HTTP request; HTTP headers in the request have all characters converted to uppercase, replacing any hyphens with underscores and adding an HTTP\_ prefix to the name. For example `X-Auth-User` would be converted to `HTTP_X_AUTH_USER`.

**Example value**

    // For header key X-Auth-User
    HTTP_X_AUTH_USER

**See also**

- [Django's documentation on the `REMOTE_USER` authentication method](https://docs.djangoproject.com/en/5.0/howto/auth-remote-user/)
- [Django's documentation on the request.META object](https://docs.djangoproject.com/en/5.0/ref/request-response/#django.http.HttpRequest.META)
- [`REVERSE_PROXY_AUTH`](#reverse_proxy_auth)

## `REVERSE_PROXY_AUTH`

_Default:_ `False`

Enable use of `PROXY_HEADER` to pass the username of an authenticated user.
This setting should _only_ be used with a properly configured reverse proxy to
ensure the headers are not forwarded from sources other than your proxy.

**See also**

- [`PROXY_HEADER`](#proxy_header)

## `SECRET_KEY`

_Default:_ `None`

A random, unique string must be set as the "secret key" before Baby Buddy can
be deployed and run.

See also [Django's documentation on the SECRET_KEY setting](https://docs.djangoproject.com/en/5.0/ref/settings/#secret-key).

## `SECURE_PROXY_SSL_HEADER`

_Default:_ `None`

If Baby Buddy is behind a proxy, you may need to set this to `True` in order to
trust the `X-Forwarded-Proto` header that comes from your proxy, and any time
its value is "https". This guarantees the request is secure (i.e., it originally
came in via HTTPS).

**See also**

- [Django's documentation on the SECURE_PROXY_SSL_HEADER setting](https://docs.djangoproject.com/en/5.0/ref/settings/#secure-proxy-ssl-header)
- [`ALLOWED_HOSTS`](#allowed_hosts)
- [`CSRF_TRUSTED_ORIGINS`](#csrf_trusted_origins)

## `SESSION_COOKIE_SECURE`

_Default:_ `False`

If this is set to `True`, the browser session cookie will be marked as "secure", which instructs the browser to only send the cookie over an HTTPS connection (never HTTP).

**See also**

- [Django's documentation on the `SESSION_COOKIE_SECURE` setting](https://docs.djangoproject.com/en/5.0/ref/settings/#session-cookie-secure)

## Local development and private uploads

Development installations generate a private `.development-secret-key` when
`SECRET_KEY` is not supplied. This file is ignored by Git. Keep it between restarts;
replacing it invalidates signed data and sessions. Production still requires an
explicit, strong `SECRET_KEY`, HTTPS, secure cookies, and `DEBUG=False`.

Local `/media/` requests are checked by Django: child pictures require
`core.view_child`, and note images require `core.view_note`. Thumbnails use the
same permission boundary. Session authentication and API token authentication are
supported; private media responses are not cached. Reverse proxies must forward
`/media/` to Django rather than expose `MEDIA_ROOT` directly. If using external
object storage, configure private storage and signed URLs; a public bucket bypasses
Django's access checks.

## Calendar subscriptions

Calendar URLs contain a read-only credential scoped to one child's appointments,
not the user's API key. Access is checked against the user's current permissions,
active status, and access expiration on each request. Regenerating the API key
revokes existing calendar links. After upgrading from API-key-based calendar
links, copy the new URLs from Appointments into subscribed calendar apps; old
links are rejected. Keep calendar links private and redact query strings from
proxy/access logs.

## Spreadsheet exports

Full-household exports require view permission for every exported record type in
addition to staff access. CSV and TSV exports escape formula-like text so a name
or note is not interpreted as a spreadsheet formula. Stored records are unchanged.

## API and outgoing webhooks

API list responses default to 100 records and cap `limit` at 1,000. Follow the
returned `next` URL to retrieve more records.

Webhook destinations must be HTTP(S) URLs without embedded usernames/passwords.
Use the final receiver URL: redirects are rejected. Query-string tokens are
supported and are not written to failure logs. Configure only trusted receivers;
private-network addresses remain available for Home Assistant integrations.

Events are dispatched after a database transaction commits. Delivery uses up to
four workers and 64 pending/running jobs. When full, the app logs a warning and
drops additional events instead of growing memory and threads without a limit.
Webhook delivery is best effort and is not a durable background queue.
