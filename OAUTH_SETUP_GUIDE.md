# 🔐 OAuth Setup Guide for RuntimeForce

Этот гайд поможет вам настроить OAuth-аутентификацию для GitHub, X.com (Twitter) и Reddit.

---

## 📋 Предварительные требования

1. Запущенный экземпляр `runtimeforce-app` (локально или на VPS)
2. Доступ к админ-панели для регистрации OAuth-приложений
3. HTTPS для production (требуется большинством провайдеров)

---

## 1️⃣ GitHub OAuth (для Git интеграции)

### Шаг 1: Создайте OAuth App в GitHub

1. Перейдите в **Settings** → **Developer settings** → **OAuth Apps**
2. Нажмите **New OAuth App**
3. Заполните форму:
   - **Application name**: `RuntimeForce IDE`
   - **Homepage URL**: `http://localhost:8000` (для dev) или `https://yourdomain.com` (для prod)
   - **Authorization callback URL**: `http://localhost:8000/api/v1/oauth/github/callback`
   - **Device Flow**: Отключено

### Шаг 2: Получите Credentials

После создания приложения вы получите:
- **Client ID** (например, `Iv1.a1b2c3d4e5f6g7h8`)
- **Client Secret** (например, `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0`)

### Шаг 3: Настройте Environment Variables

```bash
# В файле .env или export в терминале
export GITHUB_OAUTH_CLIENT_ID="Iv1.a1b2c3d4e5f6g7h8"
export GITHUB_OAUTH_CLIENT_SECRET="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
export GITHUB_OAUTH_CALLBACK_URL="http://localhost:8000/api/v1/oauth/github/callback"
```

### Шаг 4: Перезапустите приложение

```bash
systemctl restart ai-runtime.service
# или
uvicorn app.main:app --reload
```

---

## 2️⃣ X.com (Twitter) OAuth 2.0

### Шаг 1: Создайте проект в Developer Portal

1. Перейдите на [developer.twitter.com](https://developer.twitter.com/en/portal/dashboard)
2. Создайте новый проект и приложение
3. Выберите **OAuth 2.0** при настройке

### Шаг 2: Настройте Redirect URI

В настройках приложения добавьте:
- **Redirect URI / Callback URL**: `http://localhost:8000/api/v1/oauth/x/callback`
- **App permissions**: `Read and Write` (для публикации постов)
- **Type of App**: `Web App, Automated App or Bot`

### Шаг 3: Получите Credentials

- **Client ID**: (например, `abc123xyz789`)
- **Client Secret**: (например, `def456uvw012ghi789jkl345mno678pqr901`)

### Шаг 4: Настройте Environment Variables

```bash
export X_OAUTH_CLIENT_ID="abc123xyz789"
export X_OAUTH_CLIENT_SECRET="def456uvw012ghi789jkl345mno678pqr901"
export X_OAUTH_CALLBACK_URL="http://localhost:8000/api/v1/oauth/x/callback"
```

---

## 3️⃣ Reddit OAuth

### Шаг 1: Создайте приложение в Reddit

1. Перейдите в [Reddit Apps](https://www.reddit.com/prefs/apps)
2. Нажмите **create another app...**
3. Выберите тип: **web app**

### Шаг 2: Заполните данные

- **name**: `RuntimeForce Social`
- **about url**: `https://runtimeforce.dev`
- **redirect uri**: `http://localhost:8000/api/v1/oauth/reddit/callback`

### Шаг 3: Получите Credentials

- **Client ID**: Отображается под названием приложения (например, `abc123XYZ`)
- **Client Secret**: Нажмите **edit**, чтобы увидеть (например, `def456-UVW789_GHI012`)

### Шаг 4: Настройте Environment Variables

```bash
export REDDIT_OAUTH_CLIENT_ID="abc123XYZ"
export REDDIT_OAUTH_CLIENT_SECRET="def456-UVW789_GHI012"
export REDDIT_OAUTH_CALLBACK_URL="http://localhost:8000/api/v1/oauth/reddit/callback"
```

---

## ✅ Проверка работы

### 1. Проверьте логи приложения

```bash
journalctl -u ai-runtime.service -f
# Ищите строки типа:
# [INFO] runtimeforce.oauth: GitHub OAuth initialized
# [INFO] runtimeforce.oauth: X.com OAuth configured
```

### 2. Протестируйте в UI

1. Откройте RuntimeForce IDE в браузере
2. Откройте **Project Settings** → **Git & GitHub**
3. Нажмите кнопку **Connect with GitHub OAuth**
4. Должно открыться OAuth-окно авторизации

### 3. Проверьте API endpoints

```bash
# GitHub
curl -X POST http://localhost:8000/api/v1/oauth/github/authorize \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test-123"}'

# X.com
curl -X POST http://localhost:8000/api/v1/oauth/x/authorize \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test-123"}'

# Reddit
curl -X POST http://localhost:8000/api/v1/oauth/reddit/authorize \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test-123"}'
```

---

## 🔒 Безопасность

### Production Checklist

- [ ] Используйте **HTTPS** для всех callback URLs
- [ ] Никогда не коммитьте `.env` файл в Git
- [ ] Регулярно обновляйте Client Secrets
- [ ] Используйте environment-specific credentials (dev/staging/prod)
- [ ] Включите CORS только для доверенных доменов

### Permissions

| Провайдер | Минимальные права | Рекомендуемые права |
|-----------|------------------|---------------------|
| GitHub | `public_repo` | `repo`, `read:user`, `user:email` |
| X.com | Read | Read & Write |
| Reddit | identity | identity, submit, read |

---

## 🐛 Troubleshooting

### Ошибка: "Popup blocked"

**Решение:** Разрешите popups для вашего домена в настройках браузера.

### Ошибка: "redirect_uri_mismatch"

**Причина:** Callback URL в настройках OAuth не совпадает с `*_OAUTH_CALLBACK_URL`

**Решение:** Убедитесь, что URLs идентичны (включая `http/https` и порт).

### Ошибка: "Invalid client_secret"

**Причина:** Неверный secret или лишние пробелы

**Решение:** Скопируйте secret заново без пробелов, проверьте encoding.

### Логи показывают "OAuth service not initialized"

**Причина:** Переменные окружения не загружены

**Решение:**
```bash
# Проверьте переменные
printenv | grep OAUTH

# Перезапустите сервис
systemctl daemon-reload
systemctl restart ai-runtime.service
```

---

## 📚 Дополнительные ресурсы

- [GitHub OAuth Docs](https://docs.github.com/en/developers/apps/building-oauth-apps)
- [Twitter OAuth 2.0 Guide](https://developer.twitter.com/en/docs/authentication/oauth-2-0)
- [Reddit OAuth2 Wiki](https://github.com/reddit-archive/reddit/wiki/OAuth2)

---

## ✨ Что дальше?

После настройки OAuth:

1. **Автоматическая публикация релизов** — подключите X.com и Reddit для авто-постинга из Changelog
2. **Git integration** — используйте OAuth токен вместо PAT для безопасного пуша
3. **Social feedback loop** — собирайте фидбек из соцсетей прямо в Task Board проекта

**Готово!** Теперь ваша система поддерживает безопасную OAuth-аутентификацию. 🎉
