import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, request, jsonify
import hmac
import hashlib
import asyncio
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger('VexeraBot')

# Конфигурация
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET')
PORT = int(os.getenv('PORT', 8000))

# Проверка переменных
if not DISCORD_TOKEN:
    logger.critical("❌ DISCORD_TOKEN не установлен!")
    raise ValueError("Токен бота не установлен")

if not CHANNEL_ID:
    logger.critical("❌ CHANNEL_ID не установлен!")
    raise ValueError("ID канала не установлен")

# Инициализация
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='!', 
    intents=intents,
    help_command=None
)

app = Flask(__name__)

@bot.event
async def on_ready():
    logger.info(f'✅ Бот {bot.user} запущен!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="за релизами VexeraDubbing"
    ))
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"🔄 Синхронизировано команд: {len(synced)}")
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации: {e}")

# Проверка прав администратора
def is_admin(interaction: discord.Interaction) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return interaction.user.guild_permissions.administrator

# Команда проверки
@bot.tree.command(name="ping", description="Проверка работы бота")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"🏓 Pong! Задержка: {latency}мс",
        ephemeral=True
    )

# Тестовая отправка (только для админов)
@bot.tree.command(name="test_send", description="Тест отправки сообщения (только админы)")
@app_commands.check(is_admin)
async def test_send(interaction: discord.Interaction):
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
            return
        
        await channel.send("✅ Тестовое сообщение от бота!")
        await interaction.response.send_message("Сообщение отправлено!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка: {str(e)}", ephemeral=True)

# Ручная отправка (только для админов)
@bot.tree.command(name="announce", description="Отправить сообщение в канал (только админы)")
@app_commands.check(is_admin)
async def announce(interaction: discord.Interaction, message: str):
    try:
        channel = bot.get_channel(CHANNEL_ID)
        await channel.send(message)
        await interaction.response.send_message("✅ Сообщение отправлено!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

# Обработка ошибок для команд админов
@test_send.error
@announce.error
async def admin_commands_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ Эта команда доступна только администраторам сервера!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"⚠️ Произошла ошибка: {str(error)}",
            ephemeral=True
        )

# Обработка GitHub вебхука
@app.route('/webhook', methods=['POST'])
def github_webhook():
    try:
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = request.data
        
        if not verify_signature(payload, signature, GITHUB_WEBHOOK_SECRET):
            logger.error("❌ Неверная подпись вебхука")
            return jsonify({"status": "invalid signature"}), 401

        event = request.headers.get('X-GitHub-Event')
        if event == 'release':
            data = request.json
            if data['action'] == 'published':
                release = data['release']
                asyncio.run_coroutine_threadsafe(
                    send_release_notification(release), 
                    bot.loop
                )
                logger.info(f"🚀 Обработан релиз: {release['tag_name']}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.exception(f"🔥 Ошибка вебхука: {e}")
        return jsonify({"status": "error"}), 500

def verify_signature(payload, signature, secret):
    if not signature or not secret:
        return False
        
    digest = hmac.new(
        secret.encode('utf-8'), 
        payload, 
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={digest}", signature)

async def send_release_notification(release):
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            logger.error(f"❌ Канал {CHANNEL_ID} не найден")
            return

        description = release.get('body', 'Новая серия доступна!')
        if len(description) > 500:
            description = description[:500] + "..."

        embed = discord.Embed(
            title=f"🎬 {release.get('name', 'Новый релиз')}",
            url=release.get('html_url', ''),
            description=description,
            color=0x6A0DAD
        )
        embed.add_field(name="Версия", value=release.get('tag_name', 'v1.0.0'))
        embed.set_footer(text="VexeraDubbing")
        
        await channel.send(
            content="@everyone Новая серия готова! 🎉",
            embed=embed
        )
        logger.info(f"📢 Отправлено в канал {channel.name}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")

def run_bot():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    run_bot()
