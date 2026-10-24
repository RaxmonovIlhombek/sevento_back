#!/bin/sh
set -e

# MB tayyor bo'lguncha kutish (compose healthcheck bor, bu qo'shimcha himoya)
i=0
until python manage.py check --database default >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "Ma'lumotlar bazasi javob bermayapti" >&2
    exit 1
  fi
  echo "MB kutilmoqda... ($i)"
  sleep 2
done

# Faqat asosiy (web) konteyner migratsiya va bootstrap qiladi; worker/beat RUN_MIGRATIONS=0 bilan
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py bootstrap
  # Demo ma'lumotlar (faqat sinov/ko'rgazma uchun; idempotent). Parol: DEMO_PASSWORD yoki tasodifiy
  if [ "${SEED_DEMO:-0}" = "1" ]; then
    python manage.py seed_demo
  fi
fi

exec "$@"
