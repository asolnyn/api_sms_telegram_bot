import os
import requests
import datetime
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ----------------- Config -----------------
OWNER_ID = your_telegram_id  # your Telegram ID
ALLOWED_USERS = {OWNER_ID: "owners name"}  # dictionary: {user_id: name}
MAX_HISTORY = 50  # max SMS history per user
TIMEZONE_OFFSET = 6  # Bangladesh = UTC+6

# Tokens & API
BOT_TOKEN = os.getenv("BOT_TOKEN") or "your_bot_token"
API_KEY = os.getenv("API_KEY") or "your_api_key"
CLIENT_ID = os.getenv("CLIENT_ID") or "your_client_id"
SENDER_ID = os.getenv("SENDER_ID") or "your_sender_id"
API_SEND_URL = os.getenv("API_SEND_URL") or "https://api.smsq.global/api/v2/SendSMS"
API_BALANCE_URL = f"https://api.smsq.global/api/v2/Balance?ApiKey={API_KEY}&ClientId={CLIENT_ID}"

# ----------------- History & Scheduled Tasks -----------------
sms_history = {}         # {user_id: [ {numbers, message, status, message_id, time, type, sms_count}, ... ] }
scheduled_tasks = {}     # {user_id: [ {numbers, message, send_time, task}, ... ] }

# ----------------- Cooldown & ON/OFF -----------------
last_command_time = {}   # {user_id: timestamp}
USER_COOLDOWN = 5       # 5 seconds cooldown for non-admin users
BOT_ON_FOR_USERS = True  # ON/OFF switch for other users

# ----------------- Helper Functions -----------------
def get_sms_type_and_count(message):
    """Determine SMS type (GSM/Unicode) and count."""
    try:
        message.encode('gsm0338')
        sms_type = "GSM"
        sms_count = (len(message) + 159) // 160
    except:
        sms_type = "Unicode"
        sms_count = (len(message) + 69) // 70
    return sms_type, sms_count

async def send_sms_api(numbers_str, message):
    """Send SMS via API and return response JSON."""
    params = {
        "ApiKey": API_KEY,
        "ClientId": CLIENT_ID,
        "SenderId": SENDER_ID,
        "Message": message,
        "MobileNumbers": numbers_str
    }
    response = requests.get(API_SEND_URL, params=params)
    return response.json()

async def save_history(user_id, numbers, message, data_list):
    """Save SMS info to history and format output."""
    now = (datetime.datetime.utcnow() + datetime.timedelta(hours=TIMEZONE_OFFSET)).strftime("%Y-%m-%d %H:%M")
    sms_type, sms_count = get_sms_type_and_count(message)
    info_text = ""
    for d in data_list:
        status = "✅ Success" if d.get("MessageErrorCode") == 0 else "❌ Failed"
        number = d.get("MobileNumber")
        msg_id = d.get("MessageId")
        info_text += (
            f"{status}\n"
            f"📱 Number: {number}\n"
            f"🆔 MessageId: {msg_id}\n"
            f"📝 Message: {message}\n"
            f"⏱ Time: {now}\n"
            f"💠 Type: {sms_type}\n"
            f"✉️ SMS Count: {sms_count}\n\n"
        )
        sms_history.setdefault(user_id, []).append({
            "numbers": number,
            "message": message,
            "status": "Sent" if d.get("MessageErrorCode") == 0 else "Failed",
            "message_id": msg_id,
            "time": now,
            "type": sms_type,
            "sms_count": sms_count
        })
        if len(sms_history[user_id]) > MAX_HISTORY:
            sms_history[user_id] = sms_history[user_id][-MAX_HISTORY:]
    return info_text

def is_allowed(user_id):
    return user_id in ALLOWED_USERS

def check_cooldown(user_id):
    if user_id == OWNER_ID:
        return True
    now = datetime.datetime.now().timestamp()
    last = last_command_time.get(user_id, 0)
    if now - last < USER_COOLDOWN:
        return False
    last_command_time[user_id] = now
    return True

def bot_allowed(user_id):
    if user_id == OWNER_ID:
        return True
    return BOT_ON_FOR_USERS

# ----------------- Command Functions -----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_allowed(user_id):
        await update.message.reply_text("✅ You are allowed. Type /help to see commands.")
    else:
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = (
        "📋 Available Commands:\n"
        "/myid - Show your Telegram ID\n"
        "/balance - Check SMS credits\n"
        "/history - Show last SMS history\n"
        "/schedule <numbers> <YYYY-MM-DD> <HH:MM> <message> - Schedule SMS\n"
        "/list_tasks - List scheduled SMS\n"
        "/cancel_schedule - Cancel all scheduled SMS\n"
        "/cancel_task <n> - Cancel specific scheduled SMS\n"
        "/sender_id - Show current sender ID\n"
    )
    if user_id == OWNER_ID:
        msg += (
            "\n🔒 Admin Commands:\n"
            "/add_user <id> <name> - Add allowed user\n"
            "/remove_user <id> - Remove allowed user\n"
            "/list_users - List all allowed users\n"
            "/on - Turn bot ON for users\n"
            "/off - Turn bot OFF for users\n"
        )
    await update.message.reply_text(msg)

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: {update.message.from_user.id}")

async def show_sender_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    await update.message.reply_text(f"Sender ID: {SENDER_ID}")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can add users.")
        return
    try:
        new_id = int(context.args[0])
        name = context.args[1] if len(context.args) > 1 else f"user{new_id}"
        if new_id in ALLOWED_USERS:
            await update.message.reply_text("❌ User already exists.")
        else:
            ALLOWED_USERS[new_id] = name
            await update.message.reply_text(f"✅ Added user {new_id} ~ {name}")
    except:
        await update.message.reply_text("⚠️ Usage: /add_user <id> <name>")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can remove users.")
        return
    try:
        rem_id = int(context.args[0])
        if rem_id == OWNER_ID or rem_id not in ALLOWED_USERS:
            await update.message.reply_text("❌ Cannot remove owner or non-existing user")
        else:
            ALLOWED_USERS.pop(rem_id)
            await update.message.reply_text(f"✅ Removed user {rem_id}")
    except:
        await update.message.reply_text("⚠️ Usage: /remove_user <id>")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can see user list.")
        return
    msg = "✅ Allowed users:\n"
    for uid, name in ALLOWED_USERS.items():
        msg += f"[{uid}] ~ {name}\n"
    await update.message.reply_text(msg)

# ----------------- SMS Functions -----------------
async def send_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    text = update.message.text.strip()
    try:
        numbers_part, message = text.split(" ", 1)
        numbers = [("880" + n.lstrip("0") if not n.startswith("880") else n) for n in numbers_part.split(",")]
        numbers_str = ",".join(numbers)
        res_json = await send_sms_api(numbers_str, message)
        info_text = await save_history(user_id, numbers_str, message, res_json.get("Data", []))
        await update.message.reply_text(info_text)
    except:
        await update.message.reply_text("⚠️ Use format:\n017XXXXXXXX,018XXXXXXXX Your message")

async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return
    try:
        res = requests.get(API_BALANCE_URL).json()
        if res["ErrorCode"] == 0:
            credits = res["Data"][0]["Credits"]
            await update.message.reply_text(f"💰 SMS Credits: {credits}")
        else:
            await update.message.reply_text("❌ Could not fetch balance")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    history = sms_history.get(user_id, [])
    if not history:
        await update.message.reply_text("📭 No SMS history found.")
        return
    msg = ""
    for h in history[-10:]:
        msg += (
            f"{'✅ Success' if h['status']=='Sent' else '❌ Failed'}\n"
            f"📱 Number: {h['numbers']}\n"
            f"🆔 MessageId: {h['message_id']}\n"
            f"📝 Message: {h['message']}\n"
            f"⏱ Time: {h['time']}\n"
            f"💠 Type: {h['type']}\n"
            f"✉️ SMS Count: {h['sms_count']}\n\n"
        )
    await update.message.reply_text(msg)

# ----------------- Scheduling Functions -----------------
async def scheduled_send(user_id, numbers_str, message):
    res_json = await send_sms_api(numbers_str, message)
    info_text = await save_history(user_id, numbers_str, message, res_json.get("Data", []))
    return info_text

async def schedule_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    try:
        parts = update.message.text.strip().split(" ", 4)
        numbers_part = parts[1]
        date_str = parts[2]
        time_str = parts[3]
        message = parts[4]
        numbers = [("880" + n.lstrip("0") if not n.startswith("880") else n) for n in numbers_part.split(",")]
        numbers_str = ",".join(numbers)

        send_time = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        current_time = datetime.datetime.utcnow() + datetime.timedelta(hours=TIMEZONE_OFFSET)
        delay = (send_time - current_time).total_seconds()

        if delay < 0:
            await update.message.reply_text("❌ Cannot schedule SMS in the past")
            return

        async def task_func():
            try:
                await asyncio.sleep(delay)
                res_text = await scheduled_send(user_id, numbers_str, message)
                await update.message.reply_text(f"✅ Scheduled SMS Sent:\n{res_text}")
            except asyncio.CancelledError:
                await update.message.reply_text(f"❌ Scheduled SMS canceled before sending")

        task = asyncio.create_task(task_func())
        scheduled_tasks.setdefault(user_id, []).append({
            "numbers": numbers_str,
            "message": message,
            "send_time": send_time,
            "task": task
        })
        await update.message.reply_text(f"⏰ Scheduled SMS in {int(delay)} seconds (Bangladesh time)")
    except:
        await update.message.reply_text("⚠️ Usage:\n/schedule 017XXXXXXXX 2026-03-27 10:03 Your message")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    tasks = scheduled_tasks.get(user_id, [])
    if not tasks:
        await update.message.reply_text("📭 No scheduled SMS found")
        return
    msg = ""
    for idx, t in enumerate(tasks, start=1):
        local_time = (t['send_time'] + datetime.timedelta(hours=TIMEZONE_OFFSET)).strftime('%Y-%m-%d %H:%M')
        msg += f"{idx}. 📱 Numbers: {t['numbers']}\n📝 Message: {t['message']}\n⏱ Scheduled at: {local_time}\n\n"
    await update.message.reply_text(msg)

async def cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    tasks = scheduled_tasks.get(user_id, [])
    if not tasks:
        await update.message.reply_text("📭 No scheduled SMS to cancel")
        return
    for t in tasks:
        task_obj = t.get("task")
        if task_obj and not task_obj.done():
            task_obj.cancel()
    scheduled_tasks[user_id] = []
    await update.message.reply_text("❌ All scheduled SMS canceled")

async def cancel_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("❌ You are not allowed. Contact the owner.")
        return
    if not bot_allowed(user_id):
        await update.message.reply_text("⛔ Bot is currently OFF for users.")
        return
    if not check_cooldown(user_id):
        await update.message.reply_text(f"⏱ Wait {USER_COOLDOWN}s between commands")
        return

    tasks = scheduled_tasks.get(user_id, [])
    if not tasks:
        await update.message.reply_text("📭 No scheduled SMS to cancel")
        return
    try:
        idx = int(context.args[0]) - 1
        task_obj = tasks[idx].get("task")
        if task_obj and not task_obj.done():
            task_obj.cancel()
        tasks.pop(idx)
        await update.message.reply_text(f"❌ Scheduled SMS #{idx+1} canceled")
    except:
        await update.message.reply_text("⚠️ Usage: /cancel_task <task_number>")

# ----------------- Admin ON/OFF -----------------
async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    global BOT_ON_FOR_USERS
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this.")
        return
    BOT_ON_FOR_USERS = False
    await update.message.reply_text("⛔ Bot OFF for other users. Only admin can use commands now.")

async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    global BOT_ON_FOR_USERS
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only owner can use this.")
        return
    BOT_ON_FOR_USERS = True
    await update.message.reply_text("✅ Bot ON for other users. They can use commands now.")

# ----------------- Bot Setup -----------------
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set in environment variables")

app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
app.add_handler(CommandHandler("start", start_command))  # ✅ Added /start command
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("myid", get_my_id))
app.add_handler(CommandHandler("sender_id", show_sender_id))
app.add_handler(CommandHandler("balance", check_balance))
app.add_handler(CommandHandler("history", show_history))
app.add_handler(CommandHandler("schedule", schedule_sms))
app.add_handler(CommandHandler("list_tasks", list_tasks))
app.add_handler(CommandHandler("cancel_schedule", cancel_schedule))
app.add_handler(CommandHandler("cancel_task", cancel_task))
app.add_handler(CommandHandler("add_user", add_user))
app.add_handler(CommandHandler("remove_user", remove_user))
app.add_handler(CommandHandler("list_users", list_users))
app.add_handler(CommandHandler("on", bot_on))
app.add_handler(CommandHandler("off", bot_off))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_sms))

print("Bot is running...")
app.run_polling()
