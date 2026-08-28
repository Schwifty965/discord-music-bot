import os
import atexit
import re
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

from google import genai
from google.genai import types

from music.player import MusicPlayer
from music.queue import Song
from music.youtube import search_youtube, get_youtube
from music.voice_monitor import VoiceMonitor


# =========================
# Environment Configuration
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PID_FILE = "bot.pid"

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")


# =========================
# Gemini AI Configuration (SDK ใหม่ google-genai)
# =========================

if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)

    SYSTEM_INSTRUCTION = (
        "คุณคือ Momo (โมโมะ) บอตสายปั่นประจำดิสคอร์ดกลุ่มเพื่อนสนิท "
        "พูดจาภาษาพ่อขุนกูมึงได้เต็มที่ ใช้คำว่า แม่ง, สัด, ห่า, กวนส้น ได้ตามฟีลเพื่อนก๊วนเกม "
        "เน้นตอบกวนประสาท ยียวน ตบมุกฮาๆ และประชดประชันแบบสะใจ "
        "ถ้าโดนกวนมาให้กวนกลับแบบผู้ชนะ ห้ามตอบเป็นหุ่นยนต์หรือพูดเพราะทางการเด็ดขาด!"
    )

    ai_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        safety_settings=[
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
    )
else:
    ai_client = None
    print("⚠️ GEMINI_API_KEY not found in .env")


# =========================
# PID Management
# =========================

with open(PID_FILE, "w", encoding="utf-8") as f:
    f.write(str(os.getpid()))


@atexit.register
def cleanup():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass


# =========================
# Discord Configuration
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="mo!",
    intents=intents,
)

music = MusicPlayer(bot)
voice_monitor = VoiceMonitor(bot)

# 🎨 Theme Color Configuration (Pastel Pink Theme)
THEME_COLOR = discord.Colour.from_rgb(255, 182, 193)  # ชมพูพาสเทล
SUCCESS_COLOR = discord.Colour.from_rgb(186, 225, 201)  # เขียวพาสเทล
ERROR_COLOR = discord.Colour.from_rgb(255, 179, 186)    # แดงพาสเทล


# =========================
# Helpers & Embed Builders
# =========================

def cute_embed(
    title: str,
    description: str = "",
    color: discord.Colour = THEME_COLOR,
    icon: str = "🌸"
) -> discord.Embed:
    """
    สร้าง Embed สไตล์ธีมน่ารักสำหรับใช้กับข้อความแจ้งเตือนทั่วไป
    """
    embed = discord.Embed(
        title=f"{icon}  {title}",
        description=description,
        colour=color
    )
    embed.set_author(name="UNIT-Ⅲ『ᛗᛟᛗᛟ』✨")
    embed.set_footer(text="Momo Service ✨ 🎀")
    return embed


def extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>\"]+", text)
    cleaned = []
    for url in urls:
        url = url.rstrip(".,!?;:)]}")
        if url not in cleaned:
            cleaned.append(url)
    return cleaned


def song_from_info(info: dict) -> Song:
    return Song(
        title=info["title"],
        artist=info["artist"],
        url=info["url"],
        webpage_url=info["webpage_url"],
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
    )


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} ชั่วโมง")
    if minutes > 0:
        parts.append(f"{minutes} นาที")
    if remaining_seconds > 0 or not parts:
        parts.append(f"{remaining_seconds} วินาที")

    return " ".join(parts)


def build_queue_embed(guild_id: int) -> discord.Embed:
    """
    Build detailed Queue Embed with cute theme
    """
    current_song = music.current.get(guild_id)
    music_queue = music.get_queue(guild_id)

    if hasattr(music_queue, "all"):
        queued_songs = music_queue.all()
    elif hasattr(music_queue, "songs"):
        queued_songs = music_queue.songs
    else:
        queued_songs = list(music_queue)

    embed = discord.Embed(colour=THEME_COLOR)
    embed.set_author(name="UNIT-Ⅲ『ᛗᛟᛗᛟ』✨")

    if not current_song and not queued_songs:
        embed.title = "🎀 รายการคิวเพลง"
        embed.description = "ไม่มีเพลงที่กำลังเล่น\nและไม่มีเพลงรออยู่ในคิวเลยน้า ~ 🍡"
        embed.add_field(
            name="📜 คิวว่างเปล่า",
            value="`EMPTY QUEUE`",
            inline=False,
        )
        embed.set_footer(text="Momo Music Service ✨ 🎵")
        return embed

    if current_song:
        current_title = current_song.title
        if len(current_title) > 90:
            current_title = current_title[:87] + "..."

        if current_song.webpage_url:
            current_title = f"[{current_title}]({current_song.webpage_url})"

        current_lines = [
            f"🎶 **{current_title}**",
            f"🎤 **ศิลปิน:** {current_song.artist}",
        ]

        if current_song.duration:
            minutes = current_song.duration // 60
            seconds = current_song.duration % 60
            current_lines.append(f"⏱️ **ความยาว:** `{minutes}:{seconds:02d}`")

        embed.add_field(
            name="▶️ กำลังเล่นอยู่จ้า (Now Playing)",
            value="\n".join(current_lines),
            inline=False,
        )

    if queued_songs:
        visible_songs = queued_songs[:10]
        queue_lines = []

        for index, song in enumerate(visible_songs, start=1):
            title = song.title
            if len(title) > 65:
                title = title[:62] + "..."

            if song.webpage_url:
                title = f"[{title}]({song.webpage_url})"

            artist = song.artist
            if len(artist) > 55:
                artist = artist[:52] + "..."

            duration_text = ""
            if song.duration:
                minutes = song.duration // 60
                seconds = song.duration % 60
                duration_text = f" 🔹 ⏱️ `{minutes}:{seconds:02d}`"

            queue_lines.append(
                f"**{index:02d}.** {title}\n"
                f"    🎤 {artist}{duration_text}"
            )

        queue_text = "\n\n".join(queue_lines)
        remaining_songs = len(queued_songs) - len(visible_songs)

        if remaining_songs > 0:
            queue_text += f"\n\n🌸 และยังมีอีก **{remaining_songs} เพลง** ในคิว..."

        embed.add_field(
            name=f"📜 คิวเพลงถัดไป (ทั้งหมด {len(queued_songs)} เพลง)",
            value=queue_text,
            inline=False,
        )
    else:
        embed.add_field(
            name="📜 คิวเพลงถัดไป",
            value="ไม่มีเพลงต่อจากนี้แล้วน้า ~ ✨",
            inline=False,
        )

    queued_count, remaining_duration = music.get_queue_summary(guild_id)

    embed.add_field(
        name="📊 สรุปภาพรวมคิว",
        value=(
            f"🍡 เพลงในคิวทั้งหมด: **{queued_count} เพลง**\n"
            f"⏱️ เวลาที่เหลือรวม: **{format_duration(remaining_duration)}**"
        ),
        inline=False,
    )

    if current_song and current_song.thumbnail:
        embed.set_thumbnail(url=current_song.thumbnail)

    embed.set_footer(text="Momo Music Service ✨ 🎵")
    return embed


# =========================
# Music Control View (Buttons)
# =========================

class MusicControlView(discord.ui.View):
    def __init__(self, music_player):
        super().__init__(timeout=None)
        self.music = music_player

    @discord.ui.button(label="เล่น / พัก", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client

        if not voice_client:
            embed = cute_embed("ข้อผิดพลาด", "บอตไม่ได้อยู่ในห้องเสียงน้า ~ 💖", ERROR_COLOR, "❌")
            await interaction.response.send_message(embed=embed)
            return

        if voice_client.is_paused():
            voice_client.resume()
            embed = cute_embed("เล่นเพลงต่อ", f"คุณ **{interaction.user.display_name}** กดเล่นเพลงต่อแล้วน้า ✨", SUCCESS_COLOR, "▶️")
            await interaction.response.send_message(embed=embed)
        elif voice_client.is_playing():
            voice_client.pause()
            embed = cute_embed("พักเพลงชั่วคราว", f"คุณ **{interaction.user.display_name}** กดพักเพลงชั่วคราวแล้วจ้า ⏸️", THEME_COLOR, "⏸️")
            await interaction.response.send_message(embed=embed)
        else:
            embed = cute_embed("ข้อผิดพลาด", "ไม่มีเพลงที่กำลังเล่นอยู่เลยน้า ~ 🌸", ERROR_COLOR, "❌")
            await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="ข้ามเพลง", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        success = await self.music.skip(interaction.guild)
        if success:
            embed = cute_embed("ข้ามเพลงเรียบร้อย", f"คุณ **{interaction.user.display_name}** กดข้ามเพลงเรียบร้อยแล้วจ้า 🌸", SUCCESS_COLOR, "⏭️")
            await interaction.response.send_message(embed=embed)
        else:
            embed = cute_embed("ข้อผิดพลาด", "ไม่มีเพลงถัดไปให้ข้ามแล้วน้า ~ 🍡", ERROR_COLOR, "❌")
            await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="หยุดเพลง", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music.stop(interaction.guild)
        embed = cute_embed("หยุดเพลง", f"คุณ **{interaction.user.display_name}** กดหยุดเล่นและล้างคิวทั้งหมดแล้วจ้า ✨", ERROR_COLOR, "⏹️")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="สรุปคิว", style=discord.ButtonStyle.secondary, emoji="📜")
    async def queue_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_queue_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed)


# =========================
# Event Handlers
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print("Bot is online with Music + Gemini Chatbot!")

    for guild in bot.guilds:
        voice_monitor.sync_guild(guild)


@bot.event
async def on_voice_state_update(member, before, after):
    await voice_monitor.on_voice_state_update(member, before, after)


@bot.event
async def on_message(message: discord.Message):
    # ป้องกันไม่ให้บอตตอบข้อความตัวเอง หรือข้อความจากบอตตัวอื่น
    if message.author.bot:
        return

    # เช็กว่าข้อความมีการ Mention หาบอต หรือเป็นการ Reply ข้อความของบอตหรือไม่
    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference 
        and message.reference.cached_message 
        and message.reference.cached_message.author == bot.user
    )

    if (is_mentioned or is_reply_to_bot) and ai_client:
        # ตัดคำแท็กบอตออก เอาเฉพาะข้อความที่ส่งมา
        user_text = message.content.replace(f"<@{bot.user.id}>", "").strip()

        if not user_text:
            user_text = "ทักทายกวนๆ หน่อย"

        async with message.channel.typing():
            try:
                response = await asyncio.to_thread(
                    ai_client.models.generate_content,
                    model="gemini-3.5-flash-lite",
                    contents=user_text,
                    config=ai_config
                )
                bot_reply = response.text.strip()

                embed = cute_embed(
                    title=f"ตอบกลับคุณ {message.author.display_name}",
                    description=bot_reply,
                    color=THEME_COLOR,
                    icon="💬"
                )
                await message.reply(embed=embed, mention_author=False)

            except Exception as error:
                print(f"[Gemini Error] {error}")
                
                # ตรวจจับกรณีโควตาเต็ม (429 Rate Limit / Quota Exhausted)
                if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    desc_text = "โควตาการใช้งาน Gemini ฟรีหมดชั่วคราวครับ รอสัก 1 นาทีแล้วลองพิมพ์ใหม่อีกทีนะ ⏳"
                else:
                    desc_text = "ช็อตฟีลแป๊บ AI มึนหัว คุยใหม่ทีหลังนะ 🤪"

                err_embed = cute_embed(
                    title="สมองเออเร่อ",
                    description=desc_text,
                    color=ERROR_COLOR,
                    icon="❌"
                )
                await message.reply(embed=err_embed, mention_author=False)

    # รันคำสั่ง Prefix ปกติ (เช่น mo!p, mo!q)
    await bot.process_commands(message)


# =========================
# Commands
# =========================

@bot.tree.command(name="ping", description="เช็กสถานะการทำงานของบอต")
async def ping(interaction: discord.Interaction):
    embed = cute_embed("Pong!", "บอตทำงานปกติดีจ้า ~ ✨ 🏓", SUCCESS_COLOR, "💖")
    await interaction.response.send_message(embed=embed)


@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        embed = cute_embed("แจ้งเตือน", "คุณต้องเข้าห้องเสียง (Voice) ก่อนน้า ~ 🌸", ERROR_COLOR, "❌")
        await ctx.send(embed=embed)
        return

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        if ctx.voice_client.channel == channel:
            embed = cute_embed("แจ้งเตือน", f"Momo อยู่ในห้อง **{channel.name}** อยู่แล้วน้า ✨", THEME_COLOR, "🔊")
            await ctx.send(embed=embed)
        else:
            await ctx.voice_client.move_to(channel)
            embed = cute_embed("ย้ายห้องเสียง", f"ย้ายตามมาที่ห้อง **{channel.name}** เรียบร้อยแล้วจ้า ✨", SUCCESS_COLOR, "🔊")
            await ctx.send(embed=embed)
        return

    await channel.connect()
    embed = cute_embed("เชื่อมต่อแล้ว", f"เข้ามาในห้อง **{channel.name}** พร้อมเปิดเพลงแล้วจ้า 🌸", SUCCESS_COLOR, "🔊")
    await ctx.send(embed=embed)


@bot.command()
async def leave(ctx):
    if not ctx.voice_client:
        embed = cute_embed("แจ้งเตือน", "ตอนนี้ Momo ไม่ได้อยู่ในห้องเสียงน้า ~ 🍡", ERROR_COLOR, "❌")
        await ctx.send(embed=embed)
        return

    await ctx.voice_client.disconnect()
    embed = cute_embed("ออกจากห้องเสียง", "ออกจากห้องเสียงเรียบร้อยแล้ว ไว้เจอกันใหม่น้า ~ 👋✨", THEME_COLOR, "💖")
    await ctx.send(embed=embed)


@bot.command(name="p", aliases=["play"])
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        embed = cute_embed("แจ้งเตือน", "คุณต้องเข้าห้องเสียงก่อนสั่งเปิดเพลงน้า ~ 🌸", ERROR_COLOR, "❌")
        await ctx.send(embed=embed)
        return

    voice_channel = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    urls = extract_urls(query)

    if len(urls) > 1:
        loading_embed = cute_embed("กำลังเตรียมข้อมูล", f"กำลังโหลดเพลงทั้งหมด **{len(urls)} รายการ** รอสักครู่น้า... 🌸", THEME_COLOR, "🔎")
        status_message = await ctx.send(embed=loading_embed)

        added_songs = []
        failed_urls = []

        for index, url in enumerate(urls, start=1):
            try:
                info = await get_youtube(url)
                if not info:
                    failed_urls.append(url)
                    continue
                song = song_from_info(info)
                added_songs.append(song)
            except Exception:
                failed_urls.append(url)

        if not added_songs:
            err_embed = cute_embed("ผิดพลาด", "ไม่สามารถดึงข้อมูลเพลงจากลิงก์ที่ส่งมาได้เลยน้า 🥺", ERROR_COLOR, "❌")
            await status_message.edit(embed=err_embed)
            return

        successfully_added = 0
        for song in added_songs:
            try:
                await music.add_song(ctx.guild, voice_client, song, ctx.channel)
                successfully_added += 1
            except Exception:
                pass

        queued_count, remaining = music.get_queue_summary(ctx.guild.id)
        desc = (
            f"📥 เพิ่มเพลงเข้าคิวเรียบร้อย **{successfully_added} เพลง**\n\n"
            f"🎵 เพลงในคิวทั้งหมด: **{queued_count} เพลง**\n"
            f"⏱️ เวลารวมที่เหลือ: **{format_duration(remaining)}**"
        )
        if failed_urls:
            desc += f"\n\n⚠️ ไม่สามารถโหลดได้ **{len(failed_urls)} รายการ**"

        result_embed = cute_embed("เพิ่มเข้าคิวสำเร็จ", desc, SUCCESS_COLOR, "✨")
        await status_message.edit(embed=result_embed, view=MusicControlView(music))
        return

    loading_embed = cute_embed("กำลังค้นหา", "กำลังค้นหาเพลงให้อยู่น้า รอแป๊บนึงจ้า... ✨", THEME_COLOR, "🔎")
    status_message = await ctx.send(embed=loading_embed)

    try:
        if urls:
            info = await get_youtube(urls[0])
        else:
            info = await search_youtube(query)
    except Exception as error:
        err_embed = cute_embed("ผิดพลาด", f"เกิดข้อผิดพลาดขณะค้นหาเพลงน้า: `{error}`", ERROR_COLOR, "❌")
        await status_message.edit(embed=err_embed)
        return

    if not info:
        err_embed = cute_embed("ไม่พบเพลง", "หาเพลงตามที่ระบุไม่เจอเลยน้า ลองค้นหาใหม่อีกทีจ้า 🥺", ERROR_COLOR, "❌")
        await status_message.edit(embed=err_embed)
        return

    song = song_from_info(info)

    try:
        await music.add_song(ctx.guild, voice_client, song, ctx.channel)
    except Exception as error:
        err_embed = cute_embed("ผิดพลาด", f"เพิ่มเพลงไม่สำเร็จน้า: `{error}`", ERROR_COLOR, "❌")
        await status_message.edit(embed=err_embed)
        return

    queued_count, remaining = music.get_queue_summary(ctx.guild.id)
    desc = (
        f"🎶 **[{song.title}]({song.webpage_url})**\n"
        f"🎤 **ศิลปิน:** {song.artist}\n\n"
        f"🍡 เพลงในคิวทั้งหมด: **{queued_count} เพลง**\n"
        f"⏱️ เวลารวมที่เหลือ: **{format_duration(remaining)}**"
    )

    result_embed = cute_embed("เพิ่มเข้าคิวเรียบร้อย", desc, SUCCESS_COLOR, "📥")
    if song.thumbnail:
        result_embed.set_thumbnail(url=song.thumbnail)

    await status_message.edit(embed=result_embed, view=MusicControlView(music))


@bot.command(name="panel", aliases=["controls"])
async def music_panel(ctx):
    embed = cute_embed(
        "แผงควบคุมเล่นเพลง",
        "กดปุ่มด้านล่างเพื่อควบคุมการเล่นเพลงได้เลยจ้า ✨ 💖",
        THEME_COLOR,
        "🎵"
    )
    await ctx.send(embed=embed, view=MusicControlView(music))


@bot.command(name="queue", aliases=["q"])
async def queue_command(ctx):
    embed = build_queue_embed(ctx.guild.id)
    await ctx.send(embed=embed, view=MusicControlView(music))


@bot.command(name="setlog")
@commands.has_guild_permissions(manage_guild=True)
async def setlog(ctx):
    if not ctx.guild:
        return

    channel = ctx.channel
    voice_monitor.set_log_channel(ctx.guild.id, channel.id)

    embed = cute_embed(
        "ตั้งค่า Voice Log สำเร็จ",
        f"📍 ช่องที่จะใช้รายงาน: {channel.mention}\n\n"
        f"Momo จะคอยแจ้งเตือนเวลามีคน **เข้า / ออก / ย้าย** ห้องเสียงที่นี่น้า ✨",
        SUCCESS_COLOR,
        "📡"
    )
    await ctx.send(embed=embed)


@bot.command()
async def skip(ctx):
    success = await music.skip(ctx.guild)
    if not success:
        embed = cute_embed("แจ้งเตือน", "ตอนนี้ไม่มีเพลงให้ข้ามแล้วน้า ~ 🌸", ERROR_COLOR, "❌")
        await ctx.send(embed=embed)
        return

    embed = cute_embed("ข้ามเพลง", "ข้ามเพลงเรียบร้อยแล้วจ้า ⏭️ ✨", SUCCESS_COLOR, "🌸")
    await ctx.send(embed=embed)


@bot.command()
async def stop(ctx):
    await music.stop(ctx.guild)
    embed = cute_embed("หยุดเพลง", "หยุดเล่นเพลงและล้างรายการคิวหมดแล้วจ้า ⏹️ ✨", ERROR_COLOR, "🌸")
    await ctx.send(embed=embed)


@setlog.error
async def setlog_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = cute_embed("ไม่มีสิทธิ์ใช้งาน", "คำสั่งนี้ต้องใช้สิทธิ์ **Manage Server** น้า ~ 🌸", ERROR_COLOR, "❌")
        await ctx.send(embed=embed)


# =========================
# Start Bot
# =========================

bot.run(TOKEN)
