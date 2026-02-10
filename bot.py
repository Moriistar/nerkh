import telebot
from telebot import types
import requests
import sqlite3
import datetime
import re
import time
import threading

# ==========================================
# ⚙️ تنظیمات اصلی و کانفیگ
# ==========================================
API_TOKEN = '8114454885:AAG1n55bG3IW4f2r5jv9e_1vTRkSJ3kJYQ4'
ADMIN_ID = 595580684
CMC_API_KEY = 'YOUR_API_KEY_HERE'  # اگر ندارید، ربات از قیمت‌های پیش‌فرض استفاده می‌کند

bot = telebot.TeleBot(API_TOKEN)

# متغیرهای سراسری و تنظیمات قابل تغییر توسط ادمین
config = {
    'toman_rate': 61000,          # نرخ دلار به تومان
    'card_number': '6037-9974-0000-0000',
    'card_owner': 'نام صاحب حساب',
    'min_buy': 500000,            # حداقل خرید ۵۰۰ هزار تومان
    'max_buy': 50000000,          # حداکثر خرید ۵۰ میلیون تومان
    'fee_percent': 0.05,          # ۵ درصد کارمزد
    'invite_bonus': 0             # فعلا پاداش صفر
}

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
    
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, phone TEXT, 
                  is_verified INTEGER DEFAULT 0, join_date TEXT, referrer_id INTEGER)''')
    
    # جدول سفارشات
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  coin TEXT, amount_toman INTEGER, crypto_amount REAL, 
                  wallet_address TEXT, status TEXT, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- توابع کمکی دیتابیس ---
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
        # اطلاع رسانی به معرف
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
# 🛠 ابزارها (قیمت، ولت و ...)
# ==========================================
def get_price(slug):
    # اگر کلید API ندارید یا خراب است، قیمت تقریبی می‌دهد تا ربات متوقف نشود
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
    # اعتبارسنجی ساده (طول و کاراکتر)
    if len(address) < 15:
        return False
    if coin in ['TRX', 'USDT'] and not address.startswith('T'): # استاندارد TRC20 معمولا با T شروع میشه
        return False
    return True

# ==========================================
# 🤖 هندلرهای ربات (سمت کاربر)
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    
    # هندل کردن لینک رفرال
    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            potential_ref = int(args[1])
            if potential_ref != user_id:
                referrer_id = potential_ref
        except:
            pass

    user = get_user(user_id)
    if not user:
        add_user(user_id, message.from_user.first_name, message.from_user.username, referrer_id)
        user = get_user(user_id)
    
    # چک کردن وضعیت احراز هویت
    if user[4] == 0: # ستون is_verified
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تایید شماره موبایل", request_contact=True))
        bot.send_message(user_id, "👋 سلام به SwupStar Bot خوش آمدید.\n⚠️ برای امنیت معاملات، لطفا ابتدا شماره تماس خود را تایید کنید:", reply_markup=markup)
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

# --- پروسه احراز هویت (KYC) ---
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if user_data.get(uid, {}).get('state') == 'WAITING_CONTACT':
        if message.contact.user_id != uid:
            bot.send_message(uid, "❌ لطفا شماره خودتان را ارسال کنید.")
            return
            
        update_kyc(uid, phone=message.contact.phone_number)
        bot.send_message(uid, "✅ شماره ثبت شد.\n📸 اکنون لطفا تصویر کارت ملی خود را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
        user_data[uid]['state'] = 'WAITING_KYC_PHOTO'

@bot.message_handler(content_types=['photo'])
def handle_incoming_photos(message):
    uid = message.chat.id
    state = user_data.get(uid, {}).get('state')
    
    # 1. دریافت عکس کارت ملی
    if state == 'WAITING_KYC_PHOTO':
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید هویت", callback_data=f"verify_ok_{uid}"),
                   types.InlineKeyboardButton("❌ رد هویت", callback_data=f"verify_no_{uid}"))
        
        bot.send_message(ADMIN_ID, f"⚠️ **درخواست احراز هویت جدید**\nکاربر: {message.from_user.first_name} (ID: {uid})", parse_mode='Markdown', reply_markup=markup)
        bot.send_message(uid, "⏳ مدارک ارسال شد. پس از تایید مدیریت دسترسی شما باز می‌شود.")
        user_data[uid]['state'] = None
    
    # 2. دریافت عکس فیش واریزی
    elif state == 'WAITING_RECEIPT':
        order_info = user_data[uid]
        order_id = log_order(uid, order_info['coin'], order_info['amount_toman'], 
                             order_info['crypto_amt'], order_info['wallet'])
        
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید واریز", callback_data=f"order_ok_{uid}_{order_id}"),
                   types.InlineKeyboardButton("❌ رد واریز", callback_data=f"order_no_{uid}_{order_id}"))
        
        caption = f"""
💰 **سفارش خرید جدید (#{order_id})**
👤 کاربر: {uid}
💎 ارز: {order_info['coin']}
💵 مبلغ: {order_info['amount_toman']:,} تومان
⚖️ مقدار کریپتو: {order_info['crypto_amt']}
📥 ولت: `{order_info['wallet']}`
        """
        bot.send_message(ADMIN_ID, caption, parse_mode='Markdown', reply_markup=markup)
        bot.send_message(uid, f"✅ فیش شما دریافت شد.\n🔖 کد رهگیری: {order_id}\n⏳ پس از بررسی ادمین، واریز انجام می‌شود.")
        user_data[uid] = {} # پاکسازی حافظه
        show_main_menu(uid)

# --- پروسه خرید ارز ---
@bot.message_handler(func=lambda m: m.text == '🛍 خرید ارز')
def start_buy(m):
    user = get_user(m.chat.id)
    if user[4] == 0:
        bot.send_message(m.chat.id, "⛔️ حساب شما تایید نشده است. لطفا مدارک ارسال کنید.")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    for code, info in COINS.items():
        markup.add(types.InlineKeyboardButton(info['name'], callback_data=f"buy_select_{code}"))
    
    bot.send_message(m.chat.id, "انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_select_'))
def enter_amount(call):
    coin_code = call.data.split('_')[2]
    user_data[call.message.chat.id] = {'state': 'WAITING_AMOUNT', 'coin': coin_code}
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"💵 **خرید {COINS[coin_code]['name']}**\n\nلطفا مبلغ خرید را به **تومان** وارد کنید:\n🔻 حداقل: {config['min_buy']:,}\n🔺 حداکثر: {config['max_buy']:,}",
        parse_mode='Markdown'
    )

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
        bot.send_message(m.chat.id, f"📥 لطفا آدرس کیف پول **{coin} ({COINS[coin]['network']})** خود را ارسال کنید:")
        
    except ValueError:
        bot.send_message(m.chat.id, "❌ لطفا عدد لاتین وارد کنید.")

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'WAITING_WALLET')
def process_wallet(m):
    address = m.text
    coin = user_data[m.chat.id]['coin']
    
    if not validate_wallet_address(address, coin):
        bot.send_message(m.chat.id, "❌ آدرس ولت معتبر نیست یا فرمت اشتباهی دارد. لطفا با دقت کپی کنید:")
        return

    # محاسبه نهایی
    bot.send_message(m.chat.id, "⏳ در حال استعلام قیمت لحظه‌ای...")
    
    usd_price = get_price(COINS[coin]['slug'])
    toman_price = config['toman_rate']
    user_pay = user_data[m.chat.id]['amount_toman']
    
    # فرمول: (پول کاربر / نرخ تتر) تقسیم بر قیمت جهانی ارز * (۱ منهای کارمزد)
    amount_in_usd = user_pay / toman_price
    final_crypto = (amount_in_usd / usd_price) * (1 - config['fee_percent'])
    
    user_data[m.chat.id]['wallet'] = address
    user_data[m.chat.id]['crypto_amt'] = round(final_crypto, 5)
    user_data[m.chat.id]['state'] = 'WAITING_RECEIPT'
    
    invoice = f"""
🧾 **فاکتور نهایی پرداخت**

🔹 ارز انتخابی: {COINS[coin]['name']}
🔹 نرخ دلار: {toman_price:,} تومان
🔹 قیمت جهانی: {usd_price:.4f} $

💰 **مبلغ قابل پرداخت:** {user_pay:,} تومان
💎 **دریافتی شما:** ~{final_crypto:.5f} {coin}

💳 **شماره کارت:**
`{config['card_number']}`
👤 {config['card_owner']}

⚠️ لطفا مبلغ را کارت به کارت کرده و **عکس فیش** را همینجا ارسال کنید.
    """
    bot.send_message(m.chat.id, invoice, parse_mode='Markdown')

# --- پروفایل و زیرمجموعه ---
@bot.message_handler(func=lambda m: m.text == '👤 پروفایل من')
def my_profile(m):
    user = get_user(m.chat.id)
    ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (m.chat.id,))
    ref_count = c.fetchone()[0]
    conn.close()
    
    status = "✅ احراز شده" if user[4] else "❌ در انتظار احراز"
    
    txt = f"""
🆔 شناسه شما: `{m.chat.id}`
👤 نام: {user[1]}
🔰 وضعیت حساب: {status}
📅 تاریخ عضویت: {user[5][:10]}

👥 **تعداد زیرمجموعه:** {ref_count} نفر
🔗 **لینک دعوت اختصاصی:**
`{ref_link}`
    """
    bot.send_message(m.chat.id, txt, parse_mode='Markdown')

# --- نرخ لحظه‌ای ---
@bot.message_handler(func=lambda m: m.text == '📊 نرخ لحظه‌ای')
def live_rates(m):
    msg = "📊 **قیمت‌های لحظه‌ای بازار:**\n\n"
    msg += f"🇮🇷 دلار (تتر): {config['toman_rate']:,} تومان\n\n"
    
    for code, info in COINS.items():
        price = get_price(info['slug'])
        msg += f"🔸 **{code}:** {price:.4f} $\n"
        
    msg += f"\n📅 {datetime.datetime.now().strftime('%H:%M:%S')}"
    bot.send_message(m.chat.id, msg, parse_mode='Markdown')

# --- سیستم پشتیبانی ---
@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support_mode(m):
    user_data[m.chat.id] = {'state': 'SUPPORT'}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🔙 خروج از پشتیبانی')
    bot.send_message(m.chat.id, "👨‍💻 پیام خود را بنویسید. ادمین‌ها در اسرع وقت پاسخ می‌دهند:", reply_markup=markup)

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'SUPPORT')
def handle_support_msg(m):
    if m.text == '🔙 خروج از پشتیبانی':
        user_data[m.chat.id] = {}
        show_main_menu(m.chat.id)
        return
        
    # فروارد پیام به ادمین
    bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
    bot.send_message(m.chat.id, "✅ پیام ارسال شد.")

# --- پاسخ ادمین (Reply) ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.chat.id == ADMIN_ID)
def admin_reply(m):
    try:
        # استخراج آیدی کاربر از پیام فروارد شده
        if m.reply_to_message.forward_from:
            target_id = m.reply_to_message.forward_from.id
        # اگر کاربر پروفایلش بسته باشد، تلگرام forward_from را نمی‌فرستد
        # در این صورت باید از روش‌های دیگر استفاده کرد (اینجا فرض بر باز بودن است)
        else:
            bot.reply_to(m, "❌ پروفایل کاربر بسته است، نمی‌توان آیدی را پیدا کرد.")
            return

        bot.send_message(target_id, f"📞 **پاسخ پشتیبانی:**\n\n{m.text}", parse_mode='Markdown')
        bot.reply_to(m, "✅ پاسخ ارسال شد.")
    except Exception as e:
        bot.reply_to(m, f"خطا: {e}")

# ==========================================
# 👮‍♂️ پنل مدیریت (Admin Panel)
# ==========================================
@bot.message_handler(func=lambda m: m.text == '⚙️ پنل مدیریت' and m.chat.id == ADMIN_ID)
def admin_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('💵 تغییر نرخ دلار', '💳 تغییر شماره کارت')
    markup.add('📜 ۱۰ سفارش آخر', '📢 پیام همگانی')
    markup.add('🔙 بازگشت به منو اصلی')
    bot.send_message(m.chat.id, "🛠 وارد پنل مدیریت شدید:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '💵 تغییر نرخ دلار')
def change_rate(m):
    msg = bot.send_message(m.chat.id, f"نرخ فعلی: {config['toman_rate']}\nنرخ جدید را به تومان وارد کنید:")
    bot.register_next_step_handler(msg, lambda msg: update_config(msg, 'toman_rate', int))

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '💳 تغییر شماره کارت')
def change_card(m):
    msg = bot.send_message(m.chat.id, f"کارت فعلی: {config['card_number']}\nشماره کارت جدید را وارد کنید:")
    bot.register_next_step_handler(msg, lambda msg: update_config(msg, 'card_number', str))

def update_config(message, key, type_func):
    try:
        new_val = type_func(message.text)
        config[key] = new_val
        bot.send_message(message.chat.id, "✅ تنظیمات ذخیره شد.")
    except:
        bot.send_message(message.chat.id, "❌ خطا در فرمت ورودی.")

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '📜 ۱۰ سفارش آخر')
def view_last_orders(m):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    c.execute("SELECT order_id, user_id, coin, amount_toman, status FROM orders ORDER BY order_id DESC LIMIT 10")
    orders = c.fetchall()
    conn.close()
    
    if not orders:
        bot.send_message(m.chat.id, "لیست خالی است.")
        return
        
    text = "📋 **آخرین سفارشات:**\n\n"
    for o in orders:
        text += f"🔹 #{o[0]} | کاربر: {o[1]}\n🔸 {o[2]} | {o[3]:,} T | {o[4]}\n➖\n"
    bot.send_message(m.chat.id, text, parse_mode='Markdown')

# --- کال‌بک‌های دکمه‌های شیشه‌ای (تایید/رد) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(('verify_', 'order_')))
def handle_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    
    parts = call.data.split('_')
    action = parts[0]
    result = parts[1]
    uid = int(parts[2])
    
    if action == 'verify':
        if result == 'ok':
            update_kyc(uid, is_verified=True)
            bot.send_message(uid, "✅ **تبریک!** احراز هویت شما تایید شد.\nاکنون می‌توانید خرید کنید.")
            new_text = "✅ تایید شده"
        else:
            bot.send_message(uid, "❌ احراز هویت شما رد شد. لطفا عکس واضح‌تری ارسال کنید.")
            new_text = "❌ رد شده"
            
    elif action == 'order':
        oid = parts[3]
        conn = sqlite3.connect('swupstar.db')
        c = conn.cursor()
        c.execute("UPDATE orders SET status=? WHERE order_id=?", ('COMPLETED' if result == 'ok' else 'REJECTED', oid))
        conn.commit()
        conn.close()
        
        if result == 'ok':
            bot.send_message(uid, f"✅ سفارش #{oid} تایید شد و ارز به کیف پول شما واریز گردید.")
            new_text = "✅ سفارش تایید شد"
        else:
            bot.send_message(uid, f"❌ سفارش #{oid} به دلیل مشکل در فیش واریزی رد شد.")
            new_text = "❌ سفارش رد شد"

    bot.edit_message_caption(caption=f"{call.message.caption}\n\n📌 وضعیت: {new_text}", 
                             chat_id=ADMIN_ID, message_id=call.message.message_id)

# ==========================================
# 🚀 اجرا
# ==========================================
print("SwupStar Bot is RUNNING...")
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Connection Error: {e}")
        time.sleep(5)
