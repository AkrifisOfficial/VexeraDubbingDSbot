import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, request, jsonify
import hmac
import hashlib
import asyncio
import logging
import threading
import sys

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
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))  # ID роли администратора

# Проверка переменных
if not DISCORD_TOKEN:
    logger.critical("❌ DISCORD_TOKEN не установлен!")
    sys.exit(1)

if not CHANNEL_ID:
    logger.critical("❌ CHANNEL_ID не установлен!")
    sys.exit(1)

logger.info(f"⚙️ Настройки: CHANNEL_ID={CHANNEL_ID}, ADMIN_ROLE_ID={ADMIN_ROLE_ID}")

# Инициализация
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Для проверки прав пользователей

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
        logger.error(f"❌ Ошибка синхронизации команд: {e}")

# Проверка прав администратора
def is_admin(interaction: discord.Interaction) -> bool:
    """Проверяет, является ли пользователь администратором"""
    # 1. Права администратора сервера
    if interaction.user.guild_permissions.administrator:
        return True
    
    # 2. Специальная роль администратора
    if ADMIN_ROLE_ID:
        role = discord.utils.get(interaction.user.roles, id=ADMIN_ROLE_ID)
        if role:
            return True
    
    return False

# Команда проверки (доступна всем)
@bot.tree.command(name="ping", description="Проверка работы бота")
async def ping(interaction: discord.Interaction):
    try:
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Задержка: {latency}мс",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Ошибка в команде ping: {e}")

# Команда проверки прав (только для админов)
@bot.tree.command(name="check_admin", description="Проверка прав администратора")
@app_commands.check(is_admin)
async def check_admin(interaction: discord.Interaction):
    try:
        await interaction.response.send_message(
            "✅ У вас есть права администратора!",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Ошибка в команде check_admin: {e}")

# Тестовая отправка (только для админов)
@bot.tree.command(name="test_send", description="Тест отправки сообщения (только админы)")
@app_commands.check(is_admin)
async def test_send(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            await interaction.followup.send("❌ Канал не найден!", ephemeral=True)
            return
        
        await channel.send("✅ Тестовое сообщение от бота!")
        await interaction.followup.send("✅ Сообщение отправлено!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("⛔ Нет прав для отправки сообщений в канал!", ephemeral=True)
    except Exception as e:
        logger.error(f"Ошибка в test_send: {e}")
        await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

# Ручная отправка (только для админов)
@bot.tree.command(name="announce", description="Отправить сообщение в канал (только админы)")
@app_commands.check(is_admin)
async def announce(interaction: discord.Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            await interaction.followup.send("❌ Канал не найден!", ephemeral=True)
            return
        
        # Проверка на пустое сообщение
        if not message.strip():
            await interaction.followup.send("❌ Сообщение не может быть пустым!", ephemeral=True)
            return
        
        # Проверка на слишком длинное сообщение
        if len(message) > 2000:
            await interaction.followup.send("❌ Сообщение слишком длинное (макс. 2000 символов)!", ephemeral=True)
            return
        
        await channel.send(message)
        await interaction.followup.send("✅ Сообщение отправлено!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("⛔ Нет прав для отправки сообщений в канал!", ephemeral=True)
    except Exception as e:
        logger.error(f"Ошибка в announce: {e}")
        await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

# Глобальный обработчик ошибок для команд админов
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ Эта команда доступна только администраторам сервера!",
            ephemeral=True
        )
    else:
        logger.error(f"Ошибка команды: {error}")
        await interaction.response.send_message(
            f"⚠️ Произошла ошибка при выполнении команды: {str(error)}",
            ephemeral=True
        )

# Обработка GitHub вебхука
@app.route('/webhook', methods=['POST'])
def github_webhook():
    try:
        # Проверка подписи
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = request.data
        
        if not verify_signature(payload, signature, GITHUB_WEBHOOK_SECRET):
            logger.error("❌ Неверная подпись вебхука")
            return jsonify({"status": "invalid signature"}), 401

        # Обработка релиза
        event = request.headers.get('X-GitHub-Event')
        if event == 'release':
            data = request.json
            if data.get('action') == 'published':
                release = data.get('release', {})
                asyncio.run_coroutine_threadsafe(
                    send_release_notification(release), 
                    bot.loop
                )
                logger.info(f"🚀 Обработан релиз: {release.get('tag_name', 'unknown')}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.exception(f"🔥 Ошибка вебхука: {e}")
        return jsonify({"status": "error"}), 500

def verify_signature(payload, signature, secret):
    """Проверяет подпись HMAC-SHA256 вебхука"""
    if not signature or not secret:
        return False
        
    try:
        digest = hmac.new(
            secret.encode('utf-8'), 
            payload, 
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={digest}", signature)
    except Exception:
        return False

async def send_release_notification(release):
    """Отправляет уведомление о новом релизе в Discord"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            logger.error(f"❌ Канал {CHANNEL_ID} не найден")
            return

        # Извлекаем данные релиза
        title = release.get('name', 'Новый релиз')
        version = release.get('tag_name', 'v1.0.0')
        url = release.get('html_url', '')
        body = release.get('body', 'Новая серия доступна!')
        
        # Форматируем описание
        description = body[:497] + "..." if len(body) > 500 else body

        # Создаём embed
        embed = discord.Embed(
            title=f"🎬 {title}",
            url=url,
            description=description,
            color=0x6A0DAD
        )
        embed.add_field(name="Версия", value=version)
        embed.set_footer(text="VexeraDubbing")
        
        # Отправляем сообщение
        await channel.send(content="@everyone Новая серия готова! 🎉", embed=embed)
        logger.info(f"📢 Отправлено уведомление в канал {channel.name}")
        
    except discord.Forbidden:
        logger.error("⛔ Нет прав для отправки сообщений в канал")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

def run_flask():
    """Запускает Flask сервер"""
    try:
        logger.info(f"🌐 Запуск веб-сервера на порту {PORT}")
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    except Exception as e:
        logger.critical(f"🔥 Ошибка запуска Flask: {e}")

def run_bot():
    """Запускает Discord бота"""
    try:
        logger.info("🤖 Запуск Discord бота...")
        bot.run(DISCORD_TOKEN)
    except discord.LoginError:
        logger.critical("🔑 Ошибка аутентификации: неверный токен")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка бота: {e}")

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    run_bot()
