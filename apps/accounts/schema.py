"""drf-spectacular: o'zimizning JWTAuthentication avlodimiz uchun OpenAPI security sxemasi."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class SeventoJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.JWTAuthentication"
    name = "jwtAuth"
