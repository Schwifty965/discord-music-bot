import os
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp
from google import genai
import static_ffmpeg

# โหลด FFmpeg แบบพกพาสำหรับ Render (ป้องกันปัญหาเล่นเพลงแล้วไม่มีเสียงหรือ Error FFmpeg)
static_ffmpeg.add_paths()

# โหลด Environment Variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env or Environment Variables")

# ---------------------------------------------------------
# 1. Web Server สำหรับตอบ Health Check ของ Render (แก้ปัญหา No open ports detected)
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot is running smoothly on Render!")

    def log_message(self, format, *args):
        return  # ปิด Log ของ HTTP Server ไม่ให้รกหน้าจอ

def run_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"[HealthCheck] Web Server started on port {port}")
    server.serve_forever()

# รัน HTTP Server แยกใน Background Thread ทันทีที่รันไฟล์นี้
threading.Thread(target=run_health_check_server, daemon=True).start()

# ---------------------------------------------------------
# 2. ตั้งค่า Discord Bot & Gemini API
# ---------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# ตั้งให้รองรับทั้ง Prefix 'mo!' และ '!'
bot = commands.Bot(command_prefix=["mo!", "!"], intents=intents)

gemini_client = None
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[Gemini] API Client initialized successfully.")
    except Exception as e:
        print(f"[Gemini] Initialization error: {e}")

# ---------------------------------------------------------
# 3. ตั้งค่าระบบเพลง (yt-dlp & FFmpeg & Cookies)
# ---------------------------------------------------------
# ดึง Cookie จาก Environment Variable มาสร้างไฟล์ cookies.txt อัตโนมัติ
yt_cookies = os.getenv("YOUTUBE_COOKIES")
if yt_cookies:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(yt_cookies)
    print("[YouTube] Loaded cookies.txt successfully.")

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractflat': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt' if os.path.exists("cookies.txt") else None,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# ---------------------------------------------------------
# 4. อีเวนต์และคำสั่งของบอต
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print(f"[Bot] Logged in as {bot.user.name} ({bot.user.id})")
    print("[Bot] Ready for Render deployment!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

@bot.command(name="join", aliases=["j"], help="ดึงบอตเข้าห้องเสียง")
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ คุณต้องอยู่ในห้องเสียง (Voice Channel) ก่อนครับ!")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
        await ctx.send(f"🔊 เข้าห้อง **{channel.name}** เรียบร้อยครับ!")
    else:
        await ctx.voice_client.move_to(channel)
        await ctx.send(f"🔊 ย้ายมาห้อง **{channel.name}** เรียบร้อยครับ!")

@bot.command(name="play", aliases=["p"], help="สั่งเล่นเพลงจาก YouTube")
async def play(ctx, *, url: str):
    if not ctx.author.voice:
        await ctx.send("❌ คุณต้องอยู่ในห้องเสียง (Voice Channel) ก่อนครับ!")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f"Finished playing: {e}") if e else None)
            await ctx.send(f"🎵 กำลังเล่น: **{player.title}**")
        except Exception as e:
            await ctx.send(f"❌ เกิดข้อผิดพลาดในการดึงเพลง: {e}")

@bot.command(name="pause", help="หยุดเพลงชั่วคราว")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ พักการเล่นเพลงชั่วคราว")

@bot.command(name="resume", help="เล่นเพลงต่อ")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.resume()
        await ctx.send("▶️ เล่นเพลงต่อ")

@bot.command(name="stop", aliases=["leave"], help="หยุดเล่นและออกจากห้องเสียง")
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ หยุดเล่นและออกจากห้องเสียงเรียบร้อยครับ")

@bot.command(name="chat", help="คุยกับ Gemini AI")
async def chat(ctx, *, prompt: str):
    if not gemini_client:
        await ctx.send("❌ ยังไม่ได้ตั้งค่า GEMINI_API_KEY ครับ")
        return

    async with ctx.typing():
        try:
            response = gemini_client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            await ctx.send(response.text)
        except Exception as e:
            await ctx.send(f"❌ Gemini Error: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
