# 📦 RUNTIMEFORCE — ЕДИНЫЙ КОНТЕКСТ ПРОЕКТА (MASTER FILE)

## 1. ОБЩАЯ ИДЕЯ ПРОДУКТА

RuntimeForce — это специализированная среда разработки и платформа оркестрации (AI Runtime Environment) для локальной и SSH-разработки.


Продукт представляет собой легкий гибрид:
* локального рантайма (Self-Hosted);
* управляющего SaaS-слоя (Control Plane).

RuntimeForce — это не веб-редактор и не клон Cursor.
Это распределенная платформа оркестрации кода, AI-моделей, терминала и VPS-инфраструктуры.

---

## 2. ЯЗЫКОВЫЕ ПРАВИЛА

### Язык проекта

Весь генерируемый код, конфиги, комментарии, логи, интерфейсы, API-схемы, названия файлов, переменные, функции и классы должны быть строго на английском языке.

### Язык общения

Все ответы в чате, пояснения, заголовки, обсуждения и документы — строго на русском языке.

---

## 3. ОБЯЗАТЕЛЬНЫЕ ПРИНЦИПЫ РАЗРАБОТКИ

Эти правила являются критическими. Их нарушение недопустимо.

### 3.1. Loose Coupling Architecture

Разработка RuntimeForce ведется строго по принципу слабосвязанной модульной архитектуры:

```text
Loose Coupling Architecture
```

Это означает:

* модули не знают о внутренней реализации других модулей;
* модули общаются через интерфейсы, сервисы и события;
* запрещена жесткая привязка к конкретным реализациям;
* запрещены прямые импорты UI-компонентов друг в друга;
* запрещены глобальные синглтоны, создаваемые на уровне модулей;
* запрещены god-файлы, которые делают SSH, Git, AI, файлы и UI одновременно;
* любая новая функция должна проектироваться как изолированный модуль.

### 3.2. Dependency Injection

Все сервисы, репозитории, драйверы и менеджеры должны внедряться через DI-контейнер (`container.py`).

Запрещено:

```python
service = SomeService()
repository = SomeRepository()
store = RuntimeStore()
```

в глобальной области модуля.

Разрешено только:

```python
container.register(IWorkspaceDriver, WorkspaceLocalDriver)
container.register(IStorageRepository, StorageDbRepository)
```

и внедрение через FastAPI:

```python
Depends(get_workspace_service)
```

### 3.3. Event-Driven Frontend & Backend

Фронтенд и бэкенд общаются только через событийную шину (`EventBus`).

Запрещено:

```js
window.someGlobalState = ...
import AnotherComponent from ...
```

для прямой связи компонентов.

Разрешено:

```js
EventBus.publish("workspace.changed", payload);
EventBus.subscribe("workspace.changed", handler);
```

Сервисы backend не должны вызывать друг друга напрямую там, где это создает связность.
Для межмодульных уведомлений используется Python event bus.

Примеры событий:

```text
workspace.changed
session.created
message.completed
terminal.closed
license.updated
credits.changed
byok.key.updated
support.ticket.created
audit.event.added
project.created
project.version_bumped
social.post_drafted
```

### 3.4. Interface-Driven Design

Оркестратор, агент, сервисы и UI не работают с конкретными реализациями напрямую.

Используются абстрактные интерфейсы (`app/core/interfaces/`):

```text
IWorkspaceDriver
IStorageRepository
ILLMProvider
IToolExecutor
IAuditLogger
ILicenseService
ICreditBalanceService
ISupportTicketService
IByokKeyService
IProjectService
IVersioningService
ISocialModuleService
```

Это гарантирует возможность замены:

```text
LocalDriver → SSHDriver
SQLiteRepository → PostgresRepository
OpenAIProvider → AnthropicProvider
LocalAuditLogger → ServerAuditRelay
```

без переписывания бизнес-логики.

### 3.5. Single Responsibility

Одному файлу — ровно одна задача.
Если модуль управляет одновременно SSH, локальным диском, Git, AI, UI, billing, support, audit или project rules, он должен быть немедленно разделен.

### 3.6. Запрет игнорирования архитектурных правил

Ни при каких обстоятельствах нельзя игнорировать принцип Loose Coupling Architecture.
Даже если нужно сделать быстро:

```text
сначала правильно архитектурно,
потом быстро,
потом красиво.
```

Нарушение связности должно быть устранено до merge.

---

## 4. ТЕКУЩИЙ ЭТАП ПРОДУКТА

На текущем этапе RuntimeForce реализует только три тарифа:

```text
Free
Pro
Studio
```

Enterprise не реализуется на текущем этапе. Enterprise полностью вынесен в roadmap.

---

## 5. АРХИТЕКТУРНОЕ РАЗДЕЛЕНИЕ СИСТЕМЫ

Система жестко разделена на два изолированных слоя.
Они взаимодействуют по единому унифицированному протоколу чата:

```text
SSE JSON
```

Любое дублирование кода исключено за счет выноса общей бизнес-логики в shared core layer.

---

## 6. runtimeforce-app (IDE Client)

Локальный легковесный монолит на базе FastAPI.
Разворачивается на локальной машине разработчика или на приватном dev-VPS пользователя.

### Интерфейс

```text
Monaco Editor
xterm.js terminal
distributed file tree
Git visualizer
AI chat
Project Settings UI (Project Context, Rules, SSH, Git, Versioning)
Social Build in Public Dashboard (Approval & Feedback)
```

### Управление рантаймами

Асинхронное взаимодействие с:

* локальной ОС через `asyncio.subprocess`;
* удаленными серверами через SSH async pool.

### Хранение данных

Полностью контролирует приватные данные:

* SSH keys;
* Git tokens;
* local paths;
* project structure cache;
* conversation history;
* local audit log;
* BYOK API keys (AES-256-GCM encrypted);
* project configurations & local user rules;
* local telemetry.

Основная локальная БД:

```text
SQLite
```

Путь:

```text
~/.local/share/runtimeforce/runtime.db
```

Windows:

```text
%LOCALAPPDATA%\RuntimeForce\runtime.db
```

Требования:

* strict permissions 0600/0700;
* WAL mode;
* foreign keys enabled;
* user_id isolation (защита от перехвата данных при логине разных пользователей на одном ПК);
* migrations support;
* thread-safe access;
* no relative paths.

---

## 7. runtimeforce-server (SaaS Core)

Центральный координирующий backend:

```text
https://runtimeforce.dev
```

Полностью изолирован от исходного кода пользователя.

### Зона ответственности

```text
authentication;
OAuth GitHub/Google;
RS256 JWT issuing (с Master Derivation Token для локального дешифрования);
subscription validation;
Paddle billing;
credit ledger;
usage limits;
AI proxy for managed plans;
license validation & signature issuing;
support ticket intake;
basic billing audit;
usage dashboard;
support bot;
admin panel.
```

### Чего сервер не делает на текущем этапе

* не хранит SSH keys;
* не хранит Git tokens;
* не хранит BYOK API keys;
* не хранит prompts;
* не хранит source code;
* не хранит full AI responses;
* не хранит full local audit logs;
* не имеет доступа к файловой системе пользователя.

---

## 8. ЦЕЛЕВАЯ АРХИТЕКТУРА ПОТОКОВ ДАННЫХ

```text
[ Browser UI / IDE Frontend ]
        │
        │ Unified SSE JSON: chat, terminal PTY, control, project events
        ▼
[ runtimeforce-app (Local FastAPI Runtime) ]
        │
        ├───────────────────────────────┐
        ▼                               ▼
 Local FS / SSH VPS / Ollama     runtimeforce-server (SaaS Core)
 Direct BYOK (Free & Studio)            │
                      ─────────────────────────────────────
                      │            │             │         │
                   Auth         Billing       AI Proxy   Admin
                JWT RS256        Paddle      Pro routing  Panel
```

---

## 9. КРИТИЧЕСКИЕ ПРАВИЛА БЕЗОПАСНОСТИ И ДАННЫХ (DATA SOVEREIGNTY)

### 9.1. Client NOT Trusted

Клиент не является доверенной стороной.
Вся логика проверки тарифа, подписки, лимита credits, rate limits, top-up баланса, license status и trial status выполняется строго на стороне `runtimeforce-server`.
Локальный клиент кэширует статус подписки для offline grace, но не может самостоятельно принимать окончательное биллинговое решение.

### 9.2. Разделение конфиденциальности

#### Строго локально:

SSH passwords, SSH private keys, Git PAT tokens, BYOK API keys (AES-256-GCM шифрование), local file paths, project file structure, conversation context, AI prompts, AI responses, terminal output, full local audit logs, Project Configurations & Rules, история трассировки (`session_traces`) и вызовов инструментов (`session_tools`) в SQLite (`runtime.db`).

#### Строго на сервере:

JWT sessions, subscription status, Paddle customer IDs, credit ledger, usage counters, billing events, license status, support ticket metadata, basic billing audit, blog, adminpanel.

### 9.3. Terminal Process Safety

Все PTY и SSH-сессии работают строго через async queue.
Backend обязан отслеживать активные процессы, чистить ресурсы при разрыве WebSocket, завершать orphan-процессы и ограничивать параллельные сессии.

### 9.4. Stateless Backend

Backend-компоненты проектируются как stateless.
Состояние рабочей сессии хранится в контексте фронтенда и в локальной SQLite как отказоустойчивый кэш. Сервер хранит только биллинговые, лицензионные и usage-данные.

### 9.5. Каскадное Удаление

При удалении чата или проекта все относящиеся к ним метаданные, сообщения, трассировки (`session_traces`) и лог инструментов (`session_tools`) автоматически удаляются из базы данных SQLite.

---

## 10. БИЛЛИНГ И НАЛОГИ

### 10.1. Провайдер биллинга

Используется **Paddle billing** (Paddle как Merchant of Record). Paddle администрирует эквайринг, подписки, VAT/Sales Tax, комплаенс, чарджбэки и инвойсы.

### 10.2. Юридическое лицо

ИП в Грузии (малый бизнес, 1% от валового оборота до вычета комиссии Paddle). Конвертация в GEL выполняется по курсу Нацбанка Грузии на день выплаты.

### 10.3. Комиссии и экономика

* Базовая комиссия Paddle: 5% + $0.50 за транзакцию.
* Целевая чистая маржа: 30–40%.

---

## 11. ТАРИФНАЯ СЕТКА И БИЗНЕС-МОДЕЛЬ

### 11.1. Free ($0)

* **Billing:** Локальная и серверная запись в БД.
* **AI Managed:** Нет.
* **BYOK (Free & Local):** **Да**. Открыт доступ к личным ключам для бесплатных провайдеров (Gemini Free, Groq, SambaNova, Cerebras, OpenRouter Free) и локальных движков (Ollama, LM Studio). BYOK не тратит серверные токены. Внедрить реферальные ссылки в кнопки для регистрации у этих провайдеров.
* **BYOK (Pro):** Нет.
* **Лимиты Проектов:** Максимум 1 активный проект.
* **Ограничения:** 1 SSH host, 1 параллельный AI-запрос. Без Consilium, нет фоновых агентов, нет top-ups.

### 11.2. Pro ($19/месяц, $190/год)

* **Billing:** Paddle subscription.
* **AI Managed (Managed Proxy):** 5,000 AI Credits/месяц для работы с Pro-моделями (OpenAI, Anthropic, DeepSeek, xAI) "из коробки" без необходимости регистрировать ключи.
* **BYOK (Free & Local):** Да.
* **BYOK (Pro):** Нет.
* **Защита BYOK & Лицензирование:** Локальная дешифрация ключей завязана на серверную подпись JWT. Критические модули скопилированы через Cython. **Offline Grace Period:** 48 часов.
* **Оркестрация:** Разблокируется режим Consilium (тратит серверные кредиты).
* **Лимиты Проектов:** Максимум 3 активных проекта, 3 SSH-хоста, 3 фоновых процесса, доступ к top-ups (макс 2/мес).

### 11.3. Studio ($49/месяц, $490/год)

* **Billing:** Paddle subscription.
* **AI Managed:** 15,000 AI Credits/месяц для работы с Pro-моделями (OpenAI, Anthropic, DeepSeek, xAI) "из коробки" без необходимости регистрировать ключи.
* **BYOK (Full Pro BYOK):** **Да**. Полный доступ к подключению собственных API-ключей к Pro-провайдерам (OpenAI, Anthropic, Perplexity, DeepSeek, xAI). Прямой вызов с клиента без расхода AI Credits.
* **Защита BYOK & Лицензирование:** Локальная дешифрация ключей завязана на серверную подпись JWT. Критические модули скопилированы через Cython. **Offline Grace Period:** 48 часов.
* **Верховная сущность «Проект» (Project-Driven Architecture):** Полный доступ к Project System, включая изолированный Project Context, авто-версионирование (SemVer/CalVer/Hybrid), Git-роутинг и фоновые авто-агенты.
* **Social Build in Public Module:** Автоматическая генерация постов для X.com/Reddit из Changelog с модерацией в 1 клик и фоновый сбор входящего фидбека.
* **Лимиты Проектов:** Максимум 5 активных проектов, 5 SSH-хостов, 5 параллельных фоновых задач, доступ к top-ups (макс 5/мес).

---

## 12. ОРКЕСТРАТОР МОДЕЛЕЙ И СТРОГАЯ ФИЛЬТРАЦИЯ

### 12.1. Принцип Строгой Фильтрации (Strict Model Filtering)

Оркестратор работает **строго с моделями, явно включенными пользователем в настройках** (`localStorage` по ключу `rf_selected_models_${provider}`). Модели, снятые с выбора, никогда не вызываются. Смысл чекбоксов в настройках как раз в том, чтобы отсечь слабые или неподходящие модели.

### 12.2. Принцип Router Model

Для анализа сложности запроса используется самый дешевый и быстрый роутер из разрешенного списка моделей (под «доступными» понимаются строго отмеченные в настройках модели от разных провайдеров).

Функция роутера: Анализирует входящий запрос пользователя, оценивает его сложность, подбирает и передает задачу той модели, которая лучше всего подходит для ее решения.

Приоритеты при подборе моделей (от высшего к низшему):

1. Мощность и качество (соответствие возможностям модели)
2. Цена (приоритет бесплатным / объем токенов и контекста)
3. Скорость работы

### 12.3. Каскадный Роутинг Провайдеров

Система использует клиентскую матрицу распределения (Smart Local Matrix) в `llm_router_service.py` для минимальной нагрузки на бэкенд:

1. **Fast Chat & Sub-second tasks:** `Groq` и `Cerebras` (LPU/WSE чипы, 500–2600+ tok/s). Автодополнение терминала и отладка команд.
2. **Heavy Document & Long Context:** `Gemini` (контекст до 2M токенов). Загрузка больших репозиториев и логов.
3. **Privacy / Offline mode:** `Ollama` / `LM Studio`. Работа с конфиденциальным кодом без сети.
4. **Deep Reasoning & Architecture:** `DeepSeek`, `OpenAI`, `Anthropic`, `xAI`. Архитектурные задачи и Consilium.
* Это все при условии что все они доступны иначе действует принцип максимально возможной эффективноси из того что есть.

### 12.4. Режимы Работы Оркестратора
AUTO (Free, Pro, Studio): Выбор исполнителя на основе сложности промпта, стоимости и задержки. Оркестратор сам выбирает оптимального исполнителя.
AUTONOMOUS TEAM MODE / ATM (Pro, Studio): Многоагентная схема «Архитектор $\rightarrow$ Исполнитель» с полным циклом `Planning $\rightarrow$ Implementation $\rightarrow$ Verification $\rightarrow$ Decision`.
- **Роль Архитектора**: Декомпозиция задачи, планирование шагов, Code Review и контроль Definition of Done (DoD).
- **Роль Исполнителя**: Написание кода, генерация тестов, применение фиксов.
- **Роль Дизайнер**: Дизайн и написание кода UI, генерация текстов и картинок, применение фиксов.
- **Ограничение**: Доступно строго для тарифа Pro (с бесплатными провайдерами) и Studio (с платными провайдерами) и выше.
LOCAL (Free, Pro, Studio): Строгая фильтрация только локальными движками (`ollama`, `lm_studio`). Работа только с локальными моделями, запущенными на ПК или VPS пользователя.
MANUAL (Studio): По умолчанию автоматически выбирает одиночную самую мощную модель из списка разрешенных (или жестко фиксирует выбор пользователя). Оркестратор выполняет только fallback.
CONSILIUM (Pro, Studio): Автоматически выбирает две самые мощные, но обязательно разные модели из разрешенных для дебатов (Draft и Critic) и третью модель-судью — еще более мощную, чем две спорящие — для итогового синтеза. По умолчанию подбираются рассуждающие модели автоматически + функция ручного выбора из всех доступных моделей.

### 12.5. Индикатор Выполнения Оркестратора

Во время обработки запроса в реальном времени работает динамический шкальный индикатор загрузки (`#orchestrator-progress-bar`) и бейдж статуса `Running` в панели Оркестратора.

### 12.6. Реферальные Ссылки

На странице настроек BYOK UI (`providers_ui_controller.js`) интегрированы реферальные ссылки для получения бесплатных API-ключей.

---

## 13. ВЕРХОВНАЯ СУЩНОСТЬ «ПРОЕКТ» (PROJECT-DRIVEN ARCHITECTURE)

«Проект» (Project) является корневым объектом системы. Все ресурсы, сессии, SSH-подключения, Git-ветки, версии и SMM-ключи изолируются внутри конкретного `project_id`.

### 13.1. Структура и Компоненты Проекта

| Компонент | Зона ответственности и спецификация |
| --- | --- |
| **Project Context & Rules** | Хранит текстовый стек и архитектурные гайдлайны, а также прикрепленные мульти-файлы контекста (`.md`, `.txt`, `.json`). Автоматически внедряется в системный промпт каждого агента (`AgentContextBuilder`). Задает жесткий Workflow для агентов (например: Код → Тесты → Changelog → Версия → Push → Social Post). |
| **Workspace** | Локальная директория или параметры подключения Remote SSH VPS (`ps-ssh-host`, `ps-ssh-port`, `ps-ssh-user`, `ps-ssh-password`, `ps-ssh-key`). Абсолютный локальный путь к директории проекта, привязанный к `project_id`. |
| **Git & GitHub Engine** | GitHub Remote URL (`git@github.com:...`), PAT токен, режим пуша (Manual / Auto-Push), умный роутинг веток (отправка коммитов в `dev`, `main` или `release/*` на основе тегов). |
| **Versioning System** | Стандарты SemVer (`v1.2.3`), CalVer (`v2026.07.31`) или Hybrid (`v2026.07.31-1.0.0`), поддержка предрелизных тегов (`-alpha`, `-beta`, `-rc1`). Авто-расчет инкремента версии и генерация Changelog на базе выполненных задач. |
| **Social SMM Keys** | Ключи интеграции X.com Bearer Token и Reddit Client ID/Secret для публикации релизов. |

### 13.2. Двухуровневая Система Настроек

1. **Глобальные настройки (Settings Modal):** Профиль пользователя, темы оформления, глобальные ключи API (BYOK), лимиты кредитов, системный аудит, форма техподдержки.
2. **Настройки Проекта (`#project-settings-modal`):** Полнофункциональное табулированное окно настроек конкретного проекта (**General & Rules**, **Workspace & SSH**, **Git & GitHub**, **SMM Platform Keys**).

### 13.3. Безопасность и хранение конфигов Проекта

Конфигурации, правила и контекст проекта хранятся **строго локально в SQLite БД** (`runtime.db`), в связанных таблицах `projects`, `project_git_rules`, `project_ssh_configs` с привязкой к `user_id`.

*Вынос правил в `.runtimeforce.yaml` в корень проекта запрещен для предотвращения перехвата конфиденциальных данных другими пользователями при совместном использовании устройства.*

---

## 14. МОДУЛЬ SOCIAL & FEEDBACK (BUILD IN PUBLIC) — STUDIO ONLY

Модуль бесшовно интегрируется в конец Workflow Проекта и работает полностью в фоновом режиме.

### 14.1. Фоновая оркестрация и источники данных

* Для генерации постов выделяется легковесный фоновый профиль (например, локальная Ollama / Qwen-7B / Llama 3.1 8B), работающий с низким приоритетом process queue, или если они не доступны — максимально дешевая модель, которая только может справиться с такими задачами.
* Вместо парсинга `git diff`, фоновая модель забирает структурированный `Changelog` из **Versioning System** при фиксации версии.

### 14.2. Workflow публикации и модерация

1. Фоновый агент генерирует человечный черновик поста для разработчиков на основе `Changelog`.
2. В UI дашборде Проекта появляется уведомление: кнопка **[Approve в 1 клик]** для мгновенной публикации в X.com и Reddit (с возможностью прикрепить скриншот/видео/документ).

Конкретные примеры работы фонового агента в RuntimeForce:

| Пример | Что делает агент в фоне |
| --- | --- |
| **Project Workflow** (Studio) | После коммита сам прогоняет: Тесты → Changelog → Версия → Push → Social Post |
| **Social генерация** (Studio) | Забирает Changelog, пишет черновик поста для X.com/Reddit, ждёт одобрения |
| **Feedback мониторинг** (Studio) | Парсит ответы в соцсетях, фильтрует спам, заносит баги в Task Board |
| **Длинный рефакторинг** | Перестраивает 30 файлов по заданию, пока ты работаешь в другой вкладке |
| **Consilium** (Pro/Studio) | 3+ модели спорят в фоне, ты получаешь уведомление когда готово |

Все эти процессы должны быть видны и логироваться в окне **Active Tools**.

### 14.3. Входящий Feedback Loop

Фоновый профиль мониторит ответы с X.com и Reddit, отсекает до 90% спама/токсичности, а конструктивные баги и фиче-реквесты структурирует и заносит в Task Board Проекта. При необходимости отвечает на вопросы из базы знаний (которую нужно доработать).

---

## 15. СТАНДАРТЫ ИНТЕРФЕЙСА (UI/UX) И STATE MANAGEMENT

### 15.1. Двухтональная Адаптивная Тема

Элементы `<select>` и `<option>` используют CSS-переменные (`var(--ide-surface)`, `var(--ide-text-primary)`), идеально сочетаясь со светлой и тёмной темой.

### 15.2. Редактор Monaco

Отслеживает состояние файлов (`isDirty`). При попытке закрыть файл без сохранения выводит предупреждение (`showConfirm`), а при закрытии файла автоматически переключает вкладку интерфейса на чат (`Chat`).

### 15.3. Карточка Воркспейса (Workspace Card)

Размещена в верхней части **File Explorer** над деревом файлов, отображая имя воркспейса, абсолютный путь и тип подключения (`Local` / `SSH`).

### 15.4. Галочка в Active Tools

При успешном вызове инструмента чтения файлов `read_workspace_file` в лог выводится зеленый символ **`✓`** (`text-emerald-400`).

### 15.5. Глобальная Валидация Опасных Команд

Потенциально опасные команды (`rm -rf`, `chmod 777`, `git reset --hard` и другие) вызывают мгновенное глобальное модальное окно `#command-approval-modal` с выбором:

* **Срок действия:** *Only this time*, *Only today*, *Always*.
* **Область применения:** *In this session*, *In this workspace*, *In this project*, *Everywhere*.

### 15.6. BYOK UI & Реферальные Ссылки

В карточки бесплатных провайдеров (Gemini, Groq, OpenRouter, SambaNova, Cerebras) интегрированы кнопки получения бесплатных ключей `Get Free Key ↗`.

### 15.7. Динамический Индикатор Провайдеров

В шапку карточки каждого провайдера выводится реактивный счетчик формата `Connected • 3/12 models selected`.

### 15.8. State Persistence

При открытии модального окна настройки провайдера чекбоксы выбранных моделей строго подтягиваются из локальной SQLite. Поведение `selectAll` по умолчанию запрещено.

---

## 16. СТОИМОСТЬ AI-ОПЕРАЦИЙ И CREDITS

Публичная единица измерения — **AI Credits** (1 credit ≈ $0.0005 AI cost внутренне).

* Quick answer / terminal explain: 1–2 credits.
* Standard code edit: 5–10 credits.
* Strong model: 20–50 credits.
* Multi-model consensus (Consilium): 100–300 credits.
* Heavy agent run: 200–1000 credits.

Before performing high-cost operations, UI displays an estimated credit cost approval dialog.

---

## 17. ТЕХНИЧЕСКИЙ СТАНДАРТ И СТРУКТУРА ФАЙЛОВ `RUNTIMEFORCE-APP`

Все имена файлов обязаны соответствовать архитектурному слою (`*_http_router.py`, `*_db_repository.py`, `*_driver.py`, `*_service.py`, `*_ui_controller.js`, `*_interface.py`).

### Обновленная целевая карта директорий `runtimeforce-app`:

```text
app/
 ├── main.py
 ├── container.py
 ├── config.py
 │
 ├── core/
 │   ├── interfaces/
 │   │   ├── workspace_driver_interface.py
 │   │   ├── workspace_driver_factory_interface.py
 │   │   ├── storage_repository_interface.py
 │   │   ├── llm_provider_interface.py
 │   │   ├── tool_executor_interface.py
 │   │   ├── audit_logger_interface.py
 │   │   ├── license_service_interface.py
 │   │   ├── credit_balance_service_interface.py
 │   │   ├── support_ticket_service_interface.py
 │   │   ├── byok_key_service_interface.py
 │   │   ├── project_service_interface.py
 │   │   ├── versioning_service_interface.py
 │   │   ├── social_module_interface.py
 │   │   ├── graph_memory_interface.py
 │   │   ├── decision_memory_interface.py
 │   │   ├── context_builder_interface.py
 │   │   ├── embedding_engine_interface.py
 │   │   ├── embedding_search_interface.py
 │   │   ├── rotation_service_interface.py
 │   │   ├── architect_agent_interface.py
 │   │   ├── engineer_agent_interface.py
 │   │   ├── designer_agent_interface.py
 │   │   ├── implementer_agent_interface.py
 │   │   ├── github_oauth_service_interface.py
 │   │   ├── x_oauth_service_interface.py
 │   │   ├── reddit_oauth_service_interface.py
 │   │   └── oauth_repository_interface.py
 │   │
 │   ├── security/
 │   │   ├── jwt_auth_service.py
 │   │   └── aes_crypto_service.py (Cython compiled)
 │   │
 │   └── events/
 │       └── event_bus.py
 │
 ├── repository/
 │   ├── db_connection.py
 │   ├── conversation_db_repository.py
 │   ├── workspace_db_repository.py
 │   ├── provider_keys_db_repository.py
 │   ├── ssh_keys_db_repository.py
 │   ├── telemetry_db_repository.py
 │   ├── subscription_db_repository.py
 │   ├── audit_local_db_repository.py
 │   ├── support_ticket_db_repository.py
 │   ├── project_db_repository.py
 │   ├── versioning_db_repository.py
 │   ├── social_feed_db_repository.py
 │   ├── graph_db_repository.py
 │   ├── decision_db_repository.py
 │   ├── embeddings_db_repository.py
 │   └── oauth_db_repository.py
 │
 ├── services/
 │   ├── workspace/
 │   │   ├── workspace_local_driver.py
 │   │   ├── workspace_ssh_driver.py
 │   │   ├── workspace_tree_service.py
 │   │   ├── workspace_file_service.py
 │   │   ├── workspace_manager_service.py
 │   │   └── workspace_driver_factory.py
 │   │
 │   ├── project/
 │   │   ├── project_manager_service.py
 │   │   ├── project_context_service.py
 │   │   └── project_rules_service.py
 │   │
 │   ├── versioning/
 │   │   ├── version_calculator_service.py
 │   │   └── changelog_generator_service.py
 │   │
 │   ├── social/
 │   │   ├── social_post_generator_service.py
 │   │   ├── social_feedback_listener_service.py
 │   │   ├── github_oauth_service.py
 │   │   ├── x_oauth_service.py
 │   │   ├── reddit_oauth_service.py
 │   │   └── oauth_smm_service.py
 │   │
 │   ├── ssh/
 │   │   ├── ssh_connection_pool.py
 │   │   ├── ssh_sftp_service.py
 │   │   └── ssh_credential_verifier.py
 │   │
 │   ├── git/
 │   │   ├── git_status_service.py
 │   │   ├── git_diff_service.py
 │   │   ├── git_commit_service.py
 │   │   ├── git_branch_service.py
 │   │   ├── git_log_service.py
 │   │   └── git_routing_service.py
 │   │
 │   ├── llm/
 │   │   ├── llm_registry_service.py
 │   │   ├── llm_discovery_service.py
 │   │   ├── llm_router_service.py
 │   │   ├── llm_rotation_service.py
 │   │   ├── llm_scoring_service.py
 │   │   ├── llm_consilium_service.py (Cython compiled)
 │   │   └── llm_orchestrator_service.py
 │   │
 │   ├── agent/
 │   │   ├── agent_intent_classifier.py
 │   │   ├── agent_context_builder.py
 │   │   ├── agent_loop_detector.py
 │   │   ├── agent_regex_fallback.py
 │   │   ├── agent_loop_coordinator.py
 │   │   ├── agent_safety_guard_service.py
 │   │   ├── architect_agent_service.py
 │   │   ├── engineer_agent_service.py
 │   │   ├── designer_agent_service.py
 │   │   └── implementer_agent_service.py
 │   │
 │   ├── memory/
 │   │   ├── graph_memory_service.py
 │   │   ├── graph_traversal_service.py
 │   │   ├── context_builder_service.py
 │   │   ├── context_cache_service.py
 │   │   ├── decision_recorder_service.py
 │   │   ├── embedding_engine_service.py
 │   │   ├── local_embedding_service.py
 │   │   ├── file_intelligence_service.py
 │   │   ├── git_intelligence_service.py
 │   │   ├── terminal_intelligence_service.py
 │   │   ├── intent_analyzer_service.py
 │   │   ├── memory_ranking_service.py
 │   │   ├── summarizer_service.py
 │   │   └── token_budget_allocator.py
 │   │
 │   ├── terminal/
 │   │   ├── terminal_runner_service.py
 │   │   └── terminal_command_filter.py
 │   │
 │   ├── billing/
 │   │   ├── license_service.py (Cython compiled)
 │   │   ├── subscription_cache_service.py (Cython compiled)
 │   │   ├── credit_balance_service.py
 │   │   └── usage_limit_service.py
 │   │
 │   ├── byok/
 │   │   ├── byok_key_service.py (Cython compiled)
 │   │   ├── byok_safety_service.py
 │   │   ├── byok_openai_driver.py
 │   │   ├── byok_anthropic_driver.py
 │   │   └── byok_openrouter_driver.py
 │   │
 │   ├── audit/
 │   │   ├── audit_logger_service.py
 │   │   └── audit_local_query_service.py
 │   │
 │   └── support/
 │       ├── support_ticket_service.py
 │       ├── support_diagnostics_service.py
 │       └── support_bot_service.py
 │
 ├── tools/
 │   ├── tool_registry_manifest.py
 │   ├── tool_dispatcher_service.py
 │   ├── tool_file_executors.py
 │   ├── tool_shell_executors.py
 │   ├── tool_patch_executor.py
 │   └── tool_git_executors.py
 │
 ├── api/
 │   ├── http/
 │   │   ├── workspace_http_router.py
 │   │   ├── project_http_router.py
 │   │   ├── git_http_router.py
 │   │   ├── session_http_router.py
 │   │   ├── message_http_router.py
 │   │   ├── model_http_router.py
 │   │   ├── keys_http_router.py
 │   │   ├── telemetry_http_router.py
 │   │   ├── billing_http_router.py
 │   │   ├── usage_http_router.py
 │   │   ├── audit_http_router.py
 │   │   ├── support_http_router.py
 │   │   ├── social_http_router.py
 │   │   ├── memory_http_router.py
 │   │   ├── oauth_http_router.py
 │   │   ├── git_oauth_http_router.py
 │   │   └── social_oauth_http_router.py
 │   │
 │   └── websocket/
 │       ├── chat_ws_router.py
 │       └── chat_ws_session_manager.py
 │
 └── static/
     ├── css/
     │   └── main.css
     │
     ├── js/
     │   ├── core/
     │   │   ├── event_bus.js
     │   │   ├── state_store.js
     │   │   ├── api_http_client.js
     │   │   └── chat_ws_client.js
     │   │
     │   ├── services/
     │   │   ├── auth_frontend_service.js
     │   │   ├── billing_frontend_service.js
     │   │   ├── usage_frontend_service.js
     │   │   ├── support_frontend_service.js
     │   │   ├── local_models_service.js
     │   │   ├── project_frontend_service.js
     │   │   ├── avatar_ui_service.js
     │   │   └── oauth_frontend_service.js
     │   │
     │   ├── components/
     │   │   ├── chat_ui_controller.js
     │   │   ├── file_tree_ui_controller.js
     │   │   ├── editor_ui_controller.js
     │   │   ├── terminal_ui_controller.js
     │   │   ├── git_ui_controller.js
     │   │   ├── workspace_ui_controller.js
     │   │   ├── project_ui_controller.js
     │   │   ├── providers_ui_controller.js
     │   │   ├── settings_ui_controller.js
     │   │   ├── trace_ui_controller.js
     │   │   ├── toast_ui_controller.js
     │   │   ├── billing_ui_controller.js
     │   │   ├── usage_ui_controller.js
     │   │   ├── support_ui_controller.js
     │   │   ├── audit_ui_controller.js
     │   │   ├── social_ui_controller.js
     │   │   ├── chat.js
     │   │   ├── audit.js
     │   │   ├── filetree.js
     │   │   ├── fileviewer.js
     │   │   ├── git.js
     │   │   ├── orchestrator_ui.js
     │   │   ├── projects_ui_controller.js
     │   │   ├── providers.js
     │   │   ├── sessions.js
     │   │   ├── settings.js
     │   │   ├── setup_wizard_ui_controller.js
     │   │   ├── social.js
     │   │   ├── support.js
     │   │   ├── terminal.js
     │   │   ├── toast.js
     │   │   ├── trace.js
     │   │   ├── usage.js
     │   │   └── workspace.js
     │   │
     │   ├── utils/
     │   │   ├── escape.js
     │   │   ├── format.js
     │   │   └── icons.js
     │   │
     │   ├── main.js
     │   ├── state.js
     │   └── app_bootstrap.js
     │
     └── index.html
```

---

## 18. ГЛАВНАЯ ИНСТРУКЦИЯ ДЛЯ AI-РАЗРАБОТЧИКА

При любой задаче:

1. Соблюдай Loose Coupling Architecture.
2. Используй DI container (`container.py`).
3. Используй event bus (`EventBus`).
4. Не создавай жестких зависимостей.
5. Не смешивай слои.
6. Не храни секреты на сервере.
7. Не доверяй клиенту billing.
8. Не логируй prompts, code, keys.
9. Все имена файлов и код — английский.
10. Пояснения в чате — русский.
11. Для изменений файлов `index.html` и `main.css` НЕ использовать авто-скрипты `cat << EOF`, а отдавать чистый код напрямую в чат для ручной вставки пользователем.

## 19. ## ✅ Graph Memory Architecture

Все фиксы верифицированы. Код корректен. Pipeline замкнут полностью.

---

### Финальная сводка системы

```
User Prompt
    │
    ▼
AgentLoopCoordinator
    ├─ history > 25 → SummarizerService → [COMPRESSED HISTORY]
    ├─ iteration == 1 → GitIntelligenceService.index_recent_git_activity()
    │
    ▼
ContextBuilderService.build_optimal_context()
    ├─ IntentAnalyzerService.analyze()
    ├─ EmbeddingsDBRepository.hybrid_search(top_k=5)
    ├─ ContextCacheService.get_delta_context()
    │   ├─ HIT → cached_nodes + delta
    │   └─ MISS → keyword SQL → BFS(depth=2, decay=0.7) → MemoryRanking
    ├─ DecisionRepo.get_decisions(limit=5)
    ├─ TokenBudgetAllocator (dynamic %)
    └─ Assembly + Cap → compiled_memory_context
    │
    ▼
LLMOrchestratorService.stream_completion()
    │
    ▼
Post-response feedback loop:
    ├─ DecisionRecorderService (JSON extraction → graph)
    ├─ FileIntelligenceService (AST/regex → graph)
    ├─ GitIntelligenceService (on git commit/merge)
    ├─ TerminalIntelligenceService (on exit_code ≠ 0)
    └─ ContextCacheService.update_cache()
```

---

### Что делать дальше

**Немедленно (тестирование):**

1. Создать тестовый workspace с 5–10 Python-файлами
2. Выполнить 3–4 итерации диалога с tool calls
3. Проверить `GET /api/v1/memory/subgraph/{project_id}` — граф должен расти
4. Проверить, что на 26-м сообщении срабатывает summarizer
5. Проверить, что повторный запрос "продолжи" даёт cache hit в логах

**Мониторинг (первая неделя):**

- Логировать `cache_hit` rate (цель: >40% при непрерывной работе)
- Логировать `nodes_count` и `compiled_memory_context` length (цель: стабильно < 5000 токенов)
- Следить за размером `runtime.db` (граф не должен расти бесконечно — нужен pruning)

**v2.0 (следующий этап):**

| Фича | Приоритет |
|------|-----------|
| Graph Pruning (удаление узлов с score < 0.1 старше 30 дней) | High |
| MCP-совместимость (expose graph как MCP resource) | Medium |
| Multi-agent memory sharing (несколько моделей читают один граф) | Medium |
| Tree-sitter вместо regex для TS/Go/Rust | Low |
| Distributed graph (PostgreSQL + pgvector для команд) | Low |
| UI: визуализация графа в IDE (D3.js / Cytoscape) | Low |

---

Система больше не деградирует от длины диалога. Контекст определяется не историей сообщений, а структурой знаний проекта. Это и есть отличие AI Runtime IDE от чат-бота.

20. АРХИТЕКТУРНЫЕ ИНВАРИАНТЫ И ПРАВИЛА ПРЕДОТВРАЩЕНИЯ РЕГРЕССА (Graph Memory & Pocock Skills)

Данный раздел является абсолютным приоритетом. Любое изменение кода, нарушающее эти инварианты, считается критическим багом и должно быть немедленно отклонено при code review.

20.1. Инвариант сборки контекста (No Linear History)
• ЗАПРЕЩЕНО: Использовать полную историю сообщений (`get_session_messages`) как основной источник контекста для LLM.
• ОБЯЗАТЕЛЬНО: Перед каждым запросом к LLM вызывается строго `ContextBuilderService.build_optimal_context()`.
• Контекст формируется исключительно через: Intent Analysis → Hybrid Search → BFS Graph Traversal (depth=2) → Memory Ranking → Token Budget Capping.
• Инкрементальный кэш (`ContextCacheService`) должен использоваться для повторных запросов с семантическим сходством > 0.8.

20.2. Инвариант исполнения инструментов (No Mocked Execution)
• ЗАПРЕЩЕНО: Имитировать успешное выполнение тестов или команд терминала без реального вызова `ToolDispatcherService` и `IWorkspaceDriver`.
• ОБЯЗАТЕЛЬНО: В TDD-цикле статус узла `Test` меняется на `GREEN` ТОЛЬКО после реального выполнения команды тестирования и получения `exit_code == 0`.
• Хук `on_file_written_by_agent` в `AgentLoopCoordinator` должен вызываться автоматически при любой записи файлов агентом для отслеживания состояния `RED`/`GREEN`.

20.3. Инвариант целостности Графа Памяти (Graph Memory Integrity)
• ЗАПРЕЩЕНО: Создавать узлы графа (`create_graph_node`) напрямую через `IStorageRepository` в бизнес-логике, минуя сервисы памяти.
• ОБЯЗАТЕЛЬНО: Все новые сущности (Decision, Test, TerminalCmd, Hypothesis) должны создаваться или регистрироваться через `GraphMemoryService.record_entity()`, чтобы гарантировать автоматическую генерацию и сохранение векторных эмбеддингов (`node_embeddings`) для последующего Hybrid Search.

20.4. Инвариант инженерной дисциплины (Pocock Skills Enforcement)
• Debugging Protocol: При обнаружении бага агент НЕ имеет права сразу предлагать исправление. Он обязан пройти фазы: reproduce → minimise → hypothesise (3-5 узлов) → instrument → verify. Каждая фаза фиксируется в графе через `TerminalIntelligenceService`.
• ADR Filtering: `DecisionRecorderService` обязан применять строгий фильтр. Узел помечается как `is_adr: true` и получает связь `CONSTRAINS` ТОЛЬКО если в тексте одновременно присутствуют признаки: (1) hard-to-reverse, (2) surprising, (3) trade-off. Остальное — обычные Decision узлы.
• Domain Alignment: `IntentAnalyzerService` обязан проверять термины пользователя против глоссария проекта. При обнаружении конфликтов агент должен задать уточняющий вопрос (grilling), а не гадать.

20.5. Инвариант интеллекта файлов и тестов (File & Test Intelligence)
• ЗАПРЕЩЕНО: Связывать узел `Test` с узлом `Function` по имени тестовой функции (например, `test_my_function`).
• ОБЯЗАТЕЛЬНО: `FileIntelligenceService.index_test_file` должен извлекать реальные целевые швы (seams) через анализ вызовов: `assert function_name(...)`, `@patch("...")`, `expect(function_name)`. Связь `TESTS_SEAM` создается только с этими целевыми функциями/классами.
• Встроенные функции (`len`, `dict`, `True`, `Equal` и т.д.) должны быть жестко исключены из списка целевых швов через набор `ignored`.

20.6. Правило сохранения языковых стандартов
• Весь код, имена переменных, названия классов, ключи JSON, названия таблиц БД и логи — СТРОГО на английском языке.
• Все пояснения, комментарии в этом файле, ответы на русском