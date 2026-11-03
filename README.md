# discord-ai-moderator
Advanced Discord moderation bot with AI-powered toxicity detection and role management | Продвинутый бот модерации Discord с ИИ-детекцией токсичности и управлением ролями

## Что умеет

- Слушает сообщения на сервере и игнорирует ботов, ЛС, пустой текст, владельца сервера, администраторов и роль `BYPASS_ROLE_ID`.
- Сначала проверяет **спам-эвристики** (дешево, без API). Если спама нет — вызывает **OpenAI Moderation API**.
- При нарушении удаляет сообщение, выдаёт мут, пишет короткое уведомление в канал (удаляется через 10 секунд) и строку в `logs/moderation.log`.
- Если задан `LOG_CHANNEL_ID` — дополнительно шлёт embed в лог-канал.
- Команда `/roles` публикует persistent-кнопки: нажатие выдаёт роль, повторное — снимает.

## Требования

- Python 3.11+
- Приложение бота в [Discord Developer Portal](https://discord.com/developers/applications)

## Установка

```bash
cd discord-ai-moderator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

На Linux/macOS: `source .venv/bin/activate` и `cp .env.example .env`.

Откройте `.env` и заполните значения. **Не коммитьте `.env`.**

## Discord Developer Portal

В разделе **Bot** включите:

- `MESSAGE CONTENT INTENT`
- `SERVER MEMBERS INTENT`

Инвайт-ссылка (OAuth2 → URL Generator):

- Scopes: `bot`, `applications.commands`
- Bot Permissions:
  - View Channel
  - Send Messages
  - Embed Links
  - Manage Messages
  - Moderate Members
  - Manage Roles
  - Read Message History

Роль бота на сервере должна стоять **выше** ролей, которые он выдаёт и которых мутит.

## Переменные `.env`

| Переменная | Назначение |
| --- | --- |
| `DISCORD_TOKEN` | Токен бота. Пустой — бот не запустится. |
| `OPENAI_API_KEY` | Ключ OpenAI. Пустой — бот стартует, токсичность не проверяется. |
| `LOG_CHANNEL_ID` | Канал для embed-логов. Можно оставить пустым. |
| `MUTE_MINUTES` | Длительность мута за токсичность (по умолчанию `10`). |
| `MODERATION_MODEL` | Модель модерации, по умолчанию `omni-moderation-latest`. |
| `BYPASS_ROLE_ID` | Роль, которую бот не модерирует. |
| `SPAM_WINDOW_SECONDS` | Окно антиспама в секундах (`10`). |
| `SPAM_MAX_MESSAGES` | Больше этого числа сообщений в окне = спам (`5`). |
| `SPAM_TIMEOUT_MINUTES` | Мут за спам (`10`). |
| `ROLE_ID_1` … `ROLE_ID_3` | ID ролей для кнопок. Пустой слот не создаёт кнопку. |
| `ROLE_LABEL_1` … `ROLE_LABEL_3` | Подписи кнопок. |

## Запуск

```bash
python main.py
```

Первая синхронизация `/roles` глобальная: команда может появиться в Discord с задержкой (иногда до часа). Перезапуск бота не ломает уже опубликованные кнопки ролей.

## Команды

- `/roles` — публикует панель ролей. Нужно право **Manage Roles**. Если в `.env` нет ни одного `ROLE_ID_n`, бот ответит, что панель пустая.

## Как устроена модерация

1. Спам (без OpenAI):
   - больше `SPAM_MAX_MESSAGES` сообщений от одного пользователя за `SPAM_WINDOW_SECONDS`;
   - 3 одинаковых текста в том же окне;
   - 5+ упоминаний пользователей/ролей;
   - `@everyone` / `@here`;
   - ссылки-инвайты `discord.gg/`, `discord.com/invite/`, `discordapp.com/invite/`.
2. Если спама нет — текст уходит в OpenAI Moderation. Наказание, если `flagged` и сработала одна из категорий: hate, harassment, violence, sexual, self-harm (включая threatening/graphic/minors/intent/instructions).
3. Спам не вызывает API, чтобы не тратить квоту.

Мут за спам — `SPAM_TIMEOUT_MINUTES`, за токсичность — `MUTE_MINUTES`. Если бот не может выдать timeout (нет права или иерархия), сообщение всё равно пытается удалить и пишет ошибку в лог.

## Fallback без OpenAI

Если `OPENAI_API_KEY` пустой, бот **не падает**. Все сообщения считаются чистыми по токсичности, в лог пишется предупреждение. Антиспам при этом работает как обычно.

Ошибка API, таймаут (15 с) или rate limit: одна повторная попытка через 2 секунды. Если снова сбой — сообщение не наказывается.

## Логи

Файл: `logs/moderation.log`

Формат строки:

```text
2026-11-03 19:00:00,123 | INFO | guild=123 channel=456 user=789 action=timeout_spam reason=spam: too many messages
```

Токены и ключи в лог не пишутся.

## Ручная проверка

1. Заполните `DISCORD_TOKEN`, запустите бота, убедитесь, что в консоли есть `Bot ready`.
2. `/roles` — кнопки появляются; нажатие выдаёт роль, повтор снимает. Роль бота выше выдаваемой.
3. С обычного (не админ) аккаунта отправьте 6 сообщений за 10 секунд — удаление и мут.
4. Отправьте `discord.gg/example` — сработает эвристика инвайта.
5. Три одинаковых сообщения подряд — повтор текста.
6. С заполненным `OPENAI_API_KEY` отправьте заведомо токсичный текст — мут `MUTE_MINUTES`.
7. Без ключа тот же текст остаётся, в логе есть warning про fallback.
8. Появился файл `logs/moderation.log` и (если задан канал) embed в лог-канале.

## Замечания

- Бот не модерирует вложения без текста.
- Невалидные числа в `.env` заменяются дефолтами из таблицы, в лог пишется warning.
- Реальных секретов в репозитории нет: только `.env.example` с пустыми ключами.      
