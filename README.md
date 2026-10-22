# Sevento — backend

Savdo, ombor, nasiya va kassa hisobi tizimi (ko'p nuqtali). Backend: Django + DRF + Channels + Celery, PostgreSQL, Redis.

Frontend alohida repoda: [sevento_front](https://github.com/shaxobiddindev/sevento_front). Ikkalasi faqat REST (`/api/v1/`) va WebSocket (`/ws/v1/`) orqali gaplashadi.

## Holat

**0-bosqich — reja.** Kod hali yo'q; quyidagi hujjatlar tasdiqlanishini kutmoqda:

| Hujjat | Mazmuni |
|---|---|
| [docs/architecture.md](docs/architecture.md) | umumiy diagramma, papka tuzilishi, qatlamlar, modullar chegarasi, strategiya/adapter joylari, API va JWT qoidalari, sozlamalar, Docker |
| [docs/er-diagram.md](docs/er-diagram.md) | ER-diagramma (Mermaid), modul bo'yicha |
| [docs/domain-events.md](docs/domain-events.md) | hodisalar mexanizmi (outbox + on_commit) va to'liq ro'yxat |
| [docs/realtime.md](docs/realtime.md) | WebSocket: ticket autentifikatsiya, guruhlar, xabar turlari, frontend qayta ulanish |
| [docs/permissions.md](docs/permissions.md) | huquqlar, rollar, nuqta chegarasi |
| [docs/roadmap.md](docs/roadmap.md) | bosqichlar va "tayyor" mezonlari |

## Ishga tushirish (1-bosqichdan keyin)

```bash
git clone https://github.com/shaxobiddindev/sevento_back
git clone https://github.com/shaxobiddindev/sevento_front   # yonma-yon papkada
cd sevento_back
cp .env.example .env
docker compose up --build
```

- API: `http://localhost:8000/api/v1/`, hujjat: `http://localhost:8000/api/v1/docs/`
- Frontend: `http://localhost:3000/`
