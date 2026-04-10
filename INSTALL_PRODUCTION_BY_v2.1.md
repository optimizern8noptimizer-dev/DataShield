# DataShield BY 2.1 Enterprise - установка и использование

## 1. Что это
DataShield BY 2.1 Enterprise - доработанная версия исходного продукта для обезличивания банковских БД с Web-управлением, логином, ролями, control-plane БД и production-развёртыванием через Docker Compose.

## 2. Что исправлено относительно исходника
- FastAPI control plane вместо небезопасного старого Web-слоя
- login/logout и RBAC: viewer / operator / admin
- Postgres-backed control-plane для пользователей, токенов, jobs и audit events
- Docker Compose для production/pilot запуска
- OpenAPI docs по пути `/docs`
- bootstrap admin через переменные окружения
- аудит действий входа, запуска job, маскирования preview и управления пользователями

## 3. Быстрый запуск через Docker Compose
Путь:
- распаковать архив
- открыть каталог `datashield`
- создать `.env` рядом с `docker-compose.yml`

Содержимое `.env`:
```env
DS_BOOTSTRAP_ADMIN=admin
DS_BOOTSTRAP_PASSWORD=__REPLACE_ME_STRONG_PASSWORD__
DATASHIELD_AUDIT_KEY=__REPLACE_ME_MIN_32_CHARS__
```

Команда запуска:
```bash
docker compose up -d --build
```

Проверка:
- Web UI: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8080/docs`
- Health: `http://127.0.0.1:8080/api/health`

## 4. Логин
Путь в UI:
- открыть `http://127.0.0.1:8080`
- блок `1. Вход`
- поле `Username` -> `admin`
- поле `Password` -> значение из `.env` поля `DS_BOOTSTRAP_PASSWORD`
- кнопка `Login`

## 5. Роли
- `viewer` -> просмотр профиля и списка jobs
- `operator` -> preview masking + запуск jobs
- `admin` -> все права + users + audit + cache

## 6. Создание пользователя
Путь в UI:
- `5. Users (admin)`
- поле `new username`
- поле `new password`
- список `role`
- кнопка `Create user`

## 7. Запуск job
Путь в UI:
- `4. Run job`
- поле `Config path` -> `config/example_config.yaml`
- список `jobMode` -> `dry_run` или оставить `(config default)`
- поле `tables` -> например `customers,accounts`
- кнопка `Run`

CLI внутри контейнера:
```bash
docker compose exec app datashield run --config config/example_config.yaml --mode dry_run
```

## 8. Локальный запуск без Docker
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
export DS_CONTROL_DB_URL=sqlite:///./datashield_control.db
export DS_BOOTSTRAP_ADMIN=admin
export DS_BOOTSTRAP_PASSWORD=admin12345
export DATASHIELD_AUDIT_KEY=__REPLACE_ME_MIN_32_CHARS__
uvicorn datashield.api.app:app --host 0.0.0.0 --port 8080
```

## 9. Ошибки / причина / фикс
### 401 Invalid or expired token
Причина: не выполнен login или токен устарел.
Фикс: повторить login.

### 403 Role operator or higher required
Причина: пользователь viewer пытается запускать preview/job.
Фикс: создать пользователя с ролью operator или admin.

### 404 Config not found
Причина: неверный путь в поле `Config path`.
Фикс: указывать путь относительно каталога приложения, например `config/example_config.yaml`.

### Postgres connection failed
Причина: контейнер postgres не поднялся или неверный DS_CONTROL_DB_URL.
Фикс: `docker compose ps`, затем `docker compose logs postgres`.
