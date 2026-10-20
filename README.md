# Snippet Stack

Личное веб-приложение для хранения фрагментов кода и команд терминала. Python 3.12, Django 5.2 LTS, SQLite, Gunicorn и WhiteNoise. Frontend — серверные HTML-шаблоны, CSS и небольшой vanilla JavaScript, без npm, CDN и внешних шрифтов.

## Возможности

- Регистрация, вход, выход; приватная библиотека для каждого пользователя.
- Создание, редактирование, удаление с подтверждением, избранное и копирование полного кода.
- Теги через запятую, поиск по названию, описанию, коду и тегам, фильтрация по языку, сортировка и пагинация.
- Отдельный раздел терминальных команд; код никогда не исполняется сервером.
- Адаптивная сетка и мобильная навигация, светлая и тёмная темы с сохранением выбора.
- Редактор: Tab для отступа, Ctrl/⌘ + Enter для сохранения, предупреждение о несохранённых изменениях; `/` фокусирует поиск.
- PWA manifest, PNG-иконки и service worker. Установка поддерживается совместимыми браузерами на HTTPS или localhost. Офлайн доступна страница отсутствия соединения, личные данные не кэшируются и редактирование без сети не поддерживается.

## Быстрый запуск Docker

Нужен работающий Docker Engine / Docker Desktop с Compose v2.

```sh
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Вставьте сгенерированное значение в `SECRET_KEY` файла `.env`, затем:

```sh
docker compose up --build -d
```

Откройте http://localhost:8000 и создайте аккаунт. Миграции выполняются при старте. Данные хранятся в именованном volume `snippet_data` и сохраняются при обновлении контейнера.

```sh
docker compose logs -f web
docker compose down
```

`docker compose down -v` удалит базу вместе с volume — не используйте эту команду для обычного обновления.

## Локальная разработка

Python 3.11+:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DEBUG=true
python manage.py migrate
python manage.py runserver
```

Прямой запуск Django не читает `.env` автоматически: используйте переменные окружения. SQLite находится в `data/db.sqlite3`. Секреты, база, виртуальное окружение и собранная статика исключены из Git и Docker build context. В репозитории нет встроенных аккаунтов и паролей.

## Проверка

```sh
SECRET_KEY=test-only python manage.py collectstatic --noinput
SECRET_KEY=test-only python manage.py test
SECRET_KEY=test-only python manage.py check
```

15 интеграционных тестов проверяют регистрацию, авторизацию, операции со сниппетами, теги, поиск, пагинацию, приватность между аккаунтами, CSRF, XSS-экранирование, POST-only мутации, заголовки, service worker и ограничение попыток входа.

## Развёртывание на сервере

Порт по умолчанию опубликован только на `127.0.0.1`. Поставьте перед ним HTTPS reverse proxy (Caddy / Nginx), добавьте домен в `ALLOWED_HOSTS` и полный origin в `CSRF_TRUSTED_ORIGINS`. Сохраните `127.0.0.1` в `ALLOWED_HOSTS` для healthcheck.

```dotenv
ALLOWED_HOSTS=snippets.example.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://snippets.example.com
HTTPS=true
TRUST_PROXY=true
```

Включайте `TRUST_PROXY` только когда доверенный reverse proxy **перезаписывает**, а не просто передаёт клиентский `X-Forwarded-Proto`, и прямой доступ к backend закрыт. Для Nginx: `proxy_set_header Host $host;` и `proxy_set_header X-Forwarded-Proto $scheme;`. Ограничьте размер тела запроса до 256 KiB, частоту регистрации и входа на proxy. Настройте реальный адрес клиента для django-axes, если используете proxy; по умолчанию ограничение применяется к IP прямого соединения, поэтому клиенты за одним proxy могут разделять блокировку.

При `HTTPS=true` включаются secure cookies, HTTPS redirect и HSTS. Исключение `/health/` возвращает только состояние доступности БД. Проверка настроек production:

```sh
docker compose exec web python manage.py check --deploy
```

Защита приложения: Django ORM, стандартное хеширование и валидация паролей, CSRF, автоматическое экранирование, проверка владельца каждой записи, строгий CSP, HttpOnly session cookie, запрет встраивания во frame, отсутствие исполнения сниппетов. После 5 неудачных попыток входа IP блокируется на 15 минут (состояние в БД, общее для workers). Регистрация открытая. Восстановление пароля по email и MFA не входят в текущую реализацию.

Контейнер работает без root и Linux capabilities. `DEBUG` в Compose выключен. Зависимости зафиксированы в `requirements.txt`; регулярно обновляйте security-патчи. SQLite подходит для личной библиотеки и небольших команд; записи сериализуются, поэтому для высокой конкурентной нагрузки потребуется переход на PostgreSQL и повторная проверка запросов/миграций.

## Резервная копия SQLite

Создавайте согласованную копию через SQLite backup API:

```sh
docker compose exec web python -c "import sqlite3; source=sqlite3.connect('/app/data/db.sqlite3'); target=sqlite3.connect('/app/data/backup.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose cp web:/app/data/backup.sqlite3 ./backup.sqlite3
```

Копия содержит приватный код и хеши паролей: храните её вне публичного доступа. Для восстановления остановите приложение, замените `db.sqlite3` в volume копией, сохранив права пользователя контейнера, затем запустите сервис. Перед обновлением делайте backup.

## Структура

- `config/` — настройки, маршруты, WSGI.
- `snippets/` — модели, формы, views, миграции, тесты.
- `templates/` — страницы библиотеки, редактора, регистрации и входа.
- `static/` — стили, JS, иконки и PWA.
- `Dockerfile`, `compose.yaml` — запуск с постоянным томом SQLite.

Рекомендации Django: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
