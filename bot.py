import os
import time
import threading
import telebot
from telebot import types
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, joinedload
from models import Base, Teacher, Course, Student, Enrollment, Category, Center
from dotenv import load_dotenv

load_dotenv()

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", f'sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), "crm.db")}')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

user_data = {}

def make_bot(token, center_id):
    bot = telebot.TeleBot(token)
    
    def main_menu():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📚 Kurslarni ko'rish", "👤 Profilim")
        return markup
        
    @bot.message_handler(commands=['start'])
    def welcome(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        session.close()
        if s:
            bot.send_message(message.chat.id, f"Xush kelibsiz, {s.full_name}!", reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "Edu CRM botiga xush kelibsiz! Ismingizni kiriting:")
            bot.register_next_step_handler(message, get_name)
            
    def get_name(message):
        user_data[message.chat.id] = {'full_name': message.text}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True))
        bot.send_message(message.chat.id, "Telefon raqamingizni yuboring:", reply_markup=markup)
        bot.register_next_step_handler(message, get_phone)
        
    def get_phone(message):
        if not message.contact:
            return bot.send_message(message.chat.id, "Tugmani bosing!")
        name = user_data[message.chat.id]['full_name']
        phone = message.contact.phone_number
        session = Session()
        s = session.query(Student).filter_by(phone_number=phone, center_id=center_id).first()
        if s:
            if not s.telegram_id:
                s.telegram_id = message.from_user.id
                s.full_name = name
                session.commit()
        else:
            s_new = Student(telegram_id=message.from_user.id, full_name=name, phone_number=phone, center_id=center_id)
            session.add(s_new)
            session.commit()
        session.close()
        bot.send_message(message.chat.id, "Ro'yxatdan o'tdingiz!", reply_markup=main_menu())
        
    @bot.message_handler(func=lambda m: m.text == "📚 Kurslarni ko'rish")
    def list_categories(message):
        session = Session()
        cats = session.query(Category).filter_by(center_id=center_id).all()
        session.close()
        if not cats:
            return bot.send_message(message.chat.id, "Hozircha kurs bo'limlari mavjud emas.")
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in cats:
            markup.add(types.InlineKeyboardButton(f"📂 {c.name}", callback_data=f"section_{c.name}"))
        bot.send_message(message.chat.id, "Bo'limni tanlang:", reply_markup=markup)
        
    @bot.callback_query_handler(func=lambda call: call.data.startswith('section_'))
    def list_courses(call):
        sec = call.data.replace('section_', '')
        session = Session()
        courses = session.query(Course).options(joinedload(Course.enrollments)).filter_by(category=sec, status='active', center_id=center_id).all()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in courses:
            accepted = sum(1 for e in c.enrollments if e.status == 'accepted')
            slots_left = (c.max_students or 15) - accepted
            label = f"📘 {c.title} | {c.schedule_time} | Bo'sh joy: {slots_left}"
            markup.add(types.InlineKeyboardButton(label, callback_data=f"enroll_{c.id}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back"))
        session.close()
        bot.edit_message_text(f"📂 {sec} guruhlari:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    @bot.callback_query_handler(func=lambda call: call.data == "back")
    def back(call):
        list_categories(call.message)
        
    @bot.callback_query_handler(func=lambda call: call.data.startswith('enroll_'))
    def enroll(call):
        cid = int(call.data.split('_')[1])
        session = Session()
        s = session.query(Student).filter_by(telegram_id=call.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            return
            
        course = session.query(Course).filter_by(id=cid, center_id=center_id).first()
        course_title = course.title if course else "Noma'lum"
        
        session.add(Enrollment(student_id=s.id, course_id=cid, status='waitlisted'))
        session.commit()
        
        # Notify admin app about new lead
        try:
            import requests
            requests.post("http://localhost:3000/api/new_lead", json={
                "full_name": s.full_name,
                "course": course_title,
                "center_id": center_id
            }, timeout=2)
        except Exception as e:
            print("Real-time notification failed:", e)
            
        session.close()
        bot.answer_callback_query(call.id, "Arizangiz qabul qilindi!")
        bot.send_message(call.message.chat.id, "Arizangiz qabul qilindi! Menejerlar tez orada bog'lanishadi.")
        
    @bot.message_handler(func=lambda m: m.text == "👤 Profilim")
    def profile(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            return
        text = f"👤 {s.full_name}\n📞 {s.phone_number}\n\n📚 Sizning kurslaringiz:\n"
        ens = session.query(Enrollment).filter(Enrollment.student_id == s.id).all()
        if not ens:
            text += "Hozircha hech qaysi guruhga a'zo emassiz."
        for e in ens:
            text += f"• {e.course.title} ({e.status})\n"
        session.close()
        bot.send_message(message.chat.id, text)
        
    return bot

def supervisor_loop():
    active_bot_tokens = {} # token -> thread
    print("Multi-bot supervisor started. Monitoring database for new tokens...")
    while True:
        try:
            session = Session()
            centers = session.query(Center).all()
            session.close()
            
            for center in centers:
                token = center.telegram_bot_token
                # Only start if token is configured and not already running
                if token and token not in active_bot_tokens:
                    print(f"New bot token found for center: {center.name} (ID: {center.id})")
                    try:
                        bot = make_bot(token, center.id)
                        t = threading.Thread(target=bot.infinity_polling, daemon=True)
                        t.start()
                        active_bot_tokens[token] = t
                    except Exception as e:
                        print(f"Failed to start bot for center {center.name}: {e}")
        except Exception as e:
            print("Supervisor loop error:", e)
        time.sleep(10) # check for new centers / tokens every 10 seconds

if __name__ == "__main__":
    supervisor_loop()
