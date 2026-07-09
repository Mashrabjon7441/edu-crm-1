import os
import telebot
from telebot import types
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Admin, Center, Student, Course, Teacher
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

from db_setup import Session


SUPERADMIN_TELEGRAM_ID = 7637932499
TOKEN = os.getenv("SUPERADMIN_BOT_TOKEN")

def admin_only(func):
    def wrapper(message, *args, **kwargs):
        if message.from_user.id != SUPERADMIN_TELEGRAM_ID:
            print(f"Ignored message from unauthorized TG user: {message.from_user.id}")
            return
        return func(message, *args, **kwargs)
    return wrapper

def start_superadmin_bot():
    if not TOKEN:
        print("SUPERADMIN_BOT_TOKEN not provided. Super Admin Bot skipped.")
        return

    bot = telebot.TeleBot(TOKEN)
    print("Super Admin Telegram Bot starting...")

    def get_main_keyboard():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📊 Tizim holati", "🔑 Loginni o'zgartirish")
        markup.add("🔒 Parolni o'zgartirish")
        return markup

    @bot.message_handler(commands=['start'])
    @admin_only
    def send_welcome(message):
        bot.send_message(
            message.chat.id,
            "Assalomu alaykum, Tizim Sohibi! Super Admin boshqaruv botiga xush kelibsiz.\nQuyidagi tugmalardan birini tanlang:",
            reply_markup=get_main_keyboard()
        )

    @bot.message_handler(func=lambda msg: msg.text == "📊 Tizim holati")
    @admin_only
    def show_status(message):
        session = Session()
        try:
            centers_count = session.query(Center).count()
            directors_count = session.query(Admin).filter_by(role='director').count()
            teachers_count = session.query(Teacher).count()
            students_count = session.query(Student).count()
            text = (
                "📊 **Tizim Statistikalari:**\n\n"
                f"🏫 O'quv markazlari: {centers_count} ta\n"
                f"👤 Direktorlar soni: {directors_count} ta\n"
                f"👨‍🏫 O'qituvchilar soni: {teachers_count} ta\n"
                f"👥 Talabalar soni: {students_count} ta\n"
            )
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik yuz berdi: {str(e)}")
        finally:
            session.close()

    @bot.message_handler(func=lambda msg: msg.text == "🔑 Loginni o'zgartirish")
    @admin_only
    def ask_new_login(message):
        bot.send_message(message.chat.id, "Yangi Super Admin loginini kiriting:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, set_new_login)

    def set_new_login(message):
        new_username = message.text.strip()
        if not new_username or len(new_username) < 3:
            bot.send_message(message.chat.id, "Login kamida 3ta belgidan iborat bo'lishi kerak!", reply_markup=get_main_keyboard())
            return
        
        session = Session()
        try:
            existing = session.query(Admin).filter(Admin.username == new_username, Admin.role != 'superadmin').first()
            if existing:
                bot.send_message(message.chat.id, "Ushbu login band, boshqasini tanlang!", reply_markup=get_main_keyboard())
                return

            sa = session.query(Admin).filter_by(role='superadmin').first()
            if sa:
                old_username = sa.username
                sa.username = new_username
                session.commit()
                bot.send_message(message.chat.id, f"Muvaffaqiyatli o'zgartirildi!\nEski login: {old_username}\nYangi login: {new_username}", reply_markup=get_main_keyboard())
            else:
                bot.send_message(message.chat.id, "Tizimda superadmin topilmadi!", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik yuz berdi: {str(e)}", reply_markup=get_main_keyboard())
        finally:
            session.close()

    @bot.message_handler(func=lambda msg: msg.text == "🔒 Parolni o'zgartirish")
    @admin_only
    def ask_new_password(message):
        bot.send_message(message.chat.id, "Yangi Super Admin parolini kiriting:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, set_new_password)

    def set_new_password(message):
        new_pass = message.text.strip()
        if not new_pass or len(new_pass) < 6:
            bot.send_message(message.chat.id, "Parol kamida 6ta belgidan iborat bo'lishi kerak!", reply_markup=get_main_keyboard())
            return
        
        session = Session()
        try:
            sa = session.query(Admin).filter_by(role='superadmin').first()
            if sa:
                sa.password_hash = generate_password_hash(new_pass)
                session.commit()
                bot.send_message(message.chat.id, "Super Admin paroli muvaffaqiyatli yangilandi! 🔒", reply_markup=get_main_keyboard())
            else:
                bot.send_message(message.chat.id, "Tizimda superadmin topilmadi!", reply_markup=get_main_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"Xatolik yuz berdi: {str(e)}", reply_markup=get_main_keyboard())
        finally:
            session.close()

    try:
        bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    import time
    time.sleep(2)
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=20)

def send_superadmin_notification(text):
    if not TOKEN:
        return
    bot = telebot.TeleBot(TOKEN)
    try:
        bot.send_message(SUPERADMIN_TELEGRAM_ID, text)
    except Exception as e:
        print(f"Failed to send notification to Super Admin: {e}")
