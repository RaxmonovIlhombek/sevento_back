import uuid

from .context import RequestContext, reset_context, set_context


def get_client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    """Har so'rovga request_id beradi va kontekstni o'rnatadi; javobda X-Request-ID qaytaradi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16])[:64]
        request.request_id = request_id
        token = set_context(
            RequestContext(
                request_id=request_id,
                ip=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
        )
        try:
            response = self.get_response(request)
        finally:
            reset_context(token)
        response["X-Request-ID"] = request_id
        return response
