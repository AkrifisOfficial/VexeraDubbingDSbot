import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, request, jsonify
import hmac
import hashlib
import asyncio
import threading
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('VexeraBot')

# Конфигурация
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET')
PORT = int(os.getenv('PORT', 8000))

# Инициализация приложений
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
    logger.info(f'✅ Бот {bot.user} успешно запущен!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="за релизами VexeraDubbing"
    ))
    
    # Синхронизация команд
    try:
        synced = await bot.tree.sync()
        logger.info(f"🔄 Синхронизировано {len(synced)} команд")
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации команд: {e}")

# Слэш-команда /ping
@bot.tree.command(name="ping", description="Проверка работоспособности бота")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"🏓 Pong! Задержка: {latency}мс",
        ephemeral=True
    )

# Вебхук для GitHub
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
            if data['action'] == 'published':
                release = data['release']
                asyncio.run_coroutine_threadsafe(
                    send_release_notification(release), 
                    bot.loop
                )
                logger.info(f"🚀 Уведомление о релизе: {release['tag_name']}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.exception(f"🔥 Ошибка обработки вебхука")
        return jsonify({"status": "error"}), 500

def verify_signature(payload, signature, secret):
    """Проверка подписи HMAC SHA256"""
    if not signature or not secret:
        return False
        
    # Генерация ожидаемой подписи
    digest = hmac.new(
        secret.encode('utf-8'), 
        payload, 
        hashlib.sha256
    ).hexdigest()
    
    expected_signature = f"sha256={digest}"
    
    # Сравнение подписей
    return hmac.compare_digest(expected_signature, signature)

async def send_release_notification(release):
    """Отправка уведомления в Discord"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            logger.error(f"❌ Канал с ID {CHANNEL_ID} не найден")
            return

        # Форматирование описания
        description = release.get('body', 'Новая серия доступна!')
        if len(description) > 500:
            description = description[:500] + "..."

        # Создание embed
        embed = discord.Embed(
            title=f"🎬 {release.get('name', 'Новый релиз')}",
            url=release.get('html_url', ''),
            description=description,
            color=0x6A0DAD  # Фиолетовый цвет
        )
        embed.add_field(
            name="Версия", 
            value=release.get('tag_name', 'v1.0.0')
        )
        embed.set_footer(text="VexeraDubbing")
        
        await channel.send(
            content="@everyone Новая серия готова к просмотру! 🎉",
            embed=embed
        )
        
    except Exception as e:
        logger.exception("❌ Ошибка отправки уведомления")

def run_bot():
    """Запуск Discord бота"""
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.exception("🔥 Критическая ошибка бота")

def run_flask():
    """Запуск Flask сервера"""
    try:
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    except Exception as e:
        logger.exception("🔥 Ошибка запуска Flask сервера")

if __name__ == "__main__":
    # Настройка логирования в файл
    file_handler = logging.FileHandler('bot.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    logger.info("🚀 Запуск приложения...")
    
    # Запуск Discord бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запуск Flask сервера в основном потоке
    run_flask()
