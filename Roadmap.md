# `Roadmap.md`

```md
# 🗺️ RUNTIMEFORCE ROADMAP

## 1. ТЕКУЩИЙ ЭТАП

Текущий этап разработки включает только:

```text
Free
Pro
Studio
```

Enterprise не реализуется на текущем этапе.

Enterprise вынесен в раздел Planned.

---

## 2. ЦЕЛЬ ТЕКУЩЕГО ЭТАПА

Запустить стабильный коммерческий продукт с простой экономикой:

```text
Free   → попробовать
Pro    → managed AI для разработчика
Studio → managed AI + BYOK для power user
```

Основные задачи:

```text
стабильный billing через Paddle;
credit ledger;
server-side limits;
local BYOK для Studio;
local audit;
support bot;
docs;
usage dashboard;
orchestrator;
SSH async queue;
terminal cleanup.
```

---

## 3. PHASE 1 — MVP

### Billing

```text
Paddle Checkout
Paddle webhooks
subscription activation
subscription cancellation
past due handling
top-up purchases
3-day Pro trial without card
```

### Credits

```text
server-side credit ledger
monthly credits reset
no rollover
top-up credits valid 90 days
monthly credits consumed first
operation cost estimation
hard stop on limit
```

### Plans

```text
Free internal DB
Pro Paddle subscription
Studio Paddle subscription
```

### Limits

```text
Free 100 messages/day
Free hard caps
Pro 5,000 credits/month
Studio 15,000 credits/month
Pro max operation 500 credits
Studio max operation 2,000 credits
active projects limits
SSH hosts limits
background jobs limits
```

### BYOK

```text
Studio only
local key storage
direct provider calls
no RuntimeForce credits consumed
7-day offline grace
local safety limits
```

### Support

```text
docs
FAQ
AI support bot
ticket creation
Telegram fallback
read-only diagnostics
```

### Audit

```text
local audit log
server billing/license audit only
no prompts
no code
no keys
```

---

## 4. PHASE 2 — STABILIZATION

Цель:

```text
сделать продукт надежным перед масштабированием.
```

Задачи:

```text
улучшение error handling;
улучшение SSE stability;
улучшение SSH reconnect;
улучшение terminal cleanup;
улучшение credit usage UI;
улучшение support bot;
расширение docs;
анализ churn;
анализ top-up behavior;
анализ AI cost per plan;
оптимизация model routing;
кэширование;
prompt compression;
fallback improvements.
```

Критерии успеха:

```text
низкий процент failed AI requests;
низкий процент zombie processes;
поддержка решает большинство вопросов через bot;
AI cost держится в пределах 13–15%;
нет критических billing инцидентов.
```

---

## 5. PHASE 3 — GROWTH

Цель:

```text
улучшить конверсию Free → Pro → Studio.
```

Возможные задачи:

```text
onboarding wizard;
project templates;
SSH quick connect;
AI usage analytics;
smart model recommendations;
cost estimator;
consilium UX improvements;
annual plan promotion;
top-up recommendations;
referral mechanics;
public changelog;
community templates.
```

Не делать growth до стабилизации Phase 2.

---

## 6. PLANNED: ENTERPRISE

Enterprise находится полностью в стадии planned.

На текущем этапе не реализуется.

---

## 6.1. Enterprise positioning

Enterprise — это:

```text
Studio + team control + admin + policies + audit + SSO
```

Для кого:

```text
команды разработки;
небольшие dev-организации;
компании с требованиями к контролю;
компании с требованиями к аудиту;
компании с internal security policies.
```

---

## 6.2. Предполагаемая цена

```text
from $99/seat/month
from $990/seat/year
minimum 5 seats
```

Credits:

```text
30,000 AI Credits per seat/month
pooled credits across organization
```

Пример:

```text
5 seats × 30,000 = 150,000 credits/month
```

Top-ups:

```text
custom or unlimited by policy
```

---

## 6.3. Enterprise features

### Organization management

```text
organization entity
seats
invites
member removal
owner transfer
billing centralization
```

---

### RBAC

Планируемые роли:

```text
owner
admin
member
viewer
```

Позже:

```text
custom roles
project-level roles
workspace-level roles
```

---

### SSO

Сначала:

```text
Google OAuth as normal login
Google Workspace domain restriction
```

Потом:

```text
OIDC
SAML
Okta
Azure AD / Entra ID
Auth0
WorkOS
```

Рекомендация:

```text
не строить SAML самостоятельно;
использовать WorkOS или Auth0.
```

---

### SCIM

Планируется:

```text
automatic provisioning
deprovisioning
group mapping
directory sync
```

---

### Team workspaces

Shared:

```text
workspace metadata
settings
AI instructions
task templates
non-secret config
```

Not shared:

```text
SSH private keys
API keys
passwords
tokens
env secrets
```

Позже:

```text
encrypted secrets vault
per-workspace secrets
secret rotation
secret access audit
```

---

### Spend caps

Планируемые лимиты:

```text
org monthly credits
org daily credits
user monthly credits
user daily credits
max credits per operation
max credits per model group
alert threshold
hard stop
```

Пример:

```text
Org budget: 150,000 credits/month
Per user: 30,000 credits/month
Per operation: 2,000 credits
Premium models: max 30% of budget
Consilium: max 10% of budget
Alert at: 80%
Hard stop at: 100%
```

---

### Policies

Минимальный policy engine:

```json
{
  "byok_mode": "allowed",
  "managed_ai_enabled": true,
  "allowed_providers": [],
  "blocked_models": [],
  "max_context_tokens": 128000,
  "max_output_tokens": 8000,
  "max_credits_per_operation": 2000,
  "require_confirmation_over_credits": 500,
  "allow_consilium": false,
  "allow_background_agents": true
}
```

BYOK modes:

```text
allowed
required
disabled
```

---

### Centralized audit

Текущее решение:

```text
full audit log local
server only billing/license events
```

Enterprise planned:

```text
clients send encrypted audit metadata hourly
server acts as relay or temporary storage
admin can export or sync audit data
```

Allowed metadata:

```text
user action
timestamp
workspace id
model
credits used
error code
policy violation
ssh host metadata
session started/stopped
```

Forbidden:

```text
prompts
full AI answers
source code
private keys
API keys
passwords
tokens
env variables
```

Если audit relay хранится на сервере, необходимо:

```text
encryption at rest;
retention limit;
access control;
delete on request;
privacy policy update.
```

---

### Enterprise support

Planned SLA:

```text
priority async support
response within 24 business hours
founder-led escalation
no 24/7 real-time support
```

Каналы:

```text
AI bot
docs
ticket
priority ticket queue
Telegram notification for critical tickets
```

Не обещать:

```text
24/7 chat
instant response
phone support
on-site support
```

---

### Enterprise billing

Planned:

```text
per-seat subscription
pooled credits
central billing
annual invoicing
prorated seat changes
custom contracts for larger orgs
```

Через Paddle:

```text
subscription seats
one-time top-ups
annual plans
```

Для крупных клиентов:

```text
custom pricing
invoice-based billing
custom terms
```

---

### Security and compliance

Planned:

```text
SSO
RBAC
audit
policies
spend caps
data retention controls
BYOK required mode
local-only mode
encryption in transit
encryption at rest for server metadata
```

Не обещать на старте:

```text
SOC 2
HIPAA
ISO 27001
full GDPR certification
on-prem
private cloud
```

Это можно добавлять позже только при реальном спросе.

---

### On-prem / private deployment

Planned only as custom enterprise option.

Возможно позже:

```text
single-node private deployment
docker compose deployment
license key activation
offline license validation
customer-managed database
customer-managed AI keys
```

Не делать сейчас.

---

## 7. ENTERPRISE PHASES

---

## 7.1. Phase E0 — Preparation

Начинать только после стабилизации Free/Pro/Studio.

Требуется:

```text
stable billing;
stable credits;
stable BYOK;
support bot working;
docs complete;
local audit working;
low refund rate;
low support load;
predictable AI cost.
```

---

## 7.2. Phase E1 — Enterprise MVP

```text
organizations
seats
owner/admin/member roles
manual invites
pooled credits
basic spend caps
basic policies
local audit export
priority ticket flag
minimum 5 seats
```

Без:

```text
SAML
SCIM
centralized audit UI
custom roles
secrets vault
on-prem
```

---

## 7.3. Phase E2 — Enterprise Control

```text
RBAC viewer
policy UI
audit relay
audit export
team workspaces
shared settings
spend cap alerts
usage analytics
```

---

## 7.4. Phase E3 — Enterprise Identity

```text
Google Workspace domain restriction
OIDC
SAML via WorkOS/Auth0
SCIM
directory sync
MFA enforcement through IdP
```

---

## 7.5. Phase E4 — Enterprise Custom

```text
custom contracts
custom pricing
on-prem
private deployment
advanced retention
dedicated onboarding
```

---

## 8. КРИТЕРИИ НАЧАЛА ENTERPRISE

Не начинать Enterprise, пока нет:

```text
10+ платящих Pro/Studio;
3+ входящих запроса от команд;
стабильный billing;
support bot решает большую часть типовых вопросов;
нет хаоса с credits;
нет частых инцидентов с BYOK;
понятный churn;
MRR хотя бы $500–1000.
```

Иначе Enterprise съест слишком много времени.

---

## 9. PLANNED ECOSYSTEM MODULES

После стабилизации основного продукта возможны следующие модули.

---

## 9.1. AI UI Creator

```text
генерация интерфейсов из набросков;
генерация интерфейсов из скриншотов;
генерация интерфейсов из текстовых описаний;
нативная работа с Tailwind CSS;
синхронное обновление фронтенда при изменении backend.
```

Live Preview внутри среды отложен.

Текущий фокус:

```text
генерация качественной файловой структуры для внешнего рендеринга.
```

---

## 9.2. Analytics and Validation

```text
парсинг Product Hunt;
парсинг Reddit;
парсинг X.com;
выявление болей пользователей;
поиск актуальных ниш;
сборка waitlist-лендингов;
сбор email до написания продукта.
```

---

## 9.3. Auto-Marketing and Build in Public

```text
генерация постов о проделанной работе;
публикация в X.com;
публикация в Reddit;
публикация в GitHub;
SEO-статьи на основе архитектурных решений;
привлечение органического трафика.
```

---

## 9.4. DevOps and Infrastructure

```text
автоматический деплой на bare metal;
установка Docker;
установка Nginx;
выпуск SSL;
self-healing code;
мониторинг логов;
анализ traceback;
автоматический фикс;
автоматический деплой обновления.
```

---

## 9.5. QA and Documentation

```text
непрерывное авто-тестирование;
генерация unit tests;
генерация e2e tests;
поддержание Swagger/OpenAPI;
поддержание README.md;
синхронизация документации с коммитами.
```

---

## 10. DEFERRED / NOT NOW

Отложено:

```text
Enterprise;
team workspaces;
RBAC UI;
policy UI;
centralized audit UI;
SSO/SAML;
SCIM;
secrets vault;
on-prem;
private cloud;
SOC 2;
HIPAA;
ISO 27001;
mobile app;
Live Preview;
marketplace;
public API;
plugin system;
multiplayer editing;
real-time collaboration;
24/7 support.
```

---

## 11. ГЛАВНЫЙ ПРИНЦИП ROADMAP

Сначала:

```text
стабильный Free/Pro/Studio
```

Потом:

```text
growth
```

Потом:

```text
Enterprise
```

Потом:

```text
ecosystem automation
```

Нельзя начинать Enterprise или ecosystem modules до стабилизации core billing, credits, SSH, terminal, AI orchestrator и support.
```