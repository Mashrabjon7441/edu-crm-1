import os
import time
import threading
import telebot
from telebot import types
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, joinedload
from models import Base, Teacher, Course, Student, Enrollment, Category, Center, Attendance
from dotenv import load_dotenv
from datetime import date, timedelta

load_dotenv()

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", f'sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), "crm.db")}')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}, pool_size=5, max_overflow=10)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

user_data = {}

# Global registry: center_id -> TeleBot instance (webhook mode uses no polling threads!)
active_bots = {}

# ─────────────────────────────────────────────
# BOT FACTORY — all handlers for a single center
# ─────────────────────────────────────────────
def make_bot(token, center_id):
    bot = telebot.TeleBot(token, threaded=False)

    def main_menu():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("📚 Kurslarni ko'rish", "👤 Profilim")
        markup.row("📅 Dars jadvali", "📊 Davomatim")
        markup.row("💳 To'lov holati")
        return markup

    # ── /start ──────────────────────────────
    @bot.message_handler(commands=['start'])
    def welcome(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        session.close()
        if s:
            bot.send_message(message.chat.id, f"Xush kelibsiz, {s.full_name}! 👋", reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "Edu CRM botiga xush kelibsiz!\nIsmingizni kiriting:")
            bot.register_next_step_handler(message, get_name)

    def get_name(message):
        user_data[message.chat.id] = {'full_name': message.text}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True))
        bot.send_message(message.chat.id, "Telefon raqamingizni yuboring:", reply_markup=markup)
        bot.register_next_step_handler(message, get_phone)

    def get_phone(message):
        if not message.contact:
            # Re-register so user doesn't get stuck
            bot.send_message(message.chat.id, "Iltimos, quyidagi tugmani bosing va telefon raqamingizni yuboring! 👇")
            bot.register_next_step_handler(message, get_phone)
            return
        name = user_data.get(message.chat.id, {}).get('full_name', 'O\'quvchi')
        phone = message.contact.phone_number
        session = Session()
        s = session.query(Student).filter_by(phone_number=phone, center_id=center_id).first()
        if s:
            if not s.telegram_id:
                s.telegram_id = message.from_user.id
                s.full_name = name
                session.commit()
        else:
            s = Student(telegram_id=message.from_user.id, full_name=name, phone_number=phone, center_id=center_id, added_by='Telegram Bot')
            session.add(s)
            session.commit()
        session.close()
        bot.send_message(message.chat.id, "✅ Ro'yxatdan o'tdingiz!\nQuyidagi menyudan foydalaning:", reply_markup=main_menu())

    # ── 📚 Kurslarni ko'rish ─────────────────
    @bot.message_handler(func=lambda m: m.text == "📚 Kurslarni ko'rish")
    def list_categories(message):
        session = Session()
        cats = session.query(Category).filter_by(center_id=center_id).all()
        session.close()
        if not cats:
            return bot.send_message(message.chat.id,
                "📭 Hozircha kurs bo'limlari mavjud emas.\n"
                "Tez orada kurslar qo'shiladi! O'quv markazi bilan bog'laning.")
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in cats:
            markup.add(types.InlineKeyboardButton(f"📂 {c.name}", callback_data=f"section_{c.name}"))
        bot.send_message(message.chat.id, "📚 Quyidagi bo'limlardan birini tanlang:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('section_'))
    def list_courses(call):
        bot.answer_callback_query(call.id)  # dismiss loading spinner
        sec = call.data.replace('section_', '', 1)
        session = Session()
        courses = session.query(Course).options(joinedload(Course.enrollments)).filter_by(
            category=sec, status='active', center_id=center_id).all()
        session.close()
        markup = types.InlineKeyboardMarkup(row_width=1)
        if not courses:
            markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_cats"))
            try:
                bot.edit_message_text(f"📂 *{sec}* bo'limida hozircha faol guruh yo'q.",
                    call.message.chat.id, call.message.message_id,
                    reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.send_message(call.message.chat.id, f"📂 *{sec}* bo'limida hozircha faol guruh yo'q.",
                    reply_markup=markup, parse_mode="Markdown")
            return
        for c in courses:
            accepted = sum(1 for e in c.enrollments if e.status == 'accepted')
            slots_left = (c.max_students or 15) - accepted
            emoji = "🟢" if slots_left > 3 else ("🟡" if slots_left > 0 else "🔴")
            label = f"{emoji} {c.title} | ⏰ {c.schedule_time} | Bo'sh joy: {slots_left}"
            markup.add(types.InlineKeyboardButton(label, callback_data=f"enroll_{c.id}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_cats"))
        try:
            bot.edit_message_text(f"📂 *{sec}* guruhlari:", call.message.chat.id,
                call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            bot.send_message(call.message.chat.id, f"📂 *{sec}* guruhlari:",
                reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data == "back_cats")
    def back_to_cats(call):
        bot.answer_callback_query(call.id)
        session = Session()
        cats = session.query(Category).filter_by(center_id=center_id).all()
        session.close()
        if not cats:
            try:
                bot.edit_message_text("📭 Hozircha kurs bo'limlari mavjud emas.",
                    call.message.chat.id, call.message.message_id)
            except Exception:
                bot.send_message(call.message.chat.id, "📭 Hozircha kurs bo'limlari mavjud emas.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in cats:
            markup.add(types.InlineKeyboardButton(f"📂 {c.name}", callback_data=f"section_{c.name}"))
        try:
            bot.edit_message_text("📚 Quyidagi bo'limlardan birini tanlang:",
                call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception:
            bot.send_message(call.message.chat.id, "📚 Quyidagi bo'limlardan birini tanlang:",
                reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('enroll_'))
    def enroll(call):
        bot.answer_callback_query(call.id)  # dismiss loading spinner first
        cid = int(call.data.split('_')[1])
        session = Session()
        s = session.query(Student).filter_by(telegram_id=call.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            bot.send_message(call.message.chat.id,
                "❗ Avval ro'yxatdan o'ting! /start buyrug'ini yuboring.")
            return
        course = session.query(Course).filter_by(id=cid, center_id=center_id).first()
        if not course:
            session.close()
            bot.send_message(call.message.chat.id, "❗ Kurs topilmadi.")
            return
        course_title = course.title

        # Check if already enrolled
        existing = session.query(Enrollment).filter_by(student_id=s.id, course_id=cid).first()
        if existing:
            session.close()
            status_text = {"waitlisted": "ko'rib chiqilmoqda", "accepted": "qabul qilingan", "rejected": "rad etilgan"}.get(existing.status, existing.status)
            bot.send_message(call.message.chat.id,
                f"ℹ️ Siz *{course_title}* guruhiga avval ariza yuborgansiz.\nHolati: *{status_text}*",
                parse_mode="Markdown")
            return

        session.add(Enrollment(student_id=s.id, course_id=cid, status='waitlisted'))
        session.commit()
        student_name = s.full_name
        session.close()

        # Notify web app
        try:
            import requests
            port = os.getenv("PORT", "10000")
            requests.post(f"http://127.0.0.1:{port}/api/new_lead", json={
                "full_name": student_name, "course": course_title, "center_id": center_id
            }, timeout=2)
        except Exception:
            pass

        bot.send_message(call.message.chat.id,
            f"✅ *{course_title}* guruhiga arizangiz muvaffaqiyatli yuborildi!\n"
            f"📞 Menejerlar tez orada bog'lanishadi.",
            parse_mode="Markdown")

    # ── 👤 Profilim ──────────────────────────
    @bot.message_handler(func=lambda m: m.text == "👤 Profilim")
    def profile(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            bot.send_message(message.chat.id, "Profilingiz topilmadi. /start buyrug'ini yuboring.")
            return
        ens = session.query(Enrollment).filter(Enrollment.student_id == s.id, Enrollment.status == 'accepted').all()
        text = f"👤 *{s.full_name}*\n📞 {s.phone_number}\n\n📚 *Kurslar:*\n"
        if not ens:
            text += "Hozircha hech qaysi guruhga a'zo emassiz."
        for e in ens:
            text += f"• {e.course.title} — _{e.course.schedule_time}_\n"
        session.close()
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

    # ── 📅 Dars jadvali ─────────────────────
    @bot.message_handler(func=lambda m: m.text == "📅 Dars jadvali")
    def schedule(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            return bot.send_message(message.chat.id, "Avval ro'yxatdan o'ting! /start")
        ens = session.query(Enrollment).filter(Enrollment.student_id == s.id, Enrollment.status == 'accepted').all()
        if not ens:
            session.close()
            return bot.send_message(message.chat.id, "Hozircha birorta guruhga yozilmagansiz.")
        text = "📅 *Sizning dars jadvalingiz:*\n\n"
        for e in ens:
            c = e.course
            teacher_name = c.teacher.full_name if c.teacher else "Belgilanmagan"
            text += (f"📘 *{c.title}*\n"
                     f"   👨‍🏫 O'qituvchi: {teacher_name}\n"
                     f"   ⏰ Vaqt: {c.schedule_time}\n"
                     f"   📆 Kunlar: {c.days}\n\n")
        session.close()
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

    # ── 📊 Davomatim ─────────────────────────
    @bot.message_handler(func=lambda m: m.text == "📊 Davomatim")
    def attendance_view(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            return bot.send_message(message.chat.id, "Avval ro'yxatdan o'ting! /start")
        ens = session.query(Enrollment).filter(Enrollment.student_id == s.id, Enrollment.status == 'accepted').all()
        if not ens:
            session.close()
            return bot.send_message(message.chat.id, "Hozircha birorta guruhga yozilmagansiz.")
        text = "📊 *Davomatingiz (so'nggi 30 kun):*\n\n"
        since = date.today() - timedelta(days=30)
        for e in ens:
            atts = session.query(Attendance).filter(
                Attendance.student_id == s.id,
                Attendance.course_id == e.course_id,
                Attendance.date >= since
            ).all()
            total = len(atts)
            present = sum(1 for a in atts if a.is_present)
            pct = round(present / total * 100) if total > 0 else 0
            bar = "🟢" * (pct // 20) + "⬜" * (5 - pct // 20)
            text += f"📘 *{e.course.title}*\n   {bar} {pct}% ({present}/{total})\n\n"
        session.close()
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

    # ── 💳 To'lov holati ────────────────────
    @bot.message_handler(func=lambda m: m.text == "💳 To'lov holati")
    def payment_status(message):
        session = Session()
        s = session.query(Student).filter_by(telegram_id=message.from_user.id, center_id=center_id).first()
        if not s:
            session.close()
            return bot.send_message(message.chat.id, "Avval ro'yxatdan o'ting! /start")
        ens = session.query(Enrollment).filter(Enrollment.student_id == s.id, Enrollment.status == 'accepted').all()
        if not ens:
            session.close()
            return bot.send_message(message.chat.id, "Hozircha birorta guruhga yozilmagansiz.")
        today = date.today()
        text = "💳 *To'lov holati:*\n\n"
        for e in ens:
            if e.next_payment_date:
                days_left = (e.next_payment_date - today).days
                if days_left < 0:
                    status = f"🔴 *Qarzdor* ({abs(days_left)} kun kechikkan)"
                elif days_left <= 3:
                    status = f"🟡 *{days_left} kun qoldi* — tez to'lang!"
                else:
                    status = f"🟢 *{days_left} kun qoldi*"
            else:
                status = "—"
            text += f"📘 *{e.course.title}*\n   {status}\n   📅 Keyingi to'lov: {e.next_payment_date or '—'}\n\n"
        session.close()
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

    return bot


# ─────────────────────────────────────────────
# WEBHOOK MODE (production) — 5x less RAM
# ─────────────────────────────────────────────
def register_center_webhook(center, app_url):
    """Register Telegram webhook for a single center. No polling thread needed!"""
    token = center.telegram_bot_token
    if not token or not token.strip():
        return
    try:
        bot = make_bot(token, center.id)
        webhook_url = f"{app_url.rstrip('/')}/bot_webhook/{center.id}"
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=webhook_url)
        active_bots[center.id] = bot
        print(f"✅ Webhook set: {center.name} → {webhook_url}")
    except Exception as e:
        print(f"❌ Webhook failed for {center.name}: {e}")


def init_webhooks(app_url):
    """Init webhooks for all centers (call once on startup)."""
    session = Session()
    centers = session.query(Center).all()
    session.close()
    for center in centers:
        register_center_webhook(center, app_url)
    print(f"Webhooks initialized. Active bots: {len(active_bots)}")


# ─────────────────────────────────────────────
# POLLING MODE (local dev / fallback)
# ─────────────────────────────────────────────
def supervisor_loop():
    """Polling fallback — used locally or if APP_URL not set."""
    print("Multi-bot supervisor (polling mode) started...")
    bot_threads = {}  # center_id -> thread
    while True:
        try:
            session = Session()
            centers = session.query(Center).all()
            session.close()
            for center in centers:
                token = center.telegram_bot_token
                if not token:
                    continue
                t = bot_threads.get(center.id)
                if t is None or not t.is_alive():
                    if t is not None:
                        print(f"Bot for '{center.name}' died. Restarting...")

                    def run_bot(tok=token, cid=center.id, cname=center.name):
                        while True:
                            try:
                                b = make_bot(tok, cid)
                                b.delete_webhook(drop_pending_updates=True)
                                time.sleep(2)
                                b.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=20)
                            except Exception as e:
                                print(f"Bot '{cname}' crashed: {e}. Retry in 15s...")
                                try:
                                    from superadmin_bot import send_superadmin_notification
                                    send_superadmin_notification(
                                        f"⚠️ Bot xatosi!\n🏫 Markaz: {cname}\n❌ {str(e)[:200]}\n🔄 15s da qayta ulanadi..."
                                    )
                                except Exception:
                                    pass
                                time.sleep(15)

                    t = threading.Thread(target=run_bot, daemon=True)
                    t.start()
                    bot_threads[center.id] = t
        except Exception as e:
            print("Supervisor error:", e)
        time.sleep(15)


# ─────────────────────────────────────────────
# PAYMENT REMINDER SCHEDULER TASK
# ─────────────────────────────────────────────
def send_payment_reminders():
    """Send Telegram reminders 3 days before payment due. Run daily via APScheduler."""
    session = Session()
    try:
        reminder_date = date.today() + timedelta(days=3)
        enrollments = session.query(Enrollment).filter(
            Enrollment.status == 'accepted',
            Enrollment.next_payment_date == reminder_date
        ).all()
        sent = 0
        for en in enrollments:
            if not en.student.telegram_id:
                continue
            bot = active_bots.get(en.course.center_id)
            if not bot:
                continue
            try:
                bot.send_message(
                    en.student.telegram_id,
                    f"💳 Hurmatli *{en.student.full_name}*!\n\n"
                    f"📚 *{en.course.title}* kursi uchun to'lov muddati "
                    f"*{en.next_payment_date.strftime('%d.%m.%Y')}* ga to'g'ri kelmoqda.\n\n"
                    f"⏰ Iltimos, o'z vaqtida to'lovni amalga oshiring.\n"
                    f"Savollar uchun menejering bilan bog'laning. 🙏",
                    parse_mode="Markdown"
                )
                sent += 1
            except Exception as e:
                print(f"Reminder send failed for {en.student.full_name}: {e}")
        if sent:
            print(f"Payment reminders sent: {sent}")
    except Exception as e:
        print(f"Reminder scheduler error: {e}")
    finally:
        session.close()


# ─────────────────────────────────────────────
# BROADCAST / ANNOUNCEMENT
# ─────────────────────────────────────────────
def send_announcement(center_id, text):
    """Send an announcement to all students of a center who have Telegram IDs."""
    bot = active_bots.get(center_id)
    if not bot:
        return 0, "Bot not active for this center"
    session = Session()
    try:
        students = session.query(Student).filter(
            Student.center_id == center_id,
            Student.telegram_id != None
        ).all()
        sent = 0
        for s in students:
            try:
                bot.send_message(s.telegram_id, f"📢 *E'lon:*\n\n{text}", parse_mode="Markdown")
                sent += 1
                time.sleep(0.05)  # rate limit
            except Exception:
                pass
        return sent, None
    except Exception as e:
        return 0, str(e)
    finally:
        session.close()


if __name__ == "__main__":
    supervisor_loop()
