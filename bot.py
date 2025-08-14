import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask, request, jsonify
import hmac
import hashlib
import asyncio

# Конфигурация
DISCORD_TOKEN = os.getenv('MTQwNTU3OTQzNjQ0NjcxNjA2NQ.GzIIiZ.6SOxH-SrIpO5Ro-dGfWwtlpd4icw6vpwMv2PJQ')
CHANNEL_ID = int(os.getenv('1382970034904629392'))
GITHUB_WEBHOOK_SECRET = os.getenv('9185b27dd2072940301feea9fdc72630')
PORT = int(os.getenv('PORT', 5000))

# Инициализация приложений
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = Flask(__name__)

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="за релизами VexeraDubbing"
    ))
    
    # Синхронизация команд
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации команд: {e}")

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
            print("❌ Неверная подпись вебхука")
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
                print(f"🚀 Уведомление о релизе: {release['tag_name']}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"🔥 Ошибка обработки вебхука: {e}")
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
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"❌ Канал с ID {CHANNEL_ID} не найден")
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
    
    # Опционально: добавление превью
    if 'assets' in release and release['assets']:
        first_asset = release['assets'][0]
        if first_asset['content_type'].startswith('image/'):
            embed.set_thumbnail(url=first_asset['browser_download_url'])
    
    embed.set_footer(
        text="VexeraDubbing",
        icon_url="https://s.iimg.su/s/14/gpoeAFfxQzTomz8sVJov06CIg7aoGPgAm6u2BzjA.jpg"  # Замените на URL вашего лого
    )
    
    await channel.send(
        content="@everyone Новая серия готова к просмотру! 🎉",
        embed=embed
    )

def run_bot():
    """Запуск Discord бота"""
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    import threading
    
    # Запуск Discord бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запуск Flask сервера
    app.run(host='0.0.0.0', port=PORT, use_reloader=False)
