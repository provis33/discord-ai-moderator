"""Persistent role-toggle buttons. custom_id stays stable across restarts."""

from __future__ import annotations

import discord

from logging_setup import log_action


class RoleToggleButton(discord.ui.Button):
    """Gives or removes one role when pressed."""

    def __init__(self, role_id: int, label: str) -> None:
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"role_btn_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Эта панель работает только на сервере.",
                ephemeral=True,
            )
            return

        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("Роль не найдена.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "У бота нет права Manage Roles.",
                ephemeral=True,
            )
            return

        if role.is_default() or role.managed or role >= bot_member.top_role:
            await interaction.response.send_message(
                "Не могу выдать эту роль: проверьте иерархию (роль бота должна быть выше).",
                ephemeral=True,
            )
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Role panel toggle")
                action = "role_remove"
                reply = f"Роль **{role.name}** снята."
            else:
                await member.add_roles(role, reason="Role panel toggle")
                action = "role_add"
                reply = f"Роль **{role.name}** выдана."
        except discord.Forbidden:
            await interaction.response.send_message(
                "Недостаточно прав, чтобы изменить эту роль.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord не принял изменение роли. Попробуйте ещё раз.",
                ephemeral=True,
            )
            return

        log_action(
            guild_id=guild.id,
            channel_id=interaction.channel_id,
            user_id=member.id,
            action=action,
            reason=f"role={role.id} ({role.name})",
        )
        await interaction.response.send_message(reply, ephemeral=True)


class RolePanelView(discord.ui.View):
    """Persistent view: timeout=None so buttons work after a bot restart."""

    def __init__(self, roles: tuple[tuple[int, str], ...]) -> None:
        # RU: timeout=None — кнопки живут после рестарта, custom_id фиксированный.
        # EN: timeout=None keeps the buttons persistent; custom_id must stay fixed.
        super().__init__(timeout=None)
        for role_id, label in roles:
            self.add_item(RoleToggleButton(role_id, label))
