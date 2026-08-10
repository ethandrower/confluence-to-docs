"""Schema + Swagger UI, gated.

drf-spectacular's stock views are `AllowAny`. An open schema endpoint publishes
the field names, filters and URL shape of a cross-tenant support dataset to
anyone who finds the path, which is free reconnaissance, so both views are
narrowed to "valid bearer token OR Django admin session" here. SessionAuth is
allowed on THESE TWO VIEWS ONLY, and only because a human reading the docs in a
browser has a cookie rather than a token — it is never mixed into the data
endpoints.
"""
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication

from .auth import ApiClientAuthentication, IsApiClientOrAdminSession


class GuardedSchemaView(SpectacularAPIView):
    authentication_classes = [ApiClientAuthentication, SessionAuthentication]
    permission_classes = [IsApiClientOrAdminSession]
    http_method_names = ['get', 'head', 'options']


class GuardedSwaggerView(SpectacularSwaggerView):
    authentication_classes = [ApiClientAuthentication, SessionAuthentication]
    permission_classes = [IsApiClientOrAdminSession]
    http_method_names = ['get', 'head', 'options']
