"""User-Agent satridan brauzer, OS va qurilma turini aniqlash (qo'shimcha kutubxonasiz)."""

import re

_BROWSERS = (
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/([\d.]+)")),
    ("Opera", re.compile(r"(?:OPR|Opera)/([\d.]+)")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/([\d.]+)")),
    ("Firefox", re.compile(r"(?:Firefox|FxiOS)/([\d.]+)")),
    ("Chrome", re.compile(r"(?:Chrome|CriOS)/([\d.]+)")),
    ("Safari", re.compile(r"Version/([\d.]+).*Safari/")),
)

_OSES = (
    ("Windows", re.compile(r"Windows NT")),
    ("Android", re.compile(r"Android")),
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("macOS", re.compile(r"Mac OS X|Macintosh")),
    ("Linux", re.compile(r"Linux|X11")),
)

_BOT = re.compile(r"bot|crawler|spider|curl|python-requests|postman|httpclient", re.IGNORECASE)


def parse_user_agent(user_agent: str) -> dict[str, str]:
    """{browser, os, device_type}. Noma'lum bo'lsa bo'sh satr."""
    ua = user_agent or ""
    if not ua:
        return {"browser": "", "os": "", "device_type": ""}

    browser = ""
    for name, pattern in _BROWSERS:
        match = pattern.search(ua)
        if match:
            browser = f"{name} {match.group(1).split('.')[0]}"
            break

    os_name = next((name for name, pattern in _OSES if pattern.search(ua)), "")

    if _BOT.search(ua):
        device_type = "bot"
    elif "iPad" in ua or ("Android" in ua and "Mobile" not in ua):
        device_type = "tablet"
    elif "Mobile" in ua or "iPhone" in ua or "iPod" in ua:
        device_type = "mobile"
    else:
        device_type = "desktop"

    return {"browser": browser, "os": os_name, "device_type": device_type}
