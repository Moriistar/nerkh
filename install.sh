#!/bin/bash

# رنگ‌ها برای زیبایی خروجی
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}>>> 🚀 شروع نصب ربات SwupStar...${NC}"

# 1. آپدیت و نصب پیش‌نیازها بر اساس سیستم عامل
echo -e "${YELLOW}>>> 📦 در حال نصب پایتون و ابزارها...${NC}"
if command -v apt > /dev/null; then
    # برای سرورهای اوبونتو/دبیان
    sudo apt update
    sudo apt install -y python3 python3-pip git
elif command -v pkg > /dev/null; then
    # برای ترموکس (Termux)
    pkg update && pkg upgrade -y
    pkg install -y python git
else
    echo "❌ پکیج منیجر پیدا نشد. لطفا پایتون و گیت را دستی نصب کنید."
fi

# 2. دانلود یا آپدیت پروژه
echo -e "${YELLOW}>>> 📥 در حال دانلود سورس ربات...${NC}"
if [ -d "nerkh" ]; then
    cd nerkh
    echo "پوشه وجود دارد، آپدیت می‌شود..."
    git pull
else
    git clone https://github.com/Moriistar/nerkh
    cd nerkh
fi

# 3. نصب کتابخانه‌های پایتون
echo -e "${YELLOW}>>> 📚 نصب کتابخانه‌های مورد نیاز...${NC}"
# تلاش برای نصب با pip3 و هندل کردن خطای break-system-packages
pip3 install pyTelegramBotAPI requests --break-system-packages 2>/dev/null || pip install pyTelegramBotAPI requests

# 4. جایگزینی کد هوشمند (Setup Wizard)
echo -e "${YELLOW}>>> ⚙️ در حال تنظیم کد ربات برای پرسیدن توکن...${NC}"

cat << 'EOF' > bot.py
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
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            print(f"✅ تنظیمات از فایل {CONFIG_FILE} بارگذاری شد.")
            return json.load(f)
    
    print("\n\n" + "="*50)
    print("👋 به ربات خوش آمدید! بیایید تنظیمات اولیه را انجام دهیم.")
    print("="*50 + "\n")
    
    settings = {}
    
    while True:
        token = input("1️⃣ لطفا API TOKEN ربات را وارد کنید: ").strip()
        if len(token) > 10:
            settings['api_token'] = token
            break
        print("❌ توکن نامعتبر است.")

    while True:
        try:
            admin_id = input("2️⃣ آیدی عددی (Chat ID) ادمین را وارد کنید: ").strip()
            settings['admin_id'] = int(admin_id)
            break
        except ValueError:
            print("❌ آیدی باید عدد باشد.")

    cmc_key = input("3️⃣ کلید API کوین‌مارکت‌کپ (اختیاری - اینتر بزنید): ").strip()
    settings['cmc_api_key'] = cmc_key if cmc_key else 'YOUR_API_KEY_HERE'

    print("\n--- تنظیمات مالی ---")
    settings['card_number'] = input("4️⃣ شماره کارت: ").strip()
    settings['card_owner'] = input("5️⃣ نام صاحب حساب: ").strip()
    
    while True:
        try:
            rate = input("6️⃣ نرخ دلار (تومان): ").strip()
            settings['toman_rate'] = int(rate)
            break
        except ValueError:
            print("❌ عدد وارد کنید.")

    settings['min_buy'] = 500000
    settings['max_buy'] = 50000000
    settings['fee_percent'] = 0.05

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    
    print("\n✅ نصب تکمیل شد! فایل config.json ساخته شد.")
    return settings

SETTINGS = get_initial_setup()
API_TOKEN = SETTINGS['api_token']
ADMIN_ID = SETTINGS['admin_id']
CMC_API_KEY = SETTINGS['cmc_api_key']
config = SETTINGS

bot = telebot.TeleBot(API_TOKEN)
user_data = {} 
COINS = {
    'USDT': {'name': 'تتر (USDT)', 'slug': 'tether', 'network': 'TRC20'},
    'TON': {'name': 'تون کوین (TON)', 'slug': 'toncoin', 'network': 'TON'},
    'TRX': {'name': 'ترون (TRX)', 'slug': 'tron', 'network': 'TRC20'},
    'NOT': {'name': 'نات کوین (NOT)', 'slug': 'notcoin', 'network': 'TON'}
}

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

def save_config_to_file():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(SETTINGS, f, ensure_ascii=False, indent=4)

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
            try: bot.send_message(referrer_id, f"🎉 کاربر {first_name} با لینک شما عضو شد.")
            except: pass
    except: pass
    conn.close()

def update_kyc(user_id, phone=None, is_verified=None):
    conn = sqlite3.connect('swupstar.db')
    c = conn.cursor()
    if phone: c.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))
    if is_verified is not None: c.execute("UPDATE users SET is_verified=? WHERE user_id=?", (1 if is_verified else 0, user_id))
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

def get_price(slug):
    fallback_prices = {'tether': 1.0, 'toncoin': 5.2, 'tron': 0.12, 'notcoin': 0.005}
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    try:
        response = requests.get(url, params={'slug': slug, 'convert': 'USD'}, headers={'X-CMC_PRO_API_KEY': CMC_API_KEY}, timeout=5)
        data = response.json()
        return data['data'][list(data['data'].keys())[0]]['quote']['USD']['price']
    except: return fallback_prices.get(slug, 0)

def validate_wallet_address(address, coin):
    if len(address) < 15: return False
    if coin in ['TRX', 'USDT'] and not address.startswith('T'): return False
    return True

@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.chat.id
    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            if int(args[1]) != uid: referrer_id = int(args[1])
        except: pass

    user = get_user(uid)
    if not user:
        add_user(uid, message.from_user.first_name, message.from_user.username, referrer_id)
        user = get_user(uid)
    
    if user[4] == 0:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 تایید شماره موبایل", request_contact=True))
        bot.send_message(uid, "👋 به ربات صرافی خوش آمدید.\n⚠️ لطفا برای شروع شماره خود را تایید کنید:", reply_markup=markup)
        user_data[uid] = {'state': 'WAITING_CONTACT'}
    else:
        show_main_menu(uid)

def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('🛍 خرید ارز', '👤 پروفایل من')
    markup.add('📞 پشتیبانی', '📊 نرخ لحظه‌ای')
    if chat_id == ADMIN_ID: markup.add('⚙️ پنل مدیریت')
    bot.send_message(chat_id, "💎 منوی اصلی:", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    uid = message.chat.id
    if user_data.get(uid, {}).get('state') == 'WAITING_CONTACT':
        update_kyc(uid, phone=message.contact.phone_number)
        bot.send_message(uid, "✅ شماره ثبت شد.\n📸 لطفا عکس کارت ملی خود را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
        user_data[uid]['state'] = 'WAITING_KYC_PHOTO'

@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    uid = message.chat.id
    state = user_data.get(uid, {}).get('state')
    
    if state == 'WAITING_KYC_PHOTO':
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"verify_ok_{uid}"),
                   types.InlineKeyboardButton("❌ رد", callback_data=f"verify_no_{uid}"))
        bot.send_message(ADMIN_ID, f"⚠️ احراز هویت جدید:\n{message.from_user.first_name} ({uid})", reply_markup=markup)
        bot.send_message(uid, "⏳ مدارک ارسال شد. منتظر تایید باشید.")
        user_data[uid]['state'] = None
    
    elif state == 'WAITING_RECEIPT':
        info = user_data[uid]
        oid = log_order(uid, info['coin'], info['amount_toman'], info['crypto_amt'], info['wallet'])
        bot.forward_message(ADMIN_ID, uid, message.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ تایید واریز", callback_data=f"order_ok_{uid}_{oid}"),
                   types.InlineKeyboardButton("❌ رد", callback_data=f"order_no_{uid}_{oid}"))
        bot.send_message(ADMIN_ID, f"💰 سفارش #{oid}\nمبلغ: {info['amount_toman']:,}", reply_markup=markup)
        bot.send_message(uid, f"✅ فیش دریافت شد.\nکد رهگیری: {oid}")
        user_data[uid] = {}
        show_main_menu(uid)

@bot.message_handler(func=lambda m: m.text == '🛍 خرید ارز')
def buy_menu(m):
    if get_user(m.chat.id)[4] == 0: return bot.send_message(m.chat.id, "⛔️ حساب تایید نشده.")
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c, i in COINS.items(): markup.add(types.InlineKeyboardButton(i['name'], callback_data=f"buy_{c}"))
    bot.send_message(m.chat.id, "ارز را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('buy_'))
def buy_callback(call):
    coin = call.data.split('_')[1]
    user_data[call.message.chat.id] = {'state': 'WAITING_AMOUNT', 'coin': coin}
    bot.edit_message_text(f"💵 مبلغ خرید (تومان) برای {coin} را وارد کنید:", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'WAITING_AMOUNT')
def get_amount(m):
    try:
        amt = int(m.text)
        user_data[m.chat.id].update({'amount_toman': amt, 'state': 'WAITING_WALLET'})
        bot.send_message(m.chat.id, "📥 آدرس کیف پول را ارسال کنید:")
    except: bot.send_message(m.chat.id, "❌ عدد وارد کنید.")

@bot.message_handler(func=lambda m: user_data.get(m.chat.id, {}).get('state') == 'WAITING_WALLET')
def get_wallet(m):
    addr = m.text
    coin = user_data[m.chat.id]['coin']
    if not validate_wallet_address(addr, coin): return bot.send_message(m.chat.id, "❌ آدرس نامعتبر.")
    
    usd_price = get_price(COINS[coin]['slug'])
    crypto = (user_data[m.chat.id]['amount_toman'] / config['toman_rate'] / usd_price) * (1 - config['fee_percent'])
    user_data[m.chat.id].update({'wallet': addr, 'crypto_amt': round(crypto, 5), 'state': 'WAITING_RECEIPT'})
    
    txt = f"🧾 فاکتور:\nمبلغ: {user_data[m.chat.id]['amount_toman']:,} T\nدریافتی: {crypto:.5f}\n\n💳 کارت: `{config['card_number']}`\n{config['card_owner']}\n\n📸 عکس فیش را بفرستید."
    bot.send_message(m.chat.id, txt, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '👤 پروفایل من')
def profile(m):
    u = get_user(m.chat.id)
    bot.send_message(m.chat.id, f"👤 {u[1]}\nوضعیت: {'✅' if u[4] else '❌'}")

@bot.message_handler(func=lambda m: m.text == '📊 نرخ لحظه‌ای')
def rates(m):
    bot.send_message(m.chat.id, f"دلار: {config['toman_rate']:,} T")

@bot.message_handler(func=lambda m: m.text == '⚙️ پنل مدیریت' and m.chat.id == ADMIN_ID)
def admin(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('💵 تغییر نرخ دلار', '💳 تغییر شماره کارت', '🔙 بازگشت به منو اصلی')
    bot.send_message(m.chat.id, "پنل مدیریت:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '💵 تغییر نرخ دلار')
def set_rate(m):
    msg = bot.send_message(m.chat.id, "نرخ جدید:")
    bot.register_next_step_handler(msg, lambda M: (config.update({'toman_rate': int(M.text)}), save_config_to_file(), bot.send_message(M.chat.id, "✅")))

@bot.callback_query_handler(func=lambda c: c.data.startswith(('verify_', 'order_')))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    act, res, uid = call.data.split('_')[0], call.data.split('_')[1], int(call.data.split('_')[2])
    if act == 'verify':
        update_kyc(uid, is_verified=(res == 'ok'))
        bot.send_message(uid, "✅ تایید شد" if res == 'ok' else "❌ رد شد")
    elif act == 'order':
        oid = call.data.split('_')[3]
        conn = sqlite3.connect('swupstar.db')
        conn.execute("UPDATE orders SET status=? WHERE order_id=?", ('COMPLETED' if res == 'ok' else 'REJECTED', oid))
        conn.commit()
        conn.close()
        bot.send_message(uid, f"سفارش #{oid} {'تایید' if res=='ok' else 'رد'} شد.")
    bot.edit_message_caption(f"{call.message.caption}\nوضعیت: {res}", call.message.chat.id, call.message.message_id)

if __name__ == '__main__':
    print("✅ ربات آماده است...")
    while True:
        try: bot.polling(none_stop=True)
        except Exception as e: time.sleep(5)
EOF

# 5. اجرای ربات
echo -e "${GREEN}>>> ✅ نصب تمام شد! در حال اجرای ربات...${NC}"
python3 bot.py
