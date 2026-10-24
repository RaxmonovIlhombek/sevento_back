"""Demo ma'lumotlar: 3 nuqta, har rol uchun foydalanuvchi, katalog va narxlar, kirim, ko'chirish,
naqd va nasiya savdolar, qarz to'lovi, hisobdan chiqarish.

Hammasi app servislari orqali yoziladi (qoldiq, tannarx, hodisalar, audit — haqiqiy oqim bilan
bir xil). Idempotent: demo nuqtalari bor bo'lsa hech narsa qilmaydi.

    python manage.py seed_demo                    # parol tasodifiy, ekranga chiqadi
    DEMO_PASSWORD=... python manage.py seed_demo  # yoki --password
"""

import os
import secrets
from decimal import Decimal as D

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts import selectors as account_selectors
from apps.accounts import services as account_services
from apps.branches import selectors as branch_selectors
from apps.branches import services as branch_services
from apps.catalog import selectors as catalog_selectors
from apps.catalog import services as catalog_services
from apps.currency import selectors as currency_selectors
from apps.currency import services as currency_services
from apps.inventory import selectors as inventory_selectors
from apps.inventory import services as inventory_services
from apps.payments import selectors as payment_selectors
from apps.payments import services as payment_services
from apps.purchasing import services as purchasing_services
from apps.sales import services as sales_services

BRANCHES = [
    ("DEMO1", "Markaziy do'kon", "shop", "Toshkent, Amir Temur ko'chasi 1"),
    ("DEMO2", "Chilonzor do'koni", "shop", "Toshkent, Chilonzor 9-kvartal"),
    ("DEMOW", "Asosiy ombor", "warehouse", "Toshkent, Sergeli sanoat zonasi"),
]

USERS = [
    # username, F.I.Sh., rol, nuqtalar
    ("demo_buxgalter", "Karimova Dilnoza", "accountant", ["DEMO1", "DEMO2", "DEMOW"]),
    ("demo_omborchi", "Rahimov Jasur", "storekeeper", ["DEMOW"]),
    ("demo_sotuvchi1", "Toshmatov Aziz", "seller", ["DEMO1"]),
    ("demo_sotuvchi2", "Yusupova Madina", "seller", ["DEMO2"]),
]

CATEGORIES = {"Ichimliklar": None, "Oziq-ovqat": None, "Shirinliklar": "Oziq-ovqat"}

# sku, nomi, kategoriya, birlik, chakana narx (so'm), kirim narxi (USD), minimal qoldiq
PRODUCTS = [
    ("DM-001", "Coca-Cola 1,5 l", "Ichimliklar", "dona", "14000", "0.80", "10"),
    ("DM-002", "Nestle suv 1 l", "Ichimliklar", "dona", "4000", "0.20", "20"),
    ("DM-003", "Choy «Ahmad» 100 g", "Ichimliklar", "dona", "22000", "1.20", "5"),
    ("DM-004", "Guruch «Lazer»", "Oziq-ovqat", "kg", "18000", "1.05", "25"),
    ("DM-005", "Un «Oltin don» 1-nav", "Oziq-ovqat", "kg", "7500", "0.42", "50"),
    ("DM-006", "Kungaboqar yog'i 1 l", "Oziq-ovqat", "l", "23000", "1.40", "10"),
    ("DM-007", "Shokolad «Alpen Gold»", "Shirinliklar", "dona", "15000", "0.85", "10"),
    ("DM-008", "Pechenye «Yubileynoe»", "Shirinliklar", "dona", "9000", "0.48", "15"),
]


class Command(BaseCommand):
    help = "Demo ma'lumotlarni yaratadi (servislar orqali, idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Demo foydalanuvchilar paroli (yoki DEMO_PASSWORD). Berilmasa — tasodifiy.",
        )

    def handle(self, *args, **options):
        if branch_selectors.all_branches().filter(code="DEMO1").exists():
            self.stdout.write("Demo ma'lumotlar allaqachon bor — o'tkazib yuborildi")
            return
        owner = account_selectors.users_queryset().filter(is_superuser=True).first()
        if owner is None:
            raise CommandError("Avval rahbar kerak: python manage.py bootstrap")
        self._check_conflicts()
        password = options["password"] or os.environ.get("DEMO_PASSWORD") or ""
        generated = not password
        password = password or secrets.token_urlsafe(9)

        account_services.ensure_preset_roles()
        with transaction.atomic():
            self._seed(owner, password)

        self.stdout.write(self.style.SUCCESS("Demo ma'lumotlar yaratildi"))
        names = ", ".join(u[0] for u in USERS)
        if generated:
            self.stdout.write(f"Foydalanuvchilar: {names} — parol: {password}")
        else:
            self.stdout.write(f"Foydalanuvchilar: {names} — parol berilganidek")

    def _check_conflicts(self):
        """Mavjud ma'lumot bilan to'qnashuv bo'lsa — hech narsa yozmasdan to'xtaydi."""
        usernames = [u[0] for u in USERS]
        taken = list(
            account_selectors.users_queryset()
            .filter(username__in=usernames)
            .values_list("username", flat=True)
        )
        skus = list(
            catalog_selectors.products_queryset()
            .filter(sku__in=[p[0] for p in PRODUCTS])
            .values_list("sku", flat=True)
        )
        if taken or skus:
            raise CommandError(
                "Demo ma'lumot mavjud ma'lumot bilan to'qnashadi: " + ", ".join(taken + skus)
            )

    def _seed(self, owner, password):
        uzs = currency_selectors.get_currency("UZS")
        usd = currency_selectors.get_currency("USD")
        if currency_selectors.latest_rate(usd) is None:
            currency_services.set_rate(actor=owner, currency=usd, rate=D("12650"))

        branches = {
            code: branch_services.create_branch(
                actor=owner, code=code, name=name, type=kind, address=address
            )
            for code, name, kind, address in BRANCHES
        }
        roles = {r.code: r for r in account_selectors.roles_queryset()}
        users = {}
        for username, full_name, role, codes in USERS:
            users[username] = account_services.create_user(
                actor=owner,
                username=username,
                password=password,
                full_name=full_name,
                role=roles[role],
                branch_ids=[branches[c].pk for c in codes],
                default_branch_id=branches[codes[0]].pk,
            )

        categories = {}
        for name, parent in CATEGORIES.items():
            categories[name] = catalog_services.create_category(
                actor=owner, name=name, parent=categories.get(parent) if parent else None
            )
        units = {u.code: u for u in catalog_selectors.units_queryset()}
        retail = catalog_selectors.default_price_type()
        products = {}
        for sku, name, category, unit, price, _cost, minimum in PRODUCTS:
            product = catalog_services.create_product(
                actor=owner,
                sku=sku,
                name=name,
                category=categories[category],
                unit=units[unit],
                barcode=f"478{sku[-3:]}0000{sku[-3:]}",
                min_quantity=D(minimum),
            )
            catalog_services.set_price(
                actor=owner, product=product, price_type=retail, currency=uzs, amount=D(price)
            )
            products[sku] = product

        supplier = purchasing_services.save_supplier(
            actor=owner, name="«Toshkent Savdo» MChJ", phone="+998712000001"
        )
        local = purchasing_services.save_supplier(
            actor=owner, name="«Barakali Non» MChJ", phone="+998712000002"
        )
        cost = {p[0]: D(p[5]) for p in PRODUCTS}
        keeper = users["demo_omborchi"]

        # ombor: katta kirim (USD), do'konlarga ko'chirish
        big = purchasing_services.create_purchase(
            actor=keeper,
            branch=branches["DEMOW"],
            supplier=supplier,
            currency=usd,
            invoice_number="TS-2026-0412",
            items=[
                {"product": products[sku], "quantity": D(qty), "unit_price": cost[sku]}
                for sku, qty in [
                    ("DM-001", "120"),
                    ("DM-002", "200"),
                    ("DM-003", "40"),
                    ("DM-004", "300"),
                    ("DM-005", "500"),
                    ("DM-006", "80"),
                    ("DM-007", "100"),
                    ("DM-008", "150"),
                ]
            ],
        )
        purchasing_services.receive_purchase(actor=keeper, purchase=big)
        for code, share in (("DEMO1", D("0.3")), ("DEMO2", D("0.2"))):
            transfer = inventory_services.create_transfer(
                actor=keeper,
                from_branch=branches["DEMOW"],
                to_branch=branches[code],
                items=[
                    {"product": products[sku], "quantity": (D(qty) * share).quantize(D("1"))}
                    for sku, qty in [
                        ("DM-001", "120"),
                        ("DM-002", "200"),
                        ("DM-003", "40"),
                        ("DM-004", "300"),
                        ("DM-007", "100"),
                        ("DM-008", "150"),
                    ]
                ],
                note="Haftalik ta'minot",
            )
            inventory_services.send_transfer(actor=keeper, transfer=transfer)
            inventory_services.receive_transfer(actor=owner, transfer=transfer)

        # Chilonzor: mahalliy yetkazib beruvchidan so'mda kirim
        bread = purchasing_services.create_purchase(
            actor=owner,
            branch=branches["DEMO2"],
            supplier=local,
            currency=uzs,
            items=[{"product": products["DM-005"], "quantity": D("40"), "unit_price": D("5300")}],
        )
        purchasing_services.receive_purchase(actor=owner, purchase=bread)

        methods = {m.code: m for m in payment_selectors.active_payment_methods()}
        sales = [
            ("demo_sotuvchi1", "DEMO1", [("DM-001", "3"), ("DM-007", "2")], "cash"),
            ("demo_sotuvchi1", "DEMO1", [("DM-004", "5"), ("DM-002", "6")], "card"),
            ("demo_sotuvchi1", "DEMO1", [("DM-003", "1"), ("DM-008", "4")], "cash"),
            ("demo_sotuvchi2", "DEMO2", [("DM-005", "10"), ("DM-001", "2")], "cash"),
            ("demo_sotuvchi2", "DEMO2", [("DM-007", "5")], "card"),
        ]
        for seller, code, lines, method in sales:
            items = [{"product": products[sku], "quantity": D(q)} for sku, q in lines]
            total = sum(
                (D(next(p[4] for p in PRODUCTS if p[0] == sku)) * D(q) for sku, q in lines), D(0)
            )
            sales_services.create_sale(
                actor=users[seller],
                branch=branches[code],
                currency=uzs,
                items=items,
                payments=[{"method": methods[method], "currency": uzs, "amount": total}],
            )

        # nasiya: mijoz 200 000 so'mlik oldi (50 000 naqd, qolgani qarz), keyin 100 000 to'ladi
        customer = payment_services.save_customer(
            actor=owner,
            name="Aliyev Vali",
            phone="+998901234567",
            credit_limit_base=D("150"),
        )
        payment_services.save_customer(
            actor=owner, name="«Mehr» kafe", phone="+998935554433", credit_limit_base=D("500")
        )
        sales_services.create_sale(
            actor=users["demo_sotuvchi1"],
            branch=branches["DEMO1"],
            currency=uzs,
            items=[
                {"product": products["DM-004"], "quantity": D("10")},
                {"product": products["DM-002"], "quantity": D("5")},
            ],
            payments=[{"method": methods["cash"], "currency": uzs, "amount": D("50000")}],
            customer=customer,
        )
        payment_services.receive_debt_payment(
            actor=users["demo_sotuvchi1"],
            customer=customer,
            branch=branches["DEMO1"],
            method=methods["cash"],
            currency=uzs,
            amount=D("100000"),
        )

        # ombor: 2 dona shokolad buzilgan
        reason = inventory_selectors.write_off_reasons(manual_only=True).first()
        if reason is not None:
            inventory_services.create_write_off(
                actor=keeper,
                branch=branches["DEMOW"],
                reason=reason,
                items=[{"product": products["DM-007"], "quantity": D("2")}],
                note="Qadoq yirtilgan",
            )
