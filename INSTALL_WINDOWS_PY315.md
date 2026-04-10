# DataShield BY 2.2.2 — Windows / Python 3.15.0a6 Hotfix

## Краткий вывод
Это hotfix-пакет под **Windows + Python 3.15.0a6** с упором на **локальный SQLite-only режим по умолчанию** и быстрый запуск через готовые `.cmd` / `.ps1` скрипты.

Изменения в hotfix:
- Web запускается через **waitress**, а не через Flask dev server.
- По умолчанию используется **SQLite control-plane**: `datashield_control.db`.
- Добавлены Windows-скрипты:
  - `scripts\bootstrap_windows_py315.ps1`
  - `scripts\start_web.cmd`
  - `scripts\start_worker.cmd`
  - `scripts\start_all_windows.cmd`
- Добавлен шаблон переменных: `.env.windows.example`

---

## Основной путь

### 1. Распаковать архив
Путь:
- распаковать архив в каталог, например: `D:\datashield`

### 2. Открыть PowerShell
Путь:
- `Windows -> PowerShell`

### 3. Перейти в каталог проекта
```powershell
cd D:\datashield
```

### 4. Выполнить bootstrap-скрипт
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_py315.ps1
```

Что сделает скрипт:
- создаст `.venv`
- обновит `pip/setuptools/wheel`
- выполнит `pip install -e .`
- создаст файл `.env.local`

### 5. Открыть продукт
Путь:
- в том же каталоге выполнить:
```powershell
.\scripts\start_all_windows.cmd
```

Что произойдёт:
- откроется отдельное окно **worker**
- в текущем окне запустится **web**

### 6. Открыть UI
- `http://127.0.0.1:8080`
- docs: `http://127.0.0.1:8080/docs`

---

## Что заменить
Файл:
- `D:\datashield\.env.local`

Поля:
- `DATASHIELD_AUDIT_KEY=__REPLACE_ME_MIN_32_CHARS__`
- `DS_BOOTSTRAP_PASSWORD=__REPLACE_ME_ADMIN_PASSWORD__`

---

## Запасной путь — ручной запуск

### Web
```powershell
cd D:\datashield
.\.venv\Scripts\Activate.ps1
Get-Content .\.env.local | ForEach-Object {
  if ($_ -and $_ -notmatch '^\s*#') {
    $name,$value = $_ -split '=',2
    Set-Item -Path Env:$name -Value $value
  }
}
datashield-web
```

### Worker
Во втором окне PowerShell:
```powershell
cd D:\datashield
.\.venv\Scripts\Activate.ps1
Get-Content .\.env.local | ForEach-Object {
  if ($_ -and $_ -notmatch '^\s*#') {
    $name,$value = $_ -split '=',2
    Set-Item -Path Env:$name -Value $value
  }
}
datashield-worker
```

---

## Ошибки / симптом / причина / фикс

### Симптом
`[ERROR] .venv not found`

### Причина
Не выполнялся bootstrap.

### Фикс
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_py315.ps1
```

### Симптом
`Address already in use`

### Причина
Порт `8080` уже занят.

### Фикс
Файл:
- `D:\datashield\.env.local`

Изменить:
```text
DS_WEB_PORT=8081
```

Потом перезапустить `start_all_windows.cmd`.

### Симптом
`Jobs stay queued`

### Причина
Worker не запущен.

### Фикс
Открыть:
```powershell
.\scripts\start_worker.cmd
```

### Симптом
`401 Invalid or expired token`

### Причина
Не выполнен login или токен истёк.

### Фикс
Перелогиниться через UI.

---

## Проверка результата

```powershell
curl http://127.0.0.1:8080/api/health
```

Ожидаемо:
- `status = ok`
- `framework = flask`
- `python_315_profile = true`
- `worker_mode = external-queue-worker`


## Windows Python 3.15 note

This package pins SQLAlchemy to the 2.1 series to avoid pulling `greenlet` by default. If you previously attempted installation with an older environment, delete `.venv` and recreate it before running bootstrap again.
