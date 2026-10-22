from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication

from core.context import update_context


class JWTAuthentication(BaseJWTAuthentication):
    """Standart JWT auth + kim ekanini so'rov kontekstiga yozadi (hodisalar va audit uchun)."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            update_context(actor_id=result[0].pk)
        return result
