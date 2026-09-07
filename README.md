# BLAGOVA_SWEETS Content Agent

AI-агент для генерации готовых постов социальных сетей бренда **BLAGOVA_SWEETS** на основе URL страницы или вручную переданного текста.

Проект закрывает учебное задание курса «Агент: Генерация постов для соцсетей» и расширяет его до практического инструмента: CLI, Web UI, FastAPI, история генераций, Telegram-бот и Docker.

## Задача проекта

1. Получить URL или текст.
2. Загрузить и очистить HTML (если URL).
3. Извлечь полезное содержание.
4. Передать контекст в LLM (OpenAI-compatible API).
5. Сформировать короткий пост в заданном стиле и для выбранной площадки.
6. Вернуть один готовый текст с контролем длины и антигаллюцинациями.

## Возможности

- CLI (`agent.py`) — обязательная часть учебного задания
- FastAPI + Swagger (`/docs`)
- Минимальный Web UI
- Telegram-бот (опционально, через `BOT_TOKEN`)
- Несколько площадок: `telegram`, `vk`, `instagram`, `universal`
- Стили: `ironic`, `friendly`, `selling`, `expert`, `warm`, `premium`, `short` + произвольная строка
- Цели поста: `product`, `sales`, `new_product`, `informational`, `promo`, `holiday`, `engagement`
- CTA и хэштеги (опционально)
- История генераций (SQLite)
- SSRF-защита при загрузке URL
- Docker / docker-compose

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
blagova_sweets_content_agent/
├── app/
│   ├── config.py
│   ├── models.py
│   ├── content_agent.py
│   ├── openai_client.py
│   ├── webpage_parser.py
│   ├── prompts.py
│   ├── history.py
│   ├── api/
│   │   └── routes.py
│   └── telegram/
│       └── bot.py
├── frontend/
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

Скопируйте пример и заполните значения:

```bash
copy .env.example .env   # Windows
cp .env.example .env     # Linux / macOS
```

Переменные:

| Переменная | Описание |
|---|---|
| `OPENAI_API_KEY` | ключ OpenAI / совместимого API |
| `BASE_URL` | базовый URL API, например `https://api.openai.com/v1` |
| `OPENAI_MODEL` | модель (по умолчанию `gpt-4o-mini`) |
| `BOT_TOKEN` | токен Telegram-бота (опционально) |
| `APP_HOST` | хост API (по умолчанию `0.0.0.0`) |
| `APP_PORT` | порт API (по умолчанию `8090`) |

Файл `.env` не должен попадать в Git.

## CLI

```bash
python agent.py --url https://example.com
python agent.py --url https://example.com --style ironic
python agent.py --url https://example.com --style friendly --platform telegram
python agent.py --text "Сегодня испекли новую партию круассанов" --style selling
python agent.py --text "..." --style warm --goal product --max-length 500 --cta
```

По умолчанию для CLI:

- `--style ironic`
- `--platform telegram`
- `--goal product`
- `--max-length 800`

`--url` и `--text` взаимоисключающие. На stdout печатается преимущественно готовый пост.

## API

Запуск:

```bash
python main.py
# или
uvicorn main:app --host 0.0.0.0 --port 8090
```

Проверка:

- UI: http://127.0.0.1:8090/
- Health: http://127.0.0.1:8090/health
- Swagger: http://127.0.0.1:8090/docs

Пример запроса:

```bash
curl -X POST http://127.0.0.1:8090/api/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Сегодня в BLAGOVA_SWEETS приготовили свежие булочки с корицей.\",\"platform\":\"telegram\",\"style\":\"warm\",\"goal\":\"product\",\"max_length\":500,\"cta\":true,\"hashtags\":false}"
```

Ответ:

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

История:

```bash
curl http://127.0.0.1:8090/api/history
```

## Web UI

Откройте http://127.0.0.1:8090/ после запуска API.

В интерфейсе:

- переключатель URL / Текст
- площадка, стиль, цель
- max length, CTA, hashtags
- готовый пост + копирование
- блок «Последние генерации»

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

Через Docker Compose профиль `bot`:

```bash
docker compose --profile bot up -d --build
```

## Docker

### Сборка и запуск API

```bash
docker compose up -d --build
```

Сервис слушает `0.0.0.0:${APP_PORT}` (по умолчанию `8090`).

### Обновление контейнера на VPS

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

### Production-заметки

- секреты только в `.env` на сервере, не в образе;
- наружу лучше проксировать через Nginx/Caddy на `8090`;
- не публикуйте контейнер сразу на `80/443` без reverse proxy;
- для бота используйте отдельный сервис/профиль `bot`.

## Тесты

```bash
pytest -q
```

Покрыто:

- валидация URL / SSRF
- очистка HTML
- ограничение `max_length`
- валидация входных данных
- пустой текст
- формирование prompt
- API smoke с mock OpenAI

Реальный OpenAI API в тестах не вызывается.

## Security

- `.env` в `.gitignore`
- ключи не логируются
- запрещены `file://` и не-HTTP(S) схемы
- блокируются `localhost`, `127.0.0.1`, `0.0.0.0`, `::1` и private IP
- перед запросом hostname резолвится через DNS; private/loopback IP отклоняются
- повторная проверка hostname после redirect
- лимит размера HTML-ответа
- в LLM уходит компактный текст, а не сырой HTML

## Примеры использования для BLAGOVA_SWEETS

```bash
python agent.py --text "Сегодня в BLAGOVA_SWEETS приготовили свежие булочки с корицей. Они доступны сегодня в ограниченном количестве." --style warm --platform telegram --goal product --max-length 500 --cta
```

Ожидаемо:

- пост в тёплом тоне авторской кондитерской;
- без выдуманных цен, адресов, состава и скидок;
- длина ≤ 500;
- естественный CTA без телефона/ссылок.

## Что реализовано сверх учебного задания

- Web UI
- FastAPI + Swagger
- Telegram-бот
- несколько платформ и стилей
- цели постов (`goal`)
- история генераций (SQLite)
- Docker / docker-compose
- валидация входных данных
- антигаллюцинации в prompt
- SSRF protection
- автоматические тесты
- брендовый контекст BLAGOVA_SWEETS

## Лицензия / назначение

Учебно-практический проект для вайб-кодинга с Cursor и рабочий внутренний инструмент контента бренда BLAGOVA_SWEETS.
