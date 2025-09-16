# Salem Explorer 4.5.0.1 — README

**Разработчик:** Бағдаулет Көптілеу  
**Организация:** © Salem Software Corporation  
**Дата релиза:** 16.09.2025  
**Движок UI/веб:** PyQt5 + Qt WebEngine (QWebEngine)

> Salem Explorer — кроссплатформенный браузер с кастомным лаунчером, локальными сервисами и модульной архитектурой. Этот README поможет быстро развернуть проект, собрать билд, подписать и упаковать дистрибутив.

---

## Содержание
- [Возможности](#возможности)
- [Стек и версии](#стек-и-версии)
- [Быстрый старт](#быстрый-старт)
- [Структура репозитория](#структура-репозитория)
- [Конфигурация](#конфигурация)
- [Локальные сервисы и API](#локальные-сервисы-и-api)
- [Сборка (PyInstaller)](#сборка-pyinstaller)
- [Подпись и инсталлятор](#подпись-и-инсталлятор)
- [Каталоги данных](#каталоги-данных)
- [Диагностика и логирование](#диагностика-и-логирование)
- [Совместимость и требования](#совместимость-и-требования)
- [Изменения 4.5.0.1 (Build 4501)](#изменения-4501)
- [Roadmap → 5.0](#roadmap--50)
- [Вклад и правила](#вклад-и-правила)
- [Безопасность](#безопасность)
- [Лицензия](#лицензия)
- [Полезные ссылки по Python и Qt](#полезные-ссылки-по-python-и-qt)
- [Контакты](#контакты)

---

## Возможности
- Лаунчер с самопроверкой окружения и безопасным запуском основного окна браузера.
- Основное окно на **PyQt5** с **QWebEngineView** (Chromium Embedded / QtWebEngine).
- Локальные мини‑сервисы (MediaHub и др.) для работы с медиа/кешем/загрузками.
- API уровня приложения (микромаршруты для настроек/логов/состояния).
- Режимы: стандартный, с логированием, dev‑режим с расширенной отладкой.

## Стек и версии
- **Язык:** Python 3.10 — 3.14 (рекомендуется 3.12/3.13)
- **GUI/Web:** PyQt5, Qt WebEngine (QWebEngine)
- **Сборка:** PyInstaller (onefile/onedir)
- **Инсталлятор (Windows):** Inno Setup (рекомендовано) / альтернативы NSIS/Wix
- **Линтеры/качество (опционально):** ruff/flake8, black
- **Тесты (опционально):** pytest
- **Виртуальное окружение:** `.venv` (опционально для форков)

## Быстрый старт

### 1) Клонирование
```bash
git clone https://github.com/bagdau/Salem-Explorer-4501-build.git
cd <repo>
```

### 2) Локальное окружение (опционально)
```bash
python -m venv .venv
# Windows
. .venv/Scripts/activate
# Linux/macOS
source .venv/bin/activate
```

### 3) Установка зависимостей
```bash
python -m pip install --upgrade pip wheel
pip install -r requirements.txt
```

### 4) Запуск в dev‑режиме
```bash
python src/launcher.py  # или python -m salem.launcher
```

> Если QtWebEngine не стартует: проверьте наличие `QtWebEngineProcess` и ресурсов Qt в окружении сборки/запуска, см. раздел «Сборка» и «Траблшутинг» ниже.

## Структура репозитория
```
<repo>/
│   enabled_extensions.json
│   file_version_info.txt
│   freeze.txt
│   history_data.json
│   launcher.py
│   qtwebengine_env.py
│   README.md
│   requirements.txt
│   Salem.py
├─ LICENSE
└─ README.md
│
├───extensions
│   │   enabled_extensions.json
│   │   salem_pip_mode.zip
│   │   video-booster.zip
│   │
│   ├───salem_pip_mode
│   │   │   manifest.json
│   │   │   README.md
│   │   │
│   │   ├───css
│   │   │       pip.css
│   │   │
│   │   ├───icons
│   │   │       pip.svg
│   │   │
│   │   └───js
│   │           pip.js
│   │
│   └───video-booster
│       │   manifest.json
│       │   popup.html
│       │   README.md
│       │
│       ├───assets
│       │       video-booster.png
│       │
│       ├───css
│       │       popup.css
│       │
│       └───js
│               background.js
│               content.js
│               popup.js
│               service-worker.js
│
├───img
│   │   600px-Logo_of_Kaspi_bank.png
│   │   dominik-schroder-FIKD9t5_5zQ-unsplash.jpg
│   │   Egov.png
│   │   GreenField.jpg
│   │   GreenField.jpg.jpg
│   │   icon2.ico
│   │   icons8-chatgpt-192.png
│   │   icons8-discord-100.png
│   │   icons8-facebook-144.png
│   │   icons8-google-96.png
│   │   icons8-instagram-144.png
│   │   icons8-tiktok-240.png
│   │   icons8-user-icon-96 (1).png
│   │   icons8-user-icon-96.png
│   │   icons8-web-design-96.png
│   │   icons8-youtube-500.png
│   │   MinPhoto.png
│   │
│   └───icons
│           app-window.svg
│           arrow-badge-left.svg
│           arrow-badge-right.svg
│           arrow-bar-to-left.svg
│           arrow-big-left.svg
│           arrow-big-right-line.svg
│           assembly.svg
│           badge.svg
│           book.svg
│           bookmark.svg
│           box-multiple.svg
│           box.svg
│           brand-google.svg
│           brand-wikipedia.svg
│           brand-youtube.svg
│           brightness (1).svg
│           brightness.svg
│           calculator.svg
│           camera.svg
│           capture.svg
│           chevron-left.svg
│           chevron-right.svg
│           circle-arrow-left.svg
│           circle-arrow-right.svg
│           DES.ico
│           download.svg
│           file-description.svg
│           folder.svg
│           history.svg
│           home.svg
│           icon.ico
│           icon2.jpg
│           image.png
│           loader.gif
│           menu.svg
│           new-tab.svg
│           pip.svg
│           plus.svg
│           preloader.gif
│           puzzle.svg
│           refresh.svg
│           SalemLogo235.ico
│           user.svg
│
├───js
│       background.js
│       handleControl.js
│       news-block.js
│       notificaton.js
│       ScreenAutomator.js
│       script.js
│       UserAccount.js
│       weatherActual.js
│       weatherNotify.js
│
├───launcher_plugins
│   │   loader.py
│   │
│   ├───preload_core
│   │   │   manifest.json
│   │   │   plugin.py
│   │   │
│   │   └───__pycache__
│   │           plugin.cpython-310.pyc
│   │
│   └───preload_media
│       │   manifest.json
│       │   plugin.py
│       │
│       └───__pycache__
│               plugin.cpython-310.pyc
│
├───MediaHub
│   │   mediahub_server.py
│   │   requirements.txt
│   │   SalemMedia.html
│   │
│   ├───IconsStartPage
│   │       bookmarks.png
│   │       calendar.png
│   │       gmail.png
│   │       music.png
│   │       news.png
│   │       settings.png
│   │       uploads.png
│   │       weather.png
│   │       youtube.png
│   │
│   ├───media
│   └───static
│       ├───css
│       │       mediahub.css
│       │
│       └───js
│               mediahub_client.js
│
├───mods
│       load_order.json
│
├───modules
│   │   AccountBridge.py
│   │   bookmarks.py
│   │   bookmarks_ui.py
│   │   downloads_ui.py
│   │   extensions_loader.py
│   │   extensions_popup.py
│   │   extensions_ui.py
│   │   history_ui.py
│   │   mods_loader.py
│   │   mods_ui.py
│   │   Optimizer.py
│   │   pip_mode.py
│   │   pip_native.py
│   │   salem_sidebar.py
│   │   toggle_downloads_panel.py
│   │   user_accounts_ui.py
│   │   user_account_ui.py
│   │   __init__.py
│   │
│   └───icons
│           addons.png
│           bookmarks.png
│           broom.png
│           colors.png
│           download.png
│           fonts.png
│           history.png
│           history.svg
│           home.png
│           layers-subtrack.png
│           layers-subtract.svg
│           lock.png
│           lock.svg
│           mediaplayer.svg
│           menu.svg
│           modes.svg
│           moon.png
│           offline.svg
│           online.svg
│           player.svg
│           power.png
│           power.svg
│           print.svg
│           profile.png
│           restart.png
│           save.png
│           save.svg
│           settings.png
│           settings.svg
│           spy.svg
│           sun.png
│           Trash.png
│           volume-off.png
│           volume-on.svg
│           x.svg
│           zoom.svg
│           zoom1.svg
│
├───news_proxy
│   │   404Error.html
│   │   500Error.html
│   │   503Error.html
│   │   account.db
│   │   account_api.py
│   │   clock.html
│   │   index.html
│   │   Mail_server.py
│   │   newsapi.key
│   │   NEWSAPI_KEY.txt
│   │   news_section.html
│   │   server.py
│   │   wallpapers.html
│   │   __init__.py
│   │
│   ├───IconsStartPage
│   │       bookmarks.png
│   │       calendar.png
│   │       gmail.png
│   │       music.png
│   │       news.png
│   │       settings.png
│   │       uploads.png
│   │       weather.png
│   │       youtube.png
│   │
│   ├───img
│   │       default.jpg
│   │       icon2.jpg
│   │       icons8-user-icon-96 (1).png
│   │       Okak.jpg
│   │
│   └───static
│       │   Account.html
│       │   account.js
│       │   account_ui.css
│       │   autoplay_iframe_plugin.js
│       │   ChangeWallpaper.css
│       │   ChangeWallpaper.js
│       │   clock.js
│       │   main.css
│       │   main.js
│       │   modalWindow.js
│       │   script.js
│       │   searchSystem.js
│       │   styles.css
│       │
│       ├───api
│       │   │   htaccess
│       │   │   login.php
│       │   │   logout.php
│       │   │   profile.php
│       │   │   register.php
│       │   │   update_profile.php
│       │   │   upload_avatar.php
│       │   │   _bootstrap.php
│       │   │
│       │   └───htaccess.tmp.news_proxy
│       │       └───static
│       │           └───api
│       ├───avatars
│       ├───img
│       │       Salem.png
│       │
│       ├───uploads
│       └───wallpapers
├───rthooks
│   │   hook-urllib3.py
│   │   hook_salem_env.py
│   │
│   └───__pycache__
│           hook-urllib3.cpython-310.pyc
│
├───tools
│       build_manifest.py
│
└───utils
        asset_path.py
```

## Конфигурация
Переменные окружения и конфигурационные файлы читаются при старте лаунчера.

**Основные ключи:**
- `SALEM_PROFILE` — имя пользовательского профиля (папка данных)
- `SALEM_DEV` — включает dev‑режим (расширенные логи, отключение минификаций)
- `SALEM_MEDIA_PORT` — порт локального MediaHub
- `SALEM_DATA_DIR` — принудительный путь к каталогу данных

Файл настроек по умолчанию: `config/salem.config.json` (переопределяется переменными окружения).

## Локальные сервисы и API
**MediaHub** — легковесный локальный сервис для работы с медиа/кешем/загрузками.  
**API‑маршруты (пример):**
```
GET  /api/ping
GET  /api/version
GET  /api/settings
POST /api/logs/collect
```

Схемы и договоренности по ответам описаны в `src/salem/api/schema.py`.

## Сборка (PyInstaller)

### Минимальная сборка (onedir)
```bash
pip install pyinstaller
pyinstaller -y \
  --name "salem-explorer" \
  --icon assets/icons/icon2.ico \
  --add-data "assets;assets" \
  --hidden-import "PyQt5.sip" \
  --hidden-import "PyQt5.QtWebEngineWidgets" \
  build/salem.spec
```

**Важно:**
- Убедитесь, что в сборку попали каталоги `QtWebEngine`/`resources` (PyInstaller обычно подтягивает их автоматически для PyQt5, но проверьте в папке `dist/`).
- Не создавайте вручную `_internal` — PyInstaller сам управляет внутренней структурой.

### Onefile + ресурсы Qt
Onefile требует аккуратного включения ресурсов QtWebEngine. Практичный путь — оставить `onedir` для стабильности браузера. Если нужен `onefile`, убедитесь, что при распаковке присутствуют:
```
PyQt5/Qt/resources/
PyQt5/Qt/plugins/
PyQt5/Qt/translations/
QtWebEngineProcess(.exe)
```

### Траблшутинг QtWebEngine
- Ошибка вида `QtWebEngineProcess.exe not found` → проверьте, что бинарь и ресурсы Qt лежат рядом с исполняемым файлом или корректно запакованы в `dist/`.
- На Windows путь обычно `dist/salem-explorer/QtWebEngineProcess.exe`.
- На Linux убедитесь в наличии библиотек `libnss`, `libxcb`, `libdrm`, и совместимой версии драйверов.

## Подпись и инсталлятор

### Подпись (Windows)
- Используйте сертификат для `Salem Software Corporation`.
- Пример с signtool:
```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com \
  /td SHA256 /a dist/salem-explorer/salem-explorer.exe
```

### Inno Setup (рекомендовано)
- Храните скрипт в `installers/SalemSetup.iss`.
- Минимальные поля: `AppId`, `AppName`, `AppVersion`, `Publisher`, `DefaultDirName={autopf}\Salem-Explorer`.
- Добавьте ярлык, ассоциации (опционально), проверку наличия VC++/WebView2 не требуются для QtWebEngine.

## Каталоги данных
- **Windows:** `%APPDATA%/Salem-Explorer/` (профили, кеш, настройки)
- **Linux:** `~/.local/share/salem-explorer/` и `~/.config/salem-explorer/`
- **Portable‑режим (опционально):** рядом с бинарем в `./profile/`

## Диагностика и логирование
- Логи приложения: `logs/app.log`
- Сбор диагностической информации можно инициировать API: `POST /api/logs/collect`
- Типичные проблемы: нехватка GPU‑ресурсов, конфликт плагинов, устаревшие драйверы, блокировка антивирусом.

## Совместимость и требования
- **ОС:** Windows 10/11, Linux (современные дистрибутивы с поддержкой QtWebEngine)
- **CPU:** x86_64 (рекомендуется)
- **RAM:** минимум 4 ГБ (рекомендуется 8 ГБ+)
- **Python:** 3.10 — 3.14 (dev окружение)

## Изменения 4.5.0.1 (Build 4501)
- Улучшен лаунчер: самопроверка окружения, стабильный старт браузера.
- Обновлены маршруты MediaHub, оптимизирована работа с кешем.
- Рефакторинг DevTools‑панелей, улучшено логирование.
- Подготовка к миграции ядра под 5.0 (модульность, изоляция сервисов).

## Roadmap → 5.0
- Переупаковка ядра, облегчение старта и уменьшение «холодной» загрузки.
- Расширяемая система плагинов/модулей.
- Альтернативные каналы обновлений и дифф‑патчи.

## Вклад и правила
1. Форкните репозиторий и создайте ветку `feature/<topic>`.
2. Соблюдайте стиль кода (black/ruff), запускайте тесты.
3. PR сопровождайте кратким описанием, скриншотом/логами при необходимости.

## Безопасность
Уязвимости и вопросы безопасности: отправляйте на security@officialcorporationsalem.kz (PGP приветствуется). Не создавайте публичных issue для zero‑day.

## Лицензия
© Salem Software Corporation. Конкретные условия указаны в файле `LICENSE` этого репозитория.

## Полезные ссылки по Python и Qt
- Python (официально): https://www.python.org/
- Документация Python: https://docs.python.org/
- PyPI: https://pypi.org/
- Виртуальные окружения (venv): https://docs.python.org/3/library/venv.html
- pip: https://pip.pypa.io/
- PyQt5: https://pypi.org/project/PyQt5/
- Документация Qt: https://doc.qt.io/
- Qt WebEngine (QWebEngine): https://doc.qt.io/qt-6/qtwebengine-index.html
- PyInstaller: https://pyinstaller.org/
- Inno Setup: https://jrsoftware.org/isinfo.php

## Контакты
- Сайт: https://officialcorporationsalem.kz/
- Автор: Бағдаулет Көптілеу
- Организация: Salem Software Corporation

