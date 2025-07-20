import sqlite3
import requests
import telebot
from telebot import types

# 👇 Add this below your imports 👇
from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    return "Bot is alive!"


def run():
    app.run(host='0.0.0.0', port=8080)


# Start the web server
Thread(target=run).start()

# --- CONFIGURATION ---
BOT_TOKEN = "8055477611:AAHLLG0yv5Foow_fI_BoKn0zygG9mdOnlmU"
CHANNEL_USERNAME = "@instapanelannouncement"
ADMIN_ID = 5078131670
API_KEY = "c9a938d7f66e000f6d3631f15a322965"
UPI_ID = "mithulxfoxey456@fam"

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

# In-memory store for pending admin actions
pending_actions = {}

# === DATABASE SETUP ===
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    referred_by INTEGER
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    smm_id TEXT,
    price REAL
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS pending_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    txn_id TEXT
)
""")
conn.commit()


# === SETTINGS FUNCTIONS ===
def get_setting(key, default=None):
    cur.execute("SELECT value FROM settings WHERE key = ?", (key, ))
    row = cur.fetchone()
    return row[0] if row else default


def set_setting(key, value):
    cur.execute("REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value))
    conn.commit()


# Initialize defaults
if get_setting("referral_system") is None:
    set_setting("referral_system", "on")
if get_setting("referral_limit") is None:
    set_setting("referral_limit", "5")


# === HELPER FUNCTIONS ===
def is_user_in_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False


def send_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Balance", "➕ Add Funds")
    markup.row("🛒 Buy Services", "📢 Referral Link")
    markup.row("📖 Help")
    if user_id == ADMIN_ID:
        markup.row("/adminpanel")
    bot.send_message(user_id,
                     "👋 Welcome to Insta SMM Bot!",
                     reply_markup=markup)


# === COMMANDS ===
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    if not is_user_in_channel(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        markup.add(
            types.InlineKeyboardButton("✅ I Joined",
                                       callback_data="check_joined"))
        bot.send_message(
            user_id,
            "🚫 Please join the channel to use the bot: then send /start",
            reply_markup=markup)
        return

    cur.execute("SELECT id FROM users WHERE id = ?", (user_id, ))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (id, referred_by) VALUES (?, ?)",
                    (user_id, ref))
        if ref and get_setting("referral_system") == "on":
            cur.execute("SELECT referrals FROM users WHERE id = ?", (ref, ))
            row = cur.fetchone()
            if row and row[0] < int(get_setting("referral_limit")):
                cur.execute(
                    "UPDATE users SET referrals = referrals + 1, balance = balance + 1 WHERE id = ?",
                    (ref, ))
        conn.commit()

    send_main_menu(user_id)


@bot.callback_query_handler(func=lambda c: c.data == "check_joined")
def handle_joined(c):
    uid = c.from_user.id
    if is_user_in_channel(uid):
        bot.answer_callback_query(c.id, "✅ Verified!")
        send_main_menu(uid)
    else:
        bot.answer_callback_query(c.id, "❌ Not joined yet.")


@bot.message_handler(func=lambda m: m.text == "📖 Help")
def handle_help(m):
    bot.send_message(m.chat.id, "ℹ️ Need help? Contact @flipperxd.")


@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def handle_balance(m):
    cur.execute("SELECT balance FROM users WHERE id = ?", (m.chat.id, ))
    row = cur.fetchone()
    bal = row[0] if row else 0
    bot.send_message(m.chat.id, f"💸 Your balance: ₹{bal:.2f}")


@bot.message_handler(func=lambda m: m.text == "➕ Add Funds")
def handle_add_funds(m):
    bot.send_message(m.chat.id,
                     f"💳 Send payment to UPI: `{UPI_ID}`",
                     parse_mode="Markdown")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ I Paid", callback_data="paid"))
    bot.send_message(m.chat.id, "Tap when done.", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "paid")
def handle_paid(c):
    msg = bot.send_message(c.chat.id, "Enter amount paid:")
    bot.register_next_step_handler(msg, process_amount)


def process_amount(m):
    if not m.text.replace('.', '', 1).isdigit():
        bot.send_message(m.chat.id, "❌ Invalid number.")
        return
    amount = float(m.text)
    msg = bot.send_message(m.chat.id, "Enter transaction ID:")
    bot.register_next_step_handler(msg, process_txn, amount)


def process_txn(m, amount):
    txn = m.text.strip()
    uid = m.chat.id
    cur.execute(
        "INSERT INTO pending_payments (user_id, amount, txn_id) VALUES (?, ?, ?)",
        (uid, amount, txn))
    conn.commit()

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Approve",
                                   callback_data=f"approve_{uid}_{txn}"))
    markup.add(
        types.InlineKeyboardButton("❌ Reject",
                                   callback_data=f"reject_{uid}_{txn}"))
    bot.send_message(
        ADMIN_ID,
        f"💰 Payment Request\nUser: {uid}\nAmount: ₹{amount:.2f}\nTxn: {txn}",
        reply_markup=markup)
    bot.send_message(
        uid, "✅ Payment request sent. Please wait for admin approval.")


@bot.callback_query_handler(
    func=lambda c: c.data.startswith(("approve_", "reject_")))
def handle_payment_resp(c):
    action, uid_str, txn = c.data.split("_", 2)
    uid = int(uid_str)
    cur.execute(
        "SELECT amount FROM pending_payments WHERE user_id = ? AND txn_id = ?",
        (uid, txn))
    row = cur.fetchone()
    if not row:
        bot.answer_callback_query(c.id, "❌ Not found.")
        return

    amount = row[0]
    if action == "approve":
        cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?",
                    (amount, uid))
        bot.send_message(
            uid, f"✅ Your payment of ₹{amount:.2f} has been approved.")
    else:
        bot.send_message(uid, f"❌ Your payment of ₹{amount:.2f} was rejected.")

    cur.execute(
        "DELETE FROM pending_payments WHERE user_id = ? AND txn_id = ?",
        (uid, txn))
    conn.commit()
    bot.answer_callback_query(c.id, "Handled.")


@bot.message_handler(func=lambda m: m.text == "📢 Referral Link")
def handle_referral(m):
    uid = m.chat.id
    cur.execute("SELECT referrals FROM users WHERE id = ?", (uid, ))
    row = cur.fetchone()
    count = row[0] if row else 0
    bot.send_message(
        uid,
        f"🔗 https://t.me/{bot.get_me().username}?start={uid}\nReferrals: {count}"
    )


# === ADMIN PANEL ===
@bot.message_handler(commands=['adminpanel'])
def handle_admin(m):
    if m.chat.id != ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔁 Toggle Referral", "🔢 Set Referral Limit")
    markup.row("✏️ Edit Balance", "📊 Check Balance")
    markup.row("➕ Add Service", "❌ Delete Service")
    markup.row("📣 Announce", "🔙 Back")
    bot.send_message(m.chat.id, "🛠 Admin Panel", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "🔙 Back")
def handle_back(m):
    if m.chat.id == ADMIN_ID:
        handle_admin(m)
    else:
        send_main_menu(m.chat.id)


@bot.message_handler(func=lambda m: m.text == "🔁 Toggle Referral")
def toggle_ref(m):
    if m.chat.id != ADMIN_ID: return
    curr = get_setting("referral_system")
    nxt = "off" if curr == "on" else "on"
    set_setting("referral_system", nxt)
    bot.send_message(m.chat.id, f"Referral system is now: {nxt}")


@bot.message_handler(func=lambda m: m.text == "🔢 Set Referral Limit")
def set_ref_limit(m):
    if m.chat.id != ADMIN_ID: return
    msg = bot.send_message(
        m.chat.id,
        f"Current limit: {get_setting('referral_limit')}. Enter new limit:")
    bot.register_next_step_handler(msg, process_ref_limit)


def process_ref_limit(m):
    if m.chat.id != ADMIN_ID: return
    if not m.text.isdigit():
        bot.send_message(m.chat.id, "❌ Invalid number.")
        return
    set_setting("referral_limit", m.text)
    bot.send_message(m.chat.id, f"✅ Referral limit updated to {m.text}.")


@bot.message_handler(func=lambda m: m.text == "📣 Announce")
def announce_prompt(m):
    if m.chat.id != ADMIN_ID: return
    msg = bot.send_message(m.chat.id, "Enter announcement message:")
    bot.register_next_step_handler(msg, broadcast_all)


def broadcast_all(m):
    if m.chat.id != ADMIN_ID: return
    cur.execute("SELECT id FROM users")
    for (uid, ) in cur.fetchall():
        try:
            bot.send_message(uid, f"📢 Announcement:\n{m.text}")
        except:
            pass
    bot.send_message(m.chat.id, "✅ Broadcast sent.")


@bot.message_handler(func=lambda m: m.text == "📊 Check Balance")
def check_bal_prompt(m):
    if m.chat.id != ADMIN_ID: return
    msg = bot.send_message(m.chat.id, "Enter User ID to check balance:")
    bot.register_next_step_handler(msg, do_check_balance)


def do_check_balance(m):
    if m.chat.id != ADMIN_ID: return
    if not m.text.isdigit():
        bot.send_message(m.chat.id, "❌ Invalid ID.")
        return
    uid = int(m.text)
    cur.execute("SELECT balance FROM users WHERE id = ?", (uid, ))
    row = cur.fetchone()
    if row:
        bot.send_message(m.chat.id, f"User {uid} balance: ₹{row[0]:.2f}")
    else:
        bot.send_message(m.chat.id, "User not found.")


@bot.message_handler(func=lambda m: m.text == "✏️ Edit Balance")
def edit_balance_prompt(m):
    if m.chat.id != ADMIN_ID: return
    msg = bot.send_message(m.chat.id, "Enter User ID to edit balance:")
    bot.register_next_step_handler(msg, edit_balance_select)


def edit_balance_select(m):
    if m.chat.id != ADMIN_ID: return
    if not m.text.isdigit():
        bot.send_message(m.chat.id, "❌ Invalid ID.")
        return
    uid = int(m.text)
    cur.execute("SELECT id FROM users WHERE id=?", (uid, ))
    if not cur.fetchone():
        bot.send_message(m.chat.id, "User not found.")
        return

    pending_actions[m.chat.id] = {"target_uid": uid}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("➕ Add", "➖ Deduct", "📝 Set")
    markup.row("🔙 Back")
    bot.send_message(m.chat.id,
                     f"Choose action for user {uid}:",
                     reply_markup=markup)


@bot.message_handler(
    func=lambda m: m.text in ["➕ Add", "➖ Deduct", "📝 Set", "🔙 Back"])
def handle_edit_action(m):
    if m.chat.id != ADMIN_ID: return

    if m.text == "🔙 Back":
        pending_actions.pop(m.chat.id, None)
        handle_admin(m)
        return

    if m.chat.id not in pending_actions:
        bot.send_message(
            m.chat.id,
            "⚠️ No user selected. Please choose 'Edit Balance' first.")
        return

    action_map = {"➕ Add": "add", "➖ Deduct": "deduct", "📝 Set": "set"}
    pending_actions[m.chat.id]["action"] = action_map[m.text]
    bot.send_message(
        m.chat.id,
        f"Enter amount to {action_map[m.text]} for user {pending_actions[m.chat.id]['target_uid']}:"
    )
    bot.register_next_step_handler(m, do_edit_amount)


def do_edit_amount(m):
    if m.chat.id != ADMIN_ID: return
    data = pending_actions.get(m.chat.id)
    if not data or "action" not in data or "target_uid" not in data:
        bot.send_message(m.chat.id,
                         "⚠️ Please start with 'Edit Balance' again.")
        return

    try:
        amt = float(m.text)
    except:
        bot.send_message(m.chat.id, "❌ Invalid amount.")
        return

    uid = data["target_uid"]
    if data["action"] == "add":
        cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?",
                    (amt, uid))
    elif data["action"] == "deduct":
        cur.execute("UPDATE users SET balance = balance - ? WHERE id = ?",
                    (amt, uid))
    else:
        cur.execute("UPDATE users SET balance = ? WHERE id = ?", (amt, uid))

    conn.commit()
    bot.send_message(
        m.chat.id,
        f"✅ Updated user {uid} balance with {data['action']} ₹{amt:.2f}")
    pending_actions.pop(m.chat.id, None)
    handle_admin(m)


# === SERVICE MANAGEMENT AND ORDERING ===
@bot.message_handler(func=lambda m: m.text == "➕ Add Service")
def prompt_add_service(m):
    if m.chat.id != ADMIN_ID: return
    msg = bot.send_message(m.chat.id, "Enter service name:")
    bot.register_next_step_handler(msg, ask_service_smm_id)


def ask_service_smm_id(m):
    pending_actions[m.chat.id] = {"new_service_name": m.text}
    msg = bot.send_message(m.chat.id, "Enter SMM service ID:")
    bot.register_next_step_handler(msg, ask_service_price)


def ask_service_price(m):
    data = pending_actions.get(m.chat.id)
    if not data or "new_service_name" not in data:
        bot.send_message(m.chat.id, "⚠️ Start over by clicking ➕ Add Service")
        return
    data["smm_id"] = m.text
    msg = bot.send_message(m.chat.id, "Enter price per 1000:")
    bot.register_next_step_handler(msg, save_new_service)


def save_new_service(m):
    data = pending_actions.pop(m.chat.id, {})
    try:
        price = float(m.text)
        cur.execute(
            "INSERT INTO services (name, smm_id, price) VALUES (?, ?, ?)",
            (data["new_service_name"], data["smm_id"], price))
        conn.commit()
        bot.send_message(m.chat.id, "✅ Service added.")
    except:
        bot.send_message(m.chat.id, "❌ Error saving service.")


@bot.message_handler(func=lambda m: m.text == "❌ Delete Service")
def prompt_delete_service(m):
    if m.chat.id != ADMIN_ID: return
    cur.execute("SELECT id, name FROM services")
    rows = cur.fetchall()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for sid, name in rows:
        markup.row(f"🗑 {sid} - {name}")
    markup.row("🔙 Back")
    bot.send_message(m.chat.id,
                     "Select service to delete:",
                     reply_markup=markup)


@bot.message_handler(func=lambda m: m.text.startswith("🗑"))
def do_delete_service(m):
    try:
        sid = int(m.text.split(" ")[1])
        cur.execute("DELETE FROM services WHERE id = ?", (sid, ))
        conn.commit()
        bot.send_message(m.chat.id, "✅ Service deleted.")
    except:
        bot.send_message(m.chat.id, "❌ Invalid selection.")
    handle_admin(m)


@bot.message_handler(func=lambda m: m.text == "🛒 Buy Services")
def prompt_buy_service(m):
    cur.execute("SELECT name FROM services")
    rows = cur.fetchall()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for (name, ) in rows:
        markup.row(name)
    markup.row("🔙 Back")
    bot.send_message(m.chat.id, "Choose service:", reply_markup=markup)


@bot.message_handler(
    func=lambda m: m.text not in ["🔙 Back"] and m.chat.id != ADMIN_ID)
def process_service_selection(m):
    name = m.text.strip()
    cur.execute("SELECT id, smm_id, price FROM services WHERE name = ?",
                (name, ))
    row = cur.fetchone()
    if not row:
        return
    sid, smm_id, price = row
    pending_actions[m.chat.id] = {"service": (sid, smm_id, price)}
    msg = bot.send_message(m.chat.id, "Send link:")
    bot.register_next_step_handler(msg, ask_order_quantity)


def ask_order_quantity(m):
    data = pending_actions.get(m.chat.id, {})
    if "service" not in data:
        return
    data["link"] = m.text
    msg = bot.send_message(m.chat.id, "Enter quantity:")
    bot.register_next_step_handler(msg, place_order)


def place_order(m):
    data = pending_actions.get(m.chat.id, {})
    if "service" not in data:
        return
    try:
        qty = int(m.text)
    except:
        bot.send_message(m.chat.id, "❌ Invalid quantity.")
        return

    sid, smm_id, price = data["service"]
    cost = qty / 1000 * price
    uid = m.chat.id
    cur.execute("SELECT balance FROM users WHERE id = ?", (uid, ))
    bal = cur.fetchone()[0]
    if bal < cost:
        bot.send_message(uid, f"❌ Insufficient balance. You need ₹{cost:.2f}")
        return

    resp = requests.post("https://dllsmm.com/api/v2",
                         data={
                             "key": API_KEY,
                             "action": "add",
                             "service": smm_id,
                             "link": data["link"],
                             "quantity": qty
                         }).json()
    if resp.get("order"):
        order_id = resp["order"]
        cur.execute("UPDATE users SET balance = balance - ? WHERE id = ?",
                    (cost, uid))
        conn.commit()
        bot.send_message(uid, f"✅ Order placed. ID: {order_id}")
    else:
        bot.send_message(uid,
                         f"❌ Failed: {resp.get('error', 'Unknown error')}")

    pending_actions.pop(m.chat.id, None)
    send_main_menu(uid)


# === MAIN POLLING ===
bot.infinity_polling()
