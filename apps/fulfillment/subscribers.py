"""sale.completed hodisasiga obuna: har bir yakunlangan savdo uchun (do'kondan olib ketilgani
ham) avtomatik ravishda omborchiga yuboriladi — endi qo'lda "yetkazishga yuborish" shart emas.
"""

import logging

from apps.accounts.models import User
from apps.sales.models import Sale
from core.events import subscribe

from . import services

logger = logging.getLogger(__name__)


@subscribe("sale.completed")
def auto_create_fulfillment(event) -> None:
    actor = User.objects.filter(pk=event.seller_id).first()
    if actor is None:
        logger.warning("sale.completed: sotuvchi topilmadi (sale_id=%s)", event.sale_id)
        return
    sale = Sale.objects.select_related("branch", "customer").get(pk=event.sale_id)
    services.create_for_sale(actor=actor, sale=sale)
