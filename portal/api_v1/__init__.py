"""Read-only, machine-to-machine integration API (`/api/v1/`).

Deliberately a separate package from `portal.views`. Everything under
`portal.views` is session-authenticated and tenant-scoped through
`Ticket.for_user` / `SharedFile.for_user`; everything here is bearer-token
authenticated and crosses the tenant boundary on purpose, because its consumer
(RevenueHub) is a cross-customer health dashboard.

Because those two are opposite policies, they do not share code. The rules
this package enforces, all covered by portal/tests/test_api_v1.py:

  * GET only. There is no write path in this namespace, and the views are
    read-only generics rather than viewsets so a mutation cannot be added by
    accident.
  * The bearer authenticator never falls back to the session, and the session
    decorators never accept a bearer token. Two doors, one key each.
  * No `TicketMessage.body` and no internal note text is serialized. Serializers
    here are explicit `serializers.Serializer` allowlists, not ModelSerializers,
    so a field added to a model tomorrow cannot appear in a payload by default.
  * `Ticket.watchers` and JiraTicketLink are internal and stay out.
"""
