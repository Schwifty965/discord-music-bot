import asyncio
from typing import Optional

import discord

from .queue import MusicQueue, Song


class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot

        # Guild ID -> Queue
        self.queues: dict[int, MusicQueue] = {}

        # Guild ID -> Currently playing song
        self.current: dict[int, Optional[Song]] = {}

        # Guild ID -> Text channel used for music messages
        self.text_channels: dict[int, discord.TextChannel] = {}

        # Guild ID -> Playback task
        self.playback_tasks: dict[int, asyncio.Task] = {}

    # ============================================================
    # QUEUE
    # ============================================================

    def get_queue(self, guild_id: int) -> MusicQueue:
        """Get or create the queue for a guild."""

        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()

        return self.queues[guild_id]

    # ============================================================
    # QUEUE SUMMARY
    # ============================================================

    def get_queue_summary(self, guild_id: int) -> tuple[int, int]:
        """Get the number of queued songs and total remaining duration in seconds."""
        queue = self.get_queue(guild_id)

        if hasattr(queue, "all"):
            songs = queue.all()
        elif hasattr(queue, "songs"):
            songs = queue.songs
        else:
            songs = list(queue)

        queued_count = len(songs)
        remaining = 0

        current_song = self.current.get(guild_id)
        if current_song and getattr(current_song, "duration", None):
            remaining += current_song.duration

        for song in songs:
            if getattr(song, "duration", None):
                remaining += song.duration

        return queued_count, remaining

    # ============================================================
    # NOW PLAYING EMBED
    # ============================================================

    async def send_now_playing(
        self,
        song: Song,
        text_channel: discord.TextChannel,
    ):
        """Send the Now Playing embed."""

        embed = discord.Embed(
            description=(
                "**Started playing**\n\n"
                f"🎵 **{song.title}**\n"
                f"👤 by **{song.artist}**"
            ),
            colour=discord.Colour.from_rgb(75, 75, 75),
        )

        # Bot name
        embed.set_author(
            name="UNIT-Ⅲ『ᛗᛟᛗᛟ』"
        )

        # YouTube thumbnail
        if song.thumbnail:
            embed.set_thumbnail(
                url=song.thumbnail
            )

        # Duration
        if song.duration:
            minutes = song.duration // 60
            seconds = song.duration % 60

            embed.add_field(
                name="Duration",
                value=f"`{minutes}:{seconds:02d}`",
                inline=True,
            )

        # Source
        embed.add_field(
            name="Source",
            value="[YouTube]",
            inline=True,
        )

        # Footer
        embed.set_footer(
            text="Music Player 🎵 UNIT-Ⅲ『ᛗᛟᛗᛟ』"
        )

        await text_channel.send(
            embed=embed
        )

    # ============================================================
    # PLAY ONE SONG
    # ============================================================

    async def play_song(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
        song: Song,
        text_channel: discord.TextChannel,
    ):
        """Play one song."""

        self.current[guild.id] = song
        self.text_channels[guild.id] = text_channel

        # --------------------------------------------------------
        # FFmpeg
        # --------------------------------------------------------

        ffmpeg_options = {
            "before_options": (
                "-reconnect 1 "
                "-reconnect_streamed 1 "
                "-reconnect_delay_max 5"
            ),
            "options": "-vn",
        }

        source = discord.FFmpegPCMAudio(
            song.url,
            **ffmpeg_options,
        )

        # --------------------------------------------------------
        # Now Playing
        # --------------------------------------------------------

        await self.send_now_playing(
            song,
            text_channel,
        )

        # --------------------------------------------------------
        # Playback finished event
        # --------------------------------------------------------

        finished = asyncio.Event()

        def after_playing(error):
            if error:
                print(
                    f"[Music] Playback error "
                    f"in {guild.name}: {error}"
                )

            self.bot.loop.call_soon_threadsafe(
                finished.set
            )

        # --------------------------------------------------------
        # Start playback
        # --------------------------------------------------------

        voice_client.play(
            source,
            after=after_playing,
        )

        # Wait until FFmpeg finishes
        await finished.wait()

        # --------------------------------------------------------
        # Cleanup
        # --------------------------------------------------------

        try:
            source.cleanup()
        except Exception:
            pass

    # ============================================================
    # PLAYBACK LOOP
    # ============================================================

    async def playback_loop(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
    ):
        """Continuously play songs from the queue."""

        guild_id = guild.id
        queue = self.get_queue(guild_id)

        try:

            while voice_client.is_connected():

                # ------------------------------------------------
                # Get next song
                # ------------------------------------------------

                song = queue.get_next()

                # ------------------------------------------------
                # Queue finished
                # ------------------------------------------------

                if song is None:

                    channel = self.text_channels.get(
                        guild_id
                    )

                    if channel is not None:

                        try:
                            await channel.send(
                                "🏁 **เพลงในคิวหมดแล้วครับ**"
                            )
                        except Exception:
                            pass

                    break

                # ------------------------------------------------
                # Text channel
                # ------------------------------------------------

                channel = self.text_channels.get(
                    guild_id
                )

                if channel is None:
                    break

                # ------------------------------------------------
                # Play song
                # ------------------------------------------------

                try:

                    await self.play_song(
                        guild,
                        voice_client,
                        song,
                        channel,
                    )

                except Exception as error:

                    print(
                        f"[Music] Error playing "
                        f"{song.title}: {error}"
                    )

                    try:

                        await channel.send(
                            f"❌ เล่นเพลงไม่สำเร็จ: "
                            f"**{song.title}**"
                        )

                    except Exception:
                        pass

        finally:

            self.current.pop(
                guild_id,
                None,
            )

            self.playback_tasks.pop(
                guild_id,
                None,
            )

    # ============================================================
    # ADD SONG
    # ============================================================

    async def add_song(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
        song: Song,
        text_channel: discord.TextChannel,
    ):
        """Add song to queue."""

        guild_id = guild.id

        queue = self.get_queue(
            guild_id
        )

        self.text_channels[guild_id] = (
            text_channel
        )

        # --------------------------------------------------------
        # Nothing playing
        # --------------------------------------------------------

        if not voice_client.is_playing():

            queue.add(song)

            if guild_id not in self.playback_tasks:

                task = asyncio.create_task(
                    self.playback_loop(
                        guild,
                        voice_client,
                    )
                )

                self.playback_tasks[guild_id] = (
                    task
                )

            return False

        # --------------------------------------------------------
        # Something already playing
        # --------------------------------------------------------

        queue.add(song)

        position = len(queue)

        await text_channel.send(
            f"📜 Added to queue: "
            f"**{song.title}** by **{song.artist}**\n"
            f"Position: **#{position}**"
        )

        return True

    # ============================================================
    # SKIP
    # ============================================================

    async def skip(
        self,
        guild: discord.Guild,
    ):
        """Skip current song."""

        voice_client = guild.voice_client

        if not voice_client:
            return False

        if not voice_client.is_playing():
            return False

        voice_client.stop()

        return True

    # ============================================================
    # STOP
    # ============================================================

    async def stop(
        self,
        guild: discord.Guild,
    ):
        """Stop playback and clear queue."""

        voice_client = guild.voice_client

        queue = self.get_queue(
            guild.id
        )

        # Clear queue
        queue.clear()

        # Stop current song
        if (
            voice_client
            and voice_client.is_playing()
        ):
            voice_client.stop()

        # Clear current
        self.current.pop(
            guild.id,
            None,
        )

        return True