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

# Проверка критических переменных
if not DISCORD_TOKEN:
    logger.critical("❌ DISCORD_TOKEN не установлен!")
    raise ValueError("DISCORD_TOKEN не установлен в переменных окружения")

if not CHANNEL_ID:
    logger.critical("❌ CHANNEL_ID не установлен!")
    raise ValueError("CHANNEL_ID не установлен в переменных окружения")

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

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"🔥 Ошибка в событии {event}: {args} {kwargs}")

# Слэш-команда /ping
@bot.tree.command(name="ping", description="Проверка работоспособности бота")
async def ping(interaction: discord.Interaction):
    try:
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Задержка: {latency}мс",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в команде ping: {e}")

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
        logger.warning("⚠️ Отсутствует подпись или секрет")
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
        logger.info(f"📢 Уведомление отправлено в канал {CHANNEL_ID}")
        
    except discord.Forbidden:
        logger.error("⛔ Нет прав для отправки сообщений в канал")
    except discord.HTTPException as e:
        logger.error(f"🌐 Ошибка сети: {e.status} {e.text}")
    except Exception as e:
        logger.exception("❌ Неизвестная ошибка при отправке уведомления")

def run_bot():
    """Запуск Discord бота"""
    logger.info("🚀 Запуск Discord бота...")
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.critical("🔑 Ошибка аутентификации: Неверный токен Discord")
    except discord.PrivilegedIntentsRequired:
        logger.critical("🛡️ Требуются привилегированные интенты. Включите их в разработческом портале Discord")
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка при запуске бота: {e}")

def run_flask():
    """Запуск Flask сервера"""
    logger.info(f"🌐 Запуск веб-сервера на порту {PORT}")
    try:
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    except OSError as e:
        logger.critical(f"🔌 Ошибка порта {PORT}: {e}")
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка веб-сервера: {e}")

if __name__ == "__main__":
    logger.info("="*50)
    logger.info("🌟 Запуск приложения VexeraDubbing Bot")
    logger.info("="*50)
    
    # Проверка токена перед запуском
    logger.info(f"🔒 Используется токен: {DISCORD_TOKEN[:10]}...")
    
    # Запуск Discord бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, name="DiscordBot")
    bot_thread.daemon = True
    bot_thread.start()
    
    # Даем боту время на подключение
    import time
    time.sleep(5)
    
    # Запуск Flask сервера в основном потоке
    if bot_thread.is_alive():
        run_flask()
    else:
        logger.critical("❌ Discord бот не запустился. Веб-сервер не запущен.")
