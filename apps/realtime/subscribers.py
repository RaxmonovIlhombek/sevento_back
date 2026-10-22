from core.events import Event, subscribe

from . import router


@subscribe("*")
def forward_to_websocket(event: Event) -> None:
    """Har hodisa router dan o'tadi; marshruti bo'lmasa hech narsa yuborilmaydi.

    Hodisa transaction.on_commit ichida tarqatilgani uchun MB ga yozilmagan narsa haqida
    xabar ketmaydi.
    """
    router.forward_event(event)
