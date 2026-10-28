#!/bin/sh
set -e

# MB tayyor bo'lguncha kutish
i=0
until python manage.py check --database default > /dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "Ma'lumotlar bazasi javob bermayapti" >&2
    exit 1
  fi
  echo "MB kutilmoqda... ($i)"
  sleep 2
done

# Migratsiya va bootstrap
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py bootstrap
  if [ "${SEED_DEMO:-0}" = "1" ]; then
    python manage.py seed_demo
  fi
fi

exec "$@"
