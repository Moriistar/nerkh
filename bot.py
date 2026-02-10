import telebot
from telebot import types
import requests
import sqlite3
import datetime
import time
import json
import os
import sys

# ==========================================
# ⚙️ سیستم تنظیمات و نصب اولیه
# ==========================================
CONFIG_FILE = 'config.json'

def get_initial_setup():
    """
    این تابع بررسی می‌کند آیا فایل تنظیمات وجود دارد یا خیر.
    اگر نبود، اطلاعات را از کاربر می‌پرسد و ذخیره می‌کند.
    """
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            print(f"✅ تنظیمات از فایل {CONFIG_FILE} بارگذاری شد.")
            return json.load(f)
    
    print("⚠️ فایل تنظیمات پیدا نشد. شروع مرحله نصب...")
    print("-------------------------------------------------")
    
    settings = {}
    
    # دریافت توکن ربات
    while True:
        token = input("1️⃣ لطفا API TOKEN ربات را وارد کنید: ").strip()
        if len(token) > 10:
            settings['api_token'] = token
            break
        print("❌ توکن نامعتبر است. دوباره تلاش کنید.")

    # دریافت آیدی عددی ادمین
    while True:
        try:
            admin_id = input("2️⃣ آیدی عددی (Chat ID) ادمین را وارد کنید: ").strip()
            settings['admin_id'] = int(admin_id)
            break
        except ValueError:
            print("❌ آیدی باید عدد باشد (مثال: 123456789)")

    # دریافت کلید CoinMarketCap (اختیاری)
    cmc_key = input("3️⃣ کلید API کوین‌مارکت‌کپ (اینتر بزنید تا رد شوید): ").strip()
    settings['cmc_api_key'] = cmc_key if cmc_key else 'YOUR_API_KEY_HERE'

    # تنظیمات پیش‌فرض مالی
    print("\n--- تنظیمات مالی ---")
    settings['card_number'] = input("4️⃣ شماره کارت جهت واریز: ").strip()
    settings['card_owner'] = input("5️⃣ نام صاحب حساب: ").strip()
    
    while True:
        try:
            rate = input("6️⃣ نرخ فعلی دلار (تومان): ").strip()
            settings['toman_rate'] = int(rate)
            break
        except ValueError:
            print("❌ لطفا عدد وارد کنید.")

    # سایر تنظیمات پیش‌فرض
    settings['min_buy'] = 500000
    settings['max_buy'] = 50000000
    settings['fee_percent'] = 0.05
    settings['invite_bonus'] = 0

    # ذخیره در فایل
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    
    print("-------------------------------------------------")
    print("✅ نصب تکمیل شد! فایل config.json ساخته شد.")
    print("🚀 ربات در حال اجراست...")
    return settings

# بارگذاری تنظیمات
SETTINGS = get_initial_setup()

# مقداردهی متغیرهای اصلی از روی تنظیمات
API_TOKEN = SETTINGS['api_token']
ADMIN_ID = SETTINGS['admin_id']
CMC_API_KEY = SETTINGS['cmc_api_key']

bot = telebot.TeleBot(API_TOKEN)

# متغیر config برای استفاده در طول برنامه (لینک شده به دیکشنری اصلی)
config = SETTINGS

# حافظه موقت برای مدیریت وضعیت کاربران
user_data = {} 

# لیست کوین‌های پشتیبانی شده
COINS = {
    'USDT': {'name': 'تتر (USDT)', 'slug': 'tether', 'network': 'TRC20'},
    'TON': {'name': 'تون کوین (TON)', 'slug': 'toncoin', 'network': 'TON'},
    'TRX': {'name': 'ترون (TRX)', 'slug': 'tron', 'network': 'TRC20'},
    'NOT': {'name': 'نات کوین (NOT)', 'slug': 'notcoin', 'network': 'TON'}
}

# ==========================================
# 🗄️ بخش دیتابیس (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, phone TEXT, 
                  is_verified INTEGER DEFAULT 0, join_date TEXT, referrer_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  coin TEXT, amount_toman INTEGER, crypto_amount REAL, 
                  wallet_address TEXT, status TEXT, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- تابع کمکی برای ذخیره تغییرات تنظیمات در فایل ---
def save_config_to_file():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(SETTINGS, f, ensure_ascii=False, indent=4)

# --- توابع دیتابیس ---
def get_user(user_id):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def add_user(user_id, first_name, username, referrer_id=None):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, first_name, username, join_date, referrer_id) VALUES (?, ?, ?, ?, ?)", 
                  (user_id, first_name, username, str(datetime.datetime.now()), referrer_id))
        conn.commit()
        if referrer_id:
            try:
                bot.send_message(referrer_id, f"🎉 تبریک! کاربر {first_name} با لینک شما عضو شد.")
            except:
                pass
    except sqlite3.IntegrityError:
        pass
    conn.close()

def update_kyc(user_id, phone=None, is_verified=None):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    if phone:
        c.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))
    if is_verified is not None:
        c.execute("UPDATE users SET is_verified=? WHERE user_id=?", (1 if is_verified else 0, user_id))
    conn.commit()
    conn.close()

def log_order(user_id, coin, toman, crypto_amt, wallet, status="PENDING"):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, coin, amount_toman, crypto_amount, wallet_address, status, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (user_id, coin, toman, crypto_amt, wallet, status, str(datetime.datetime.now())[:19]))
    last_id = c.lastrowid
    conn.commit()
    conn.close()
    return last_id

# ==========================================
# 🛠 ابزارها
# ==========================================
def get_price(slug):
    fallback_prices = {'tether': 1.0, 'toncoin': 5.2, 'tron': 0.12, 'notcoin': 0.005}
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {'slug': slug, 'convert': 'USD'}
    headers = {'X-CMC_PRO_API_KEY': CMC_API_KEY}
    
    try:
        response = requests.get(url, params=parameters, headers=headers, timeout=5)
        data = response.json()
        return data['data'][list(data['data'].keys())[0]]['quote']['USD']['price']
    except:
        return fallback_prices.get(slug, 0)

def validate_wallet_address(address, coin):
    if len(address) < 15: return False
    if coin in ['TRX', 'USDT'] and not address.startswith('T'): return False
    return True

# ==========================================
# 🤖 هندلرهای ربات
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            potential_ref = int(args[1])
            if potential_ref != user_id: referrer_id = potential_ref
        except: pass

    user = get_user(user_id)
    if not user:
        add_user(user_id, message.from_user.first_name, message.from_user.username, referrer_id)
        user = get_user(user_id)
    
    if user[4] == 0:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تایید شماره موبایل", request_contact=True))
        bot.send_message(user_id, "👋 سلام به SwupStar Bot خوش آمدید.\n⚠️ لطفا ابتدا شماره تماس خود را تایید کنید:", reply_markup=markup)
        user_data[user_id] = {'state': 'WAITING_CONTACT'}
    else:
        show_main_menu(user_id)

def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('🛍 خرید ارز', '👤 پروفایل من')
    markup.add('📞 پشتیبانی', '📊 نرخ لحظه‌ای')
    if chat_id == ADMIN_ID:
        markup.add('⚙️ پنل مدیریت')
    bot.send_message(chat_id, "💎 منوی اصلی صرافی:", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if user_data.get(uid, {}).get('state') == 'WAITING_CONTACT':
        if message.contact.user_id != uid:
            bot.send_message(uid, "❌ لطفا شماره خودتان را ارسال کنید.")
            return
        update_kyc(uid, phone=message.contact.phone_number)
        bot.send_message(uid, "✅ شماره ثبت شد.\n📸 اکنون تصویر کارت ملی خود را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
        user_data[uid]['state'] = 'WAITING_KYC_PHOTO'

@bot.message_handler(content_types=['photo'])
def handle_incoming_photos(message):
    uid = message.chat.id
    state = user_data.get(uid, {}).get('state')
    
    if state == 'WAITING_KYC_PHOTO':
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید هویت", callback_data=f"verify_ok_{uid}"),
                   types.InlineKeyboardButton("❌ رد هویت", callback_data=f"verify_no_{uid}"))
        bot.send_message(ADMIN_ID, f"⚠️ **احراز هویت جدید**\nکاربر: {message.from_user.first_name} (ID: {uid})", parse_mode='Markdown', reply_markup=markup)
        bot.send_message(uid, "⏳ مدارک ارسال شد. منتظر تایید مدیریت باشید.")
        user_data[uid]['state'] = None
    
    elif state == 'WAITING_RECEIPT':
        order_info = user_data[uid]
        order_id = log_order(uid, order_info['coin'], order_info['amount_toman'], order_info['crypto_amt'], order_info['wallet'])
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید واریز", callback_data=f"order_ok_{uid}_{order_id}"),
                   types.InlineKeyboardButton("❌ رد واریز", callback_data=f"order_no_{uid}_{order_id}"))
        caption = f"💰 **سفارش جدید (#{order_id})**\n💎 {order_info['coin']}\n💵 {order_info['amount_toman']:,} T\n📥 `{order_info['wallet']}`"
        bot.send_message(ADMIN_ID, caption, parse_mode='Markdown', reply_markup=markup)
        bot.send_message(uid, f"✅ فیش دریافت شد.\n🔖 کد رهگیری: {order_id}")
        user_data[uid] = {}
        show_main_menu(uid)

@bot.message_handler(func=lambda m: m.text == '🛍 خرید ارز')
def start_buy(m):
    user = get_user(m.chat.id)
    if user[4] == 0:
        bot.send_message(m.chat.id, "⛔️ حساب تایید نشده است.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for code, info in COINS.items():
        markup.add(types.InlineKeyboardButton(info['name'], callback_data=f"buy_select_{code}"))
    bot.send_message(m.chat.id, "انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_select_'))
def enter_amount(call):
    coin_code = call.data.split('_')[2]
    user_data[call.message.chat.id] = {'state': 'WAITING_AMOUNT', 'coin': coin_code}
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                          text=f"💵 مبلغ خرید به **تومان**:\n(حداقل: {config['min_buy']:,})", parse_mode='Markdown')

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'WAITING_AMOUNT')
def process_amount(m):
    try:
        amount = int(m.text)
        if amount < config['min_buy'] or amount > config['max_buy']:
            bot.send_message(m.chat.id, f"❌ مبلغ باید بین {config['min_buy']:,} تا {config['max_buy']:,} باشد.")
            return
        user_data[m.chat.id]['amount_toman'] = amount
        user_data[m.chat.id]['state'] = 'WAITING_WALLET'
        coin = user_data[m.chat.id]['coin']
        bot.send_message(m.chat.id, f"📥 آدرس کیف پول **{coin}** را ارسال کنید:")
    except ValueError:
        bot.send_message(m.chat.id, "❌ لطفا عدد لاتین وارد کنید.")

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'WAITING_WALLET')
def process_wallet(m):
    address = m.text
    coin = user_data[m.chat.id]['coin']
    if not validate_wallet_address(address, coin):
        bot.send_message(m.chat.id, "❌ آدرس ولت معتبر نیست.")
        return
    
    bot.send_message(m.chat.id, "⏳ محاسبه قیمت...")
    usd_price = get_price(COINS[coin]['slug'])
    final_crypto = (user_data[m.chat.id]['amount_toman'] / config['toman_rate'] / usd_price) * (1 - config['fee_percent'])
    
    user_data[m.chat.id].update({'wallet': address, 'crypto_amt': round(final_crypto, 5), 'state': 'WAITING_RECEIPT'})
    invoice = f"🧾 **فاکتور پرداخت**\n\n💰 مبلغ: {user_data[m.chat.id]['amount_toman']:,} T\n💎 دریافتی: ~{final_crypto:.5f} {coin}\n\n💳 کارت: `{config['card_number']}`\n👤 {config['card_owner']}\n\n⚠️ عکس فیش را ارسال کنید."
    bot.send_message(m.chat.id, invoice, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '👤 پروفایل من')
def my_profile(m):
    user = get_user(m.chat.id)
    ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (m.chat.id,))
    ref_count = c.fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"👤 {user[1]}\n👥 زیرمجموعه: {ref_count}\n🔗 لینک دعوت:\n`{ref_link}`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '📊 نرخ لحظه‌ای')
def live_rates(m):
    msg = f"🇮🇷 دلار: {config['toman_rate']:,} T\n"
    for code, info in COINS.items():
        msg += f"🔸 {code}: {get_price(info['slug']):.4f} $\n"
    bot.send_message(m.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support_mode(m):
    user_data[m.chat.id] = {'state': 'SUPPORT'}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🔙 خروج')
    bot.send_message(m.chat.id, "👨‍💻 پیام دهید:", reply_markup=markup)

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'SUPPORT')
def handle_support_msg(m):
    if m.text == '🔙 خروج':
        user_data[m.chat.id] = {}
        show_main_menu(m.chat.id)
        return
    bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
    bot.send_message(m.chat.id, "✅ ارسال شد.")

@bot.message_handler(func=lambda m: m.reply_to_message and m.chat.id == ADMIN_ID)
def admin_reply(m):
    try:
        if m.reply_to_message.forward_from:
            bot.send_message(m.reply_to_message.forward_from.id, f"📞 **پاسخ:**\n{m.text}", parse_mode='Markdown')
            bot.reply_to(m, "✅ ارسال شد.")
        else:
            bot.reply_to(m, "❌ کاربر قابل شناسایی نیست (پروفایل بسته).")
    except: pass

# ==========================================
# 👮‍♂️ پنل مدیریت
# ==========================================
@bot.message_handler(func=lambda m: m.text == '⚙️ پنل مدیریت' and m.chat.id == ADMIN_ID)
def admin_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('💵 تغییر نرخ دلار', '💳 تغییر شماره کارت')
    markup.add('📜 ۱۰ سفارش آخر', '🔙 بازگشت به منو اصلی')
    bot.send_message(m.chat.id, "🛠 پنل مدیریت:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '💵 تغییر نرخ دلار')
def change_rate(m):
    msg = bot.send_message(m.chat.id, f"نرخ فعلی: {config['toman_rate']}\nجدید را وارد کنید:")
    bot.register_next_step_handler(msg, lambda msg: update_config(msg, 'toman_rate', int))

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '💳 تغییر شماره کارت')
def change_card(m):
    msg = bot.send_message(m.chat.id, f"کارت فعلی: {config['card_number']}\nجدید را وارد کنید:")
    bot.register_next_step_handler(msg, lambda msg: update_config(msg, 'card_number', str))

def update_config(message, key, type_func):
    try:
        new_val = type_func(message.text)
        config[key] = new_val
        save_config_to_file()  # ذخیره در فایل json
        bot.send_message(message.chat.id, "✅ ذخیره شد.")
    except:
        bot.send_message(message.chat.id, "❌ فرمت اشتباه.")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '📜 ۱۰ سفارش آخر')
def view_last_orders(m):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("SELECT order_id, user_id, coin, amount_toman, status FROM orders ORDER BY order_id DESC LIMIT 10")
    orders = c.fetchall()
    conn.close()
    text = "📋 **آخرین سفارشات:**\n" + ("\n".join([f"#{o[0]} | {o[2]} | {o[4]}" for o in orders]) if orders else "خالی")
    bot.send_message(m.chat.id, text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith(('verify_', 'order_')))
def handle_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    parts = call.data.split('_')
    action, result, uid = parts[0], parts[1], int(parts[2])
    
    if action == 'verify':
        update_kyc(uid, is_verified=(result == 'ok'))
        msg = "✅ تایید شد" if result == 'ok' else "❌ رد شد"
        bot.send_message(uid, f"وضعیت احراز هویت: {msg}")
    elif action == 'order':
        oid = parts[3]
        conn = sqlite3.connect('swupstar.db')
        c = conn.cursor()
        c.execute("UPDATE orders SET status=? WHERE order_id=?", ('COMPLETED' if result == 'ok' else 'REJECTED', oid))
        conn.commit()
        conn.close()
        bot.send_message(uid, f"سفارش #{oid} {'✅ تایید' if result == 'ok' else '❌ رد'} شد.")

    bot.edit_message_caption(caption=f"{call.message.caption}\n\n📌 وضعیت: {result}", chat_id=ADMIN_ID, message_id=call.message.message_id)

# ==========================================
# 🚀 اجرا
# ==========================================
if __name__ == '__main__':
    print("SwupStar Bot Started...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
