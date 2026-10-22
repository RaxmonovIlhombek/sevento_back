from django.conf import settings


def _cfg() -> dict:
    return settings.JWT_REFRESH_COOKIE


def get_refresh_cookie(request) -> str | None:
    return request.COOKIES.get(_cfg()["name"])


def set_refresh_cookie(response, refresh_token: str) -> None:
    cfg = _cfg()
    response.set_cookie(
        cfg["name"],
        refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=cfg["path"],
        secure=cfg["secure"],
        httponly=True,
        samesite=cfg["samesite"],
    )


def delete_refresh_cookie(response) -> None:
    cfg = _cfg()
    response.delete_cookie(cfg["name"], path=cfg["path"], samesite=cfg["samesite"])
