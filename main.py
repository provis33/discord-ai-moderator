"""Discord AI moderator: toxicity, spam, role buttons, file logs."""

from __future__ import annotations

import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from config import Settings, load_settings
from logging_setup import log_action, setup_logging
from moderation import ModerationChecker
from roles import RolePanelView
from spam import SpamTracker

logger = logging.getLogger("moderator")
NOTICE_DELETE_AFTER = 10
SNIPPET_LIMIT = 300


def is_bypassed(member: discord.Member, bypass_role_id: int | None) -> bool:
    """Skip moderation for the owner, admins, and the optional bypass role."""

    # RU: Не таймауть администраторов и владельца сервера.
    # EN: Never timeout admins or the guild owner.
    if member.id == member.guild.owner_id:
        return True
    if member.guild_permissions.administrator:
        return True
    if bypass_role_id is not None and any(role.id == bypass_role_id for role in member.roles):
        return True
    return False


def _snippet(text: str) -> str:
    cleaned = text.replace("```", "`").strip()
    if len(cleaned) > SNIPPET_LIMIT:
        return cleaned[:SNIPPET_LIMIT] + "…"
    return cleaned


class ModeratorBot(commands.Bot):
    """Slash-only moderator bot with spam heuristics and OpenAI checks."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.settings = settings
        self.spam_tracker = SpamTracker(
            window_seconds=settings.spam_window_seconds,
            max_messages=settings.spam_max_messages,
        )
        self.moderation = ModerationChecker(
            api_key=settings.openai_api_key,
            model=settings.moderation_model,
        )

    async def setup_hook(self) -> None:
        # RU: Persistent View, чтобы кнопки ролей работали после рестарта.
        # EN: Register a persistent view so role buttons survive restarts.
        if self.settings.roles:
            self.add_view(RolePanelView(self.settings.roles))
        self.tree.add_command(roles_command)
        await self.tree.sync()

    async def close(self) -> None:
        await self.moderation.close()
        await super().close()

    async def on_ready(self) -> None:
        user = self.user
        logger.info("Bot ready as %s (%s)", user, user.id if user else "?")
        if not self.settings.openai_api_key:
            logger.warning("Running without OPENAI_API_KEY: toxicity checks are disabled")

    async def on_message(self, message: discord.Message) -> None:
        """Ignore bots/DMs/empty/bypass, then spam, then OpenAI moderation."""

        if message.author.bot or message.guild is None:
            return
        content = (message.content or "").strip()
        if not content:
            return
        if not isinstance(message.author, discord.Member):
            return
        if is_bypassed(message.author, self.settings.bypass_role_id):
            return

        mention_count = len({user.id for user in message.mentions}) + len(
            {role.id for role in message.role_mentions}
        )
        spam = self.spam_tracker.check(
            guild_id=message.guild.id,
            user_id=message.author.id,
            content=content,
            mention_count=mention_count,
            mention_everyone=bool(message.mention_everyone),
        )
        if spam.flagged:
            await self._punish(
                message,
                minutes=self.settings.spam_timeout_minutes,
                action="timeout_spam",
                reason=spam.reason,
            )
            return

        result = await self.moderation.check_text(content)
        if result.flagged:
            await self._punish(
                message,
                minutes=self.settings.mute_minutes,
                action="timeout_toxicity",
                reason=result.reason,
            )

    async def _punish(
        self,
        message: discord.Message,
        *,
        minutes: int,
        action: str,
        reason: str,
    ) -> None:
        guild = message.guild
        author = message.author
        if guild is None or not isinstance(author, discord.Member):
            return

        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            log_action(
                guild_id=guild.id,
                channel_id=message.channel.id,
                user_id=author.id,
                action="delete_failed",
                reason="missing Manage Messages",
                level=logging.ERROR,
            )
        except discord.HTTPException as exc:
            logger.error("Failed to delete message: %s", type(exc).__name__)

        timeout_ok = False
        # RU: Timeout только если бот может мутить и цель ниже его роли.
        # EN: Timeout only when the bot can moderate and outranks the target.
        try:
            await author.timeout(timedelta(minutes=minutes), reason=reason[:512])
            timeout_ok = True
        except discord.Forbidden:
            log_action(
                guild_id=guild.id,
                channel_id=message.channel.id,
                user_id=author.id,
                action="timeout_failed",
                reason="missing Moderate Members or role hierarchy",
                level=logging.ERROR,
            )
        except discord.HTTPException as exc:
            log_action(
                guild_id=guild.id,
                channel_id=message.channel.id,
                user_id=author.id,
                action="timeout_failed",
                reason=type(exc).__name__,
                level=logging.ERROR,
            )

        notice = (
            f"{author.mention}: сообщение удалено"
            + (f", мут {minutes} мин" if timeout_ok else ", мут не выдан")
            + f". Причина: {reason}"
        )
        try:
            sent = await message.channel.send(notice)
            await sent.delete(delay=NOTICE_DELETE_AFTER)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send punishment notice in channel %s", message.channel.id)

        log_action(
            guild_id=guild.id,
            channel_id=message.channel.id,
            user_id=author.id,
            action=action,
            reason=reason,
        )
        await self._send_log_embed(
            guild,
            member=author,
            channel=message.channel,
            action=action,
            reason=reason,
            minutes=minutes if timeout_ok else 0,
            snippet=_snippet(message.content or ""),
        )

    async def _send_log_embed(
        self,
        guild: discord.Guild,
        *,
        member: discord.Member,
        channel: discord.abc.Messageable,
        action: str,
        reason: str,
        minutes: int,
        snippet: str,
    ) -> None:
        if self.settings.log_channel_id is None:
            return
        log_channel = guild.get_channel(self.settings.log_channel_id)
        if not isinstance(log_channel, discord.TextChannel):
            logger.warning("LOG_CHANNEL_ID=%s not found or not a text channel", self.settings.log_channel_id)
            return

        embed = discord.Embed(title="Модерация", color=discord.Color.orange())
        embed.add_field(name="Пользователь", value=f"{member.mention} (`{member.id}`)", inline=False)
        channel_label = getattr(channel, "mention", str(getattr(channel, "id", channel)))
        embed.add_field(name="Канал", value=channel_label, inline=False)
        embed.add_field(name="Действие", value=action, inline=True)
        embed.add_field(name="Мут, мин", value=str(minutes), inline=True)
        embed.add_field(name="Причина", value=reason[:1024], inline=False)
        if snippet:
            embed.add_field(name="Текст", value=snippet[:1024], inline=False)
        embed.set_footer(text=f"guild={guild.id}")
        try:
            await log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Could not send embed to log channel %s", log_channel.id)


@app_commands.command(name="roles", description="Опубликовать панель выдачи ролей")
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def roles_command(interaction: discord.Interaction) -> None:
    bot = interaction.client
    if not isinstance(bot, ModeratorBot):
        await interaction.response.send_message("Бот ещё не готов.", ephemeral=True)
        return
    if not bot.settings.roles:
        await interaction.response.send_message(
            "В `.env` не заданы ROLE_ID_n — панель пустая.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "Выберите роли кнопками ниже. Повторное нажатие снимает роль.",
        view=RolePanelView(bot.settings.roles),
    )


def main() -> None:
    setup_logging()
    settings = load_settings()
    bot = ModeratorBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
