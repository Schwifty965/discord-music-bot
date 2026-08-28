import json
import os
from datetime import datetime, timezone
from typing import Optional

import discord


class VoiceMonitor:
    """
    Monitor Voice Channel activity across the server.

    Tracks:
    - Join
    - Leave
    - Move

    Does NOT record voice/audio.

    Session tracking is kept in memory while the bot is running.
    Reconnects / repeated on_ready events will NOT reset an
    existing user's join time.
    """

    CONFIG_FILE = "voice_log_config.json"

    def __init__(self, bot):
        self.bot = bot

        # Guild ID -> Text Channel ID
        self.log_channels: dict[int, int] = {}

        # Guild ID -> User ID -> join information
        self.sessions: dict[
            int,
            dict[int, dict]
        ] = {}

        self.load_config()

    # ============================================================
    # CONFIG
    # ============================================================

    def load_config(self):
        """Load log channel configuration from disk."""

        if not os.path.exists(
            self.CONFIG_FILE
        ):
            return

        try:

            with open(
                self.CONFIG_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

            self.log_channels = {
                int(guild_id): int(channel_id)
                for guild_id, channel_id
                in data.items()
            }

            print(
                f"[VoiceMonitor] Loaded "
                f"{len(self.log_channels)} log configuration(s)."
            )

        except Exception as error:

            print(
                f"[VoiceMonitor] Failed to load config: "
                f"{error}"
            )

    def save_config(self):
        """Save log channel configuration to disk."""

        try:

            with open(
                self.CONFIG_FILE,
                "w",
                encoding="utf-8",
            ) as f:

                json.dump(
                    self.log_channels,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        except Exception as error:

            print(
                f"[VoiceMonitor] Failed to save config: "
                f"{error}"
            )

    # ============================================================
    # SET LOG CHANNEL
    # ============================================================

    def set_log_channel(
        self,
        guild_id: int,
        channel_id: int,
    ):
        """Set the Voice Log text channel for a guild."""

        self.log_channels[guild_id] = channel_id

        self.save_config()

    # ============================================================
    # GET LOG CHANNEL
    # ============================================================

    def get_log_channel(
        self,
        guild: discord.Guild,
    ) -> Optional[discord.TextChannel]:
        """Return configured log channel."""

        channel_id = self.log_channels.get(
            guild.id
        )

        if not channel_id:
            return None

        channel = guild.get_channel(
            channel_id
        )

        if isinstance(
            channel,
            discord.TextChannel,
        ):
            return channel

        return None

    # ============================================================
    # TIME
    # ============================================================

    @staticmethod
    def now():
        return datetime.now(
            timezone.utc
        )

    @staticmethod
    def format_time(
        dt: datetime,
    ) -> str:
        """Convert UTC datetime to local system time."""

        local = dt.astimezone()

        return local.strftime(
            "%H:%M:%S"
        )

    @staticmethod
    def format_duration(
        seconds: float,
    ) -> str:
        """Format seconds into Thai duration text."""

        total = int(seconds)

        hours = total // 3600

        minutes = (
            total % 3600
        ) // 60

        seconds = total % 60

        if hours > 0:

            return (
                f"{hours} ชั่วโมง "
                f"{minutes} นาที "
                f"{seconds} วินาที"
            )

        if minutes > 0:

            return (
                f"{minutes} นาที "
                f"{seconds} วินาที"
            )

        return (
            f"{seconds} วินาที"
        )

    # ============================================================
    # USER DISPLAY
    # ============================================================

    @staticmethod
    def user_name(
        member: discord.Member,
    ) -> str:

        if member.display_name:
            return member.display_name

        return member.name

    # ============================================================
    # SEND LOG
    # ============================================================

    async def send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
    ):
        """Send an activity embed to configured log channel."""

        channel = self.get_log_channel(
            guild
        )

        if not channel:
            return

        try:

            await channel.send(
                embed=embed
            )

        except discord.Forbidden:

            print(
                f"[VoiceMonitor] Missing permission "
                f"to send messages in #{channel.name} "
                f"({guild.name})"
            )

        except Exception as error:

            print(
                f"[VoiceMonitor] Failed to send log: "
                f"{error}"
            )

    # ============================================================
    # CREATE EMBED
    # ============================================================

    def create_embed(
        self,
        title: str,
        description: str,
    ) -> discord.Embed:

        embed = discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.from_rgb(
                75,
                75,
                75,
            ),
        )

        embed.set_author(
            name="UNIT-Ⅲ『ᛗᛟᛗᛟ』"
        )

        embed.set_footer(
            text=(
                "Voice Monitor • "
                "UNIT-Ⅲ『ᛗᛟᛗᛟ』"
            )
        )

        return embed

    # ============================================================
    # VOICE STATE UPDATE
    # ============================================================

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """
        Handle Discord Voice State updates.

        Only reacts to actual channel changes.
        Mute/deaf changes are ignored.
        """

        before_channel = before.channel
        after_channel = after.channel

        # --------------------------------------------------------
        # Ignore mute/deaf/etc.
        # --------------------------------------------------------

        if before_channel == after_channel:
            return

        guild = member.guild

        # --------------------------------------------------------
        # Ignore bots
        # --------------------------------------------------------

        if member.bot:
            return

        now = self.now()

        guild_sessions = self.sessions.setdefault(
            guild.id,
            {},
        )

        # ========================================================
        # JOIN
        # ========================================================

        if (
            before_channel is None
            and after_channel is not None
        ):

            guild_sessions[member.id] = {
                "channel_id": after_channel.id,
                "channel_name": after_channel.name,
                "joined_at": now,
            }

            embed = self.create_embed(
                "🔊 VOICE ACTIVITY",
                (
                    f"👤 **{self.user_name(member)}**\n"
                    f"➡️ เข้าร่วม **{after_channel.name}**\n"
                    f"🕐 `{self.format_time(now)}`"
                ),
            )

            embed.add_field(
                name="Member",
                value=member.mention,
                inline=True,
            )

            embed.add_field(
                name="Channel",
                value=after_channel.mention,
                inline=True,
            )

            await self.send_log(
                guild,
                embed,
            )

            print(
                f"[VoiceMonitor] "
                f"{member} joined "
                f"{after_channel.name}"
            )

            return

        # ========================================================
        # LEAVE
        # ========================================================

        if (
            before_channel is not None
            and after_channel is None
        ):

            session = guild_sessions.pop(
                member.id,
                None,
            )

            duration_text = None

            if session:

                joined_at = session.get(
                    "joined_at"
                )

                if joined_at:

                    duration = (
                        now - joined_at
                    ).total_seconds()

                    duration_text = (
                        self.format_duration(
                            duration
                        )
                    )

            description = (
                f"👤 **{self.user_name(member)}**\n"
                f"⬅️ ออกจาก **{before_channel.name}**\n"
                f"🕐 `{self.format_time(now)}`"
            )

            if duration_text:

                description += (
                    f"\n⏱️ อยู่ในห้อง "
                    f"`{duration_text}`"
                )

            embed = self.create_embed(
                "🔊 VOICE ACTIVITY",
                description,
            )

            embed.add_field(
                name="Member",
                value=member.mention,
                inline=True,
            )

            embed.add_field(
                name="Channel",
                value=before_channel.mention,
                inline=True,
            )

            await self.send_log(
                guild,
                embed,
            )

            print(
                f"[VoiceMonitor] "
                f"{member} left "
                f"{before_channel.name}"
            )

            return

        # ========================================================
        # MOVE
        # ========================================================

        if (
            before_channel is not None
            and after_channel is not None
        ):

            # ----------------------------------------------------
            # Get existing session
            # ----------------------------------------------------

            session = guild_sessions.get(
                member.id
            )

            duration_text = None

            if session:

                joined_at = session.get(
                    "joined_at"
                )

                if joined_at:

                    duration = (
                        now - joined_at
                    ).total_seconds()

                    duration_text = (
                        self.format_duration(
                            duration
                        )
                    )

            # ----------------------------------------------------
            # Start new session for new channel
            # ----------------------------------------------------

            guild_sessions[member.id] = {
                "channel_id": after_channel.id,
                "channel_name": after_channel.name,
                "joined_at": now,
            }

            description = (
                f"👤 **{self.user_name(member)}**\n"
                f"🔄 **{before_channel.name}** "
                f"→ **{after_channel.name}**\n"
                f"🕐 `{self.format_time(now)}`"
            )

            if duration_text:

                description += (
                    f"\n⏱️ อยู่ห้องเดิม "
                    f"`{duration_text}`"
                )

            embed = self.create_embed(
                "🔊 VOICE ACTIVITY",
                description,
            )

            embed.add_field(
                name="Member",
                value=member.mention,
                inline=True,
            )

            embed.add_field(
                name="From",
                value=before_channel.mention,
                inline=True,
            )

            embed.add_field(
                name="To",
                value=after_channel.mention,
                inline=True,
            )

            await self.send_log(
                guild,
                embed,
            )

            print(
                f"[VoiceMonitor] "
                f"{member} moved "
                f"{before_channel.name} -> "
                f"{after_channel.name}"
            )

    # ============================================================
    # STARTUP SYNC
    # ============================================================

    def sync_guild(
        self,
        guild: discord.Guild,
    ):
        """
        Synchronize current Voice users after bot startup.

        IMPORTANT:
        Existing sessions are preserved.

        This prevents repeated on_ready events / Discord
        reconnects from resetting a user's original join time.
        """

        guild_sessions = self.sessions.setdefault(
            guild.id,
            {},
        )

        now = self.now()

        synced = 0
        preserved = 0

        for channel in guild.voice_channels:

            for member in channel.members:

                if member.bot:
                    continue

                existing = guild_sessions.get(
                    member.id
                )

                # ------------------------------------------------
                # Already tracked in the SAME channel
                # ------------------------------------------------
                #
                # DO NOT reset joined_at.
                #

                if (
                    existing
                    and existing.get("channel_id")
                    == channel.id
                ):

                    preserved += 1

                    continue

                # ------------------------------------------------
                # New user/session
                # ------------------------------------------------

                guild_sessions[member.id] = {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "joined_at": now,
                }

                synced += 1

        print(
            f"[VoiceMonitor] Synced "
            f"{guild.name} "
            f"(new: {synced}, "
            f"preserved: {preserved})"
        )