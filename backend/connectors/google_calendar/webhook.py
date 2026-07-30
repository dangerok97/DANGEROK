"""Webhook placeholder.

Google Calendar supports push notifications (channels + resource watch)
but they require a public, HTTPS-reachable callback that survives across
restarts. In the current preview environment that is NOT guaranteed, so
this iteration purposefully DOES NOT enable webhook subscription.

The polling sync path (see `service.sync`) is the primary mechanism.
When we deploy on a stable domain we will:
  - POST to https://www.googleapis.com/calendar/v3/calendars/{id}/events/watch
  - Persist the channel_id + resource_id on the ConnectorInstance
  - Verify X-Goog-Channel-* headers on the callback
  - Trigger `service.sync(force_full=False)` on receipt.
"""
