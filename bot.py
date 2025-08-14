import os
import discord
from discord.ext import commands
from flask import Flask, request, jsonify
import hmac
import hashlib
import asyncio

# Конфигурация
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET')

# Discord бот
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
app = Flask(__name__)

@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="за релизами"))

@app.route('/webhook', methods=['POST'])
def github_webhook():
    # Проверка подписи
    signature = request.headers.get('X-Hub-Signature-256', '')
    payload = request.data
    if not verify_signature(payload, signature, WEBHOOK_SECRET):
        return jsonify({"status": "invalid signature"}), 401

    # Обработка релиза
    if request.headers.get('X-GitHub-Event') == 'release':
        data = request.json
        if data['action'] == 'published':
            release = data['release']
            asyncio.run_coroutine_threadsafe(
                send_notification(release), 
                bot.loop
            )
    return jsonify({"status": "success"}), 200

def verify_signature(payload, signature, secret):
    if not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

async def send_notification(release):
    channel = bot.get_channel(CHANNEL_ID)
    embed = discord.Embed(
        title=f"🎬 {release['name']}",
        url=release['html_url'],
        description=release['body'][:500] + "..." if release['body'] else "Новая серия!",
        color=0x6A0DAD
    )
    embed.add_field(name="Версия", value=release['tag_name'])
    embed.set_footer(text="VexeraDubbing")
    await channel.send(f"@everyone Новая серия готова к просмотру!", embed=embed)

def run_bot():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    import threading
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
