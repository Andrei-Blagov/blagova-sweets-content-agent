# BLAGOVA_SWEETS Content Agent

AI-агент для генерации готовых постов социальных сетей бренда **BLAGOVA_SWEETS** на основе URL страницы или вручную переданного текста.

Рабочий инструмент контента бренда: CLI, Web UI с авторизацией, FastAPI, история генераций, Telegram-бот и Docker.

**Production:** https://content.blagovasweets.com

## Задача проекта

1. Получить URL или текст.
2. Загрузить и очистить HTML (если URL).
3. Извлечь полезное содержание.
4. Передать контекст в LLM (OpenAI-compatible API).
5. Сформировать короткий пост в заданном стиле и для выбранной площадки.
6. Вернуть один готовый текст с контролем длины и антигаллюцинациями.

## Бренд (важно)

**BLAGOVA_SWEETS** — авторская кондитерская / dessert & coffee concept (десерты, шоколад, уютная кофейная культура).  
Это **не** традиционная пекарня/булочная.

Правила генерации:

- имя бренда всегда **BLAGOVA_SWEETS** (с подчёркиванием);
- факты бизнеса берутся только из входного источника (`FACTS_FROM_SOURCE`);
- нельзя выдумывать цены, адреса, наличие, доставку, открытие кофейни/точки в Паттайе и т.п.;
- CTA вида «приходите» запрещены, если посещение не подтверждено источником.

## Возможности

- CLI (`agent.py`)
- FastAPI + Swagger / ReDoc (`/docs`, `/redoc`, `/openapi.json`)
- Web UI с брендированным логином и анимацией входа (~1.5 с)
- Session-auth: роли **ADMIN** и **GOST** (guest)
- Telegram-бот (опционально, через `BOT_TOKEN`)
- Площадки: `telegram`, `vk`, `instagram`, `universal`
- Стили: `ironic`, `friendly`, `selling`, `expert`, `warm`, `premium`, `short` + произвольная строка
- Цели поста: `product`, `sales`, `new_product`, `informational`, `promo`, `holiday`, `engagement`
- CTA и хэштеги (опционально)
- История генераций (SQLite)
- SSRF-защита при загрузке URL
- Docker / docker-compose + hourly auto-update на VPS

## Авторизация и роли

Доступ к Web UI, генерации и истории — через cookie-сессию после логина.

| | ADMIN | GOST (guest) | Неавторизован |
|---|---|---|---|
| Web UI | да | да | только экран входа |
| `/api/generate` | да | да | 401 |
| `/api/history` | вся история | только своя сессия | 401 |
| `/docs`, `/redoc`, `/openapi.json` | да | да | 401 |
| Admin-only endpoints (`require_admin`) | да | 403 | 401 |
| `/health` | публичный | публичный | публичный |

GOST может открыть Swagger и вызвать разрешённые ему endpoints (генерация, своя история).  
RBAC на backend **не ослаблен**: admin-only по-прежнему возвращает **403**.

Ссылка «API Docs» в футере Web UI видна и ADMIN, и GOST.

### Переменные auth в `.env`

| Переменная | Описание |
|---|---|
| `SESSION_SECRET` | секрет подписи cookie-сессии |
| `ADMIN_PASSWORD_HASH` | Argon2-хеш пароля администратора |
| `GUEST_PASSWORD_HASH` | Argon2-хеш гостевого пароля |
| `GUEST_ENABLED` | `true` / `false` — включить гостевой вход |
| `ADMIN_SESSION_TTL_MINUTES` | TTL сессии admin (по умолчанию `720`) |
| `GUEST_SESSION_TTL_MINUTES` | TTL сессии guest (по умолчанию `240`) |
| `COOKIE_SECURE` | `true` в production (HTTPS) |
| `APP_ENV` | `production` / `development` |

Сгенерировать хеш:

```bash
python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your-password'))"
```

**Docker Compose:** в `.env` каждый символ `$` в Argon2-хеше экранируйте как `$$`, иначе Compose «съест» часть хеша.

Пароли и секреты — только на сервере в `.env`, никогда в Git.

## Архитектура

```
URL / Text
  → Content extraction (webpage_parser)
  → ContentAgent
  → OpenAI (openai_client + prompts)
  → validation / length control
  → post (+ history)
```

Интерфейсы (`CLI`, `API`, `Web UI`, `Telegram`) используют один и тот же `ContentAgent`.

## Структура проекта

```text
blagova-sweets-content-agent/
├── app/
│   ├── config.py
│   ├── models.py
│   ├── content_agent.py
│   ├── openai_client.py
│   ├── webpage_parser.py
│   ├── prompts.py
│   ├── history.py
│   ├── auth/                 # session auth, Argon2, RBAC deps
│   ├── api/
│   │   └── routes.py
│   └── telegram/
│       └── bot.py
├── frontend/                 # Web UI + logo/favicon assets
├── scripts/
│   └── update.sh             # hourly VPS auto-update
├── data/
├── tests/
├── agent.py
├── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Pipeline

```text
INPUT (url | text)
↓
получение HTML или нормализация текста
↓
очистка и компактное представление
↓
system + user prompt (бренд BLAGOVA_SWEETS)
↓
генерация через OpenAI API
↓
постпроцессинг и проверка max_length
↓
готовый пост (+ запись в историю)
```

## Установка

Требования: Python 3.10+.

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Настройка `.env`

```bash
copy .env.example .env   # Windows
cp .env.example .env     # Linux / macOS
```

Основные переменные:

| Переменная | Описание |
|---|---|
| `OPENAI_API_KEY` | ключ OpenAI / совместимого API |
| `BASE_URL` | базовый URL API, например `https://api.openai.com/v1` |
| `OPENAI_MODEL` | модель (по умолчанию `gpt-4o-mini`) |
| `BOT_TOKEN` | токен Telegram-бота (опционально) |
| `APP_HOST` | хост API (по умолчанию `0.0.0.0`) |
| `APP_PORT` | порт API (по умолчанию `8090`) |
| `DB_PATH` | путь к SQLite (в Docker: `/app/data/history.db`) |
| `REQUEST_TIMEOUT` | таймаут HTTP к страницам |
| `LOG_LEVEL` | уровень логов |

Плюс auth-переменные из раздела выше. Файл `.env` не должен попадать в Git.

## CLI

CLI **не** требует Web-сессии (работает локально с вашим `.env` / OpenAI key).

```bash
python agent.py --url https://example.com
python agent.py --url https://example.com --style ironic
python agent.py --url https://example.com --style friendly --platform telegram
python agent.py --text "Сегодня подготовили новую партию капкейков" --style selling
python agent.py --text "..." --style warm --goal product --max-length 500 --cta
```

По умолчанию для CLI:

- `--style ironic`
- `--platform telegram`
- `--goal product`
- `--max-length 800`

`--url` и `--text` взаимоисключающие. На stdout печатается преимущественно готовый пост.

## API

Запуск локально:

```bash
python main.py
# или
uvicorn main:app --host 0.0.0.0 --port 8090
```

Проверка:

- UI: http://127.0.0.1:8090/
- Health: http://127.0.0.1:8090/health (публичный)
- Swagger: http://127.0.0.1:8090/docs (нужна сессия ADMIN или GOST)

Логин и генерация через curl (cookie jar):

```bash
# login
curl -c cookies.txt -X POST http://127.0.0.1:8090/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"role\":\"admin\",\"password\":\"YOUR_PASSWORD\"}"

# generate
curl -b cookies.txt -X POST http://127.0.0.1:8090/api/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Сегодня в BLAGOVA_SWEETS подготовили свежие капкейки.\",\"platform\":\"telegram\",\"style\":\"warm\",\"goal\":\"product\",\"max_length\":500,\"cta\":true,\"hashtags\":false}"

# history
curl -b cookies.txt http://127.0.0.1:8090/api/history
```

Ответ генерации:

```json
{
  "post": "...",
  "length": 534,
  "platform": "telegram",
  "style": "warm",
  "goal": "product",
  "source_type": "text"
}
```

Auth endpoints:

- `POST /auth/login` — `{ "role": "admin"|"guest", "password": "..." }`
- `POST /auth/logout`
- `GET /auth/me`

## Web UI

Откройте http://127.0.0.1:8090/ (локально) или https://content.blagovasweets.com (production).

В интерфейсе:

- логин ADMIN / GOST с анимацией появления (~1.5 с)
- переключатель URL / Текст
- площадка, стиль, цель
- max length, CTA, hashtags
- готовый пост + копирование
- блок «Последние генерации» (у GOST — только текущая сессия)
- ссылка «API Docs» для обеих ролей

Для Web UI стиль по умолчанию — `friendly`.

## Telegram bot

Бот опционален. Если `BOT_TOKEN` пустой, API и CLI работают как обычно.

Локальный запуск:

```bash
python -m app.telegram.bot
```

Сценарий:

1. `/start` — краткое описание
2. `/post` — бот просит URL или текст
3. выбор стиля
4. бот возвращает готовый пост и число символов

Telegram использует общий `ContentAgent` с безопасными default’ами (в т.ч. без агрессивного CTA).

Через Docker Compose профиль `bot`:

```bash
docker compose --profile bot up -d --build
```

У сервиса `telegram-bot` healthcheck отключён (наследование API-healthcheck давало ложный `unhealthy`).

## Docker

### Сборка и запуск API

```bash
docker compose up -d --build
```

В production compose порт API проброшен только на localhost:

```text
127.0.0.1:8090:8090
```

Публичный HTTPS — через reverse proxy (Caddy) на хосте `content.blagovasweets.com`.  
Сеть `n8n_n8n_net` подключена как external для прокси.

### Обновление на VPS

Вручную:

```bash
cd /opt/projects/blagova-sweets-content-agent
git pull
docker compose --profile bot up -d --build
docker compose ps
docker compose logs -f api
```

Автоматически (каждый час через cron):

```bash
# скрипт в репозитории
scripts/update.sh

# cron (пример)
15 * * * * /opt/projects/blagova-sweets-content-agent/scripts/update.sh
```

Скрипт:

- `git fetch` / `git pull --ff-only` только при новых коммитах;
- пересобирает контейнеры через `docker compose --profile bot up -d --build`;
- пишет лог в `/home/andrei/logs/blagova-sweets-content-agent-update.log`;
- не запускает параллельно (flock);
- если `.env` ещё нет — пропускает обновление (ожидает первичный деплой);
- `.env` на сервере **не перезаписывается** из Git.

### Production-заметки

- секреты только в `.env` на сервере, не в образе и не в репозитории;
- наружу — Caddy/Nginx → `127.0.0.1:8090`, не публикуйте API напрямую на `80/443`;
- Argon2-хеши в Compose: `$` → `$$`;
- для бота — профиль `bot`.

## Тесты

```bash
pytest -q
```

Покрыто:

- валидация URL / SSRF
- очистка HTML
- ограничение `max_length`
- валидация входных данных
- формирование prompt / бренд-правила
- API smoke с mock OpenAI
- auth: login, logout, session TTL
- unauthenticated `/docs` → denied
- guest `/docs` → allowed
- admin `/docs` → allowed
- guest → admin-only endpoint → 403
- guest history scoped to session

Реальный OpenAI API в тестах не вызывается.

## Security

- `.env` в `.gitignore`
- ключи и пароли не логируются и не хранятся в plaintext в репозитории
- session cookie: HttpOnly, SameSite=Lax, Secure в production
- rate-limit на неудачные попытки логина
- запрещены `file://` и не-HTTP(S) схемы
- блокируются `localhost`, `127.0.0.1`, `0.0.0.0`, `::1` и private IP
- перед запросом hostname резолвится через DNS; private/loopback IP отклоняются
- повторная проверка hostname после redirect
- лимит размера HTML-ответа
- в LLM уходит компактный текст, а не сырой HTML

## Примеры использования для BLAGOVA_SWEETS

```bash
python agent.py --text "Сегодня в BLAGOVA_SWEETS подготовили свежую партию капкейков. Они доступны сегодня в ограниченном количестве." --style warm --platform telegram --goal product --max-length 500 --cta
```

Ожидаемо:

- пост в тёплом тоне авторской кондитерской;
- без выдуманных цен, адресов, состава и скидок;
- длина ≤ 500;
- CTA только в рамках подтверждённых фактов источника.

## Состав продукта

- Web UI с брендированным логином
- Session auth (ADMIN / GOST) + RBAC
- FastAPI + Swagger/ReDoc для авторизованных ролей
- Telegram-бот
- несколько платформ и стилей
- цели постов (`goal`)
- история генераций (SQLite) с изоляцией guest-сессий
- Docker / docker-compose + Caddy-ready production
- hourly auto-update (`scripts/update.sh`)
- валидация входных данных
- антигаллюцинации и бренд-контекст BLAGOVA_SWEETS
- SSRF protection
- автоматические тесты

## Назначение

Внутренний инструмент генерации контента для бренда **BLAGOVA_SWEETS**.
