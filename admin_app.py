import os
import telebot
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker, scoped_session, joinedload
from models import Base, Admin, Teacher, Course, Student, Enrollment, Category, Attendance, Center, ActivityLog
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "crm_pipeline_single_center_103")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Database Setup - PostgreSQL in production, SQLite locally
DATABASE_URL = os.getenv("DATABASE_URL", f'sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), "crm.db")}')
# Render.com provides postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
session_factory = sessionmaker(bind=engine, expire_on_commit=False)
Session = scoped_session(session_factory)

# Bot Setup
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id_str):
    try:
        parts = user_id_str.split(':')
        if len(parts) != 2:
            return None
        u_type, u_id = parts[0], int(parts[1])
        s = Session()
        if u_type == 'admin':
            return s.get(Admin, u_id)
        elif u_type == 'teacher':
            return s.get(Teacher, u_id)
    except Exception:
        return None
    return None

@app.teardown_appcontext
def shutdown_session(exception=None):
    Session.remove()

# --- Password Helpers ---
def verify_password(stored_hash, plaintext_password):
    if not stored_hash:
        return False
    if stored_hash == plaintext_password:
        return True
    try:
        return check_password_hash(stored_hash, plaintext_password)
    except Exception:
        return False

def hash_password_if_needed(password):
    if not password:
        return password
    if password.startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
        return password
    return generate_password_hash(password)

def log_action(session, center_id, user_name, user_role, action, details=None):
    """Record an activity log entry for director monitoring."""
    try:
        session.add(ActivityLog(
            center_id=center_id,
            user_name=user_name,
            user_role=user_role,
            action=action,
            details=details
        ))
    except Exception as e:
        print("log_action error:", e)

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        session = Session()
        
        # Admin table (Superadmin/Director/Manager)
        admin = session.query(Admin).filter_by(username=username).first()
        if admin and verify_password(admin.password_hash, password):
            login_user(admin)
            if admin.role == 'superadmin': return redirect(url_for('superadmin_dashboard'))
            if admin.role == 'director': return redirect(url_for('director_dashboard'))
            return redirect(url_for('manager_dashboard'))
            
        # Teacher table
        teacher = session.query(Teacher).filter_by(username=username).first()
        if teacher and verify_password(teacher.password_hash, password):
            login_user(teacher)
            return redirect(url_for('teacher_dashboard'))
            
        flash("Login yoki parol noto'g'ri!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/setup_admin_x7k9q')
def setup_admin():
    """Temporary one-time setup endpoint. Remove after first use."""
    try:
        s = session_factory()
        sa_user = os.getenv("SUPERADMIN_USER", "Mashrabjon")
        sa_pass = os.getenv("SUPERADMIN_PASS", "MAshRAbjONoo05")
        sa = s.query(Admin).filter_by(role='superadmin').first()
        if sa:
            sa.username = sa_user
            sa.password_hash = generate_password_hash(sa_pass)
            msg = f"Updated! Login: {sa_user}"
        else:
            s.add(Admin(
                username=sa_user,
                password_hash=generate_password_hash(sa_pass),
                role='superadmin',
                full_name='Super Administrator'
            ))
            msg = f"Created! Login: {sa_user}"
        s.commit()
        s.close()
        return f"<h2>OK: {msg}</h2><a href='/login'>Login sahifasiga o'tish</a>"
    except Exception as e:
        return f"<h2>Xato: {str(e)}</h2>", 500

@app.route('/')
@login_required
def index():
    if current_user.role == 'superadmin': return redirect(url_for('superadmin_dashboard'))
    if current_user.role == 'manager': return redirect(url_for('manager_dashboard'))
    if current_user.role == 'director': return redirect(url_for('director_dashboard'))
    return redirect(url_for('teacher_dashboard'))

# --- Super Admin Dashboard ---
@app.route('/superadmin/dashboard')
@login_required
def superadmin_dashboard():
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    centers = session.query(Center).all()
    directors = session.query(Admin).filter_by(role='director').options(joinedload(Admin.center)).all()
    return render_template('superadmin_dashboard.html', centers=centers, directors=directors)

@app.route('/superadmin/center/add', methods=['POST'])
@login_required
def add_center():
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    center_name = request.form.get('center_name', '').strip()
    if center_name:
        session.add(Center(name=center_name))
        session.commit()
        flash(f"Yangi o'quv markazi qo'shildi: {center_name}")
    session.close()
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/center/delete/<int:center_id>', methods=['POST'])
@login_required
def delete_center(center_id):
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    center = session.get(Center, center_id)
    if not center:
        session.close()
        flash("O'quv markazi topilmadi!")
        return redirect(url_for('superadmin_dashboard'))
    
    name = center.name
    try:
        # Delete ActivityLogs
        session.query(ActivityLog).filter_by(center_id=center_id).delete()
        
        # Get Course and Student IDs to delete Attendances & Enrollments safely
        course_ids = [c.id for c in session.query(Course).filter_by(center_id=center_id).all()]
        student_ids = [s.id for s in session.query(Student).filter_by(center_id=center_id).all()]
        
        if course_ids:
            session.query(Attendance).filter(Attendance.course_id.in_(course_ids)).delete(synchronize_session=False)
            session.query(Enrollment).filter(Enrollment.course_id.in_(course_ids)).delete(synchronize_session=False)
            
        if student_ids:
            session.query(Attendance).filter(Attendance.student_id.in_(student_ids)).delete(synchronize_session=False)
            session.query(Enrollment).filter(Enrollment.student_id.in_(student_ids)).delete(synchronize_session=False)
            
        # Delete Course (which references Teacher) BEFORE deleting Teacher
        session.query(Course).filter_by(center_id=center_id).delete()
        session.query(Teacher).filter_by(center_id=center_id).delete()
        
        # Delete Categories, Admins, Students
        session.query(Category).filter_by(center_id=center_id).delete()
        session.query(Admin).filter_by(center_id=center_id).delete()
        session.query(Student).filter_by(center_id=center_id).delete()
        
        # Delete Center itself
        session.delete(center)
        session.commit()
        flash(f"O'quv markazi '{name}' va uning barcha ma'lumotlari to'liq o'chirib tashlandi!")
    except Exception as e:
        session.rollback()
        flash(f"Xatolik yuz berdi: {str(e)}")
    finally:
        session.close()
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/director/add', methods=['POST'])
@login_required
def add_director():
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    cid = int(request.form.get('center_id'))
    full_name = request.form.get('full_name')
    username = request.form.get('username')
    password = request.form.get('password')
    bot_token = request.form.get('telegram_bot_token', '').strip()
    
    # Update token on Center
    center = session.get(Center, cid)
    if center and bot_token:
        center.telegram_bot_token = bot_token
        
    if session.query(Admin).filter_by(username=username).first():
        flash("Ushbu login band, iltimos boshqa tanlang!")
    else:
        session.add(Admin(
            username=username,
            password_hash=hash_password_if_needed(password),
            role='director',
            full_name=full_name,
            center_id=cid
        ))
        session.commit()
        flash(f"Direktor {full_name} muvaffaqiyatli qo'shildi!")
    session.close()
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/director/edit/<int:director_id>', methods=['POST'])
@login_required
def edit_director(director_id):
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    d = session.get(Admin, director_id)
    if not d or d.role != 'director':
        session.close()
        flash("Direktor topilmadi!")
        return redirect(url_for('superadmin_dashboard'))
    
    full_name = request.form.get('full_name')
    username = request.form.get('username')
    password = request.form.get('password')
    bot_token = request.form.get('telegram_bot_token', '').strip()
    cid = int(request.form.get('center_id'))
    
    existing = session.query(Admin).filter(Admin.username == username, Admin.id != director_id).first()
    if existing:
        flash("Ushbu login band, iltimos boshqa tanlang!")
        session.close()
        return redirect(url_for('superadmin_dashboard'))
        
    d.full_name = full_name
    d.username = username
    if password and password.strip():
        d.password_hash = hash_password_if_needed(password)
    d.center_id = cid
    
    center = session.get(Center, cid)
    if center:
        old_token = center.telegram_bot_token
        center.telegram_bot_token = bot_token
        session.commit()
        
        if bot_token and bot_token != old_token:
            APP_URL = os.getenv('APP_URL', '').strip()
            if APP_URL and APP_URL.startswith('https://'):
                try:
                    from bot import register_center_webhook
                    register_center_webhook(center, APP_URL)
                except Exception as e:
                    print("Webhook update failed:", e)
    else:
        session.commit()
        
    session.close()
    flash("Direktor ma'lumotlari muvaffaqiyatli yangilandi!")
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/director/delete/<int:director_id>', methods=['POST'])
@login_required
def delete_director(director_id):
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    session = Session()
    d = session.get(Admin, director_id)
    if d and d.role == 'director':
        name = d.full_name
        session.delete(d)
        session.commit()
        flash(f"Direktor {name} o'chirildi.")
    session.close()
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/webhooks/sync', methods=['POST'])
@login_required
def sync_webhooks_route():
    if current_user.role != 'superadmin': return redirect(url_for('index'))
    
    # Get current host URL and fallback
    APP_URL = os.getenv('APP_URL', '').strip()
    if not APP_URL:
        APP_URL = os.getenv('RENDER_EXTERNAL_URL', '').strip()
    if not APP_URL:
        APP_URL = request.url_root.strip()
        if 'localhost' not in APP_URL and '127.0.0.1' not in APP_URL:
            APP_URL = APP_URL.replace('http://', 'https://')
            
    if APP_URL and (APP_URL.startswith('https://') or 'onrender.com' in APP_URL):
        try:
            from bot import init_webhooks
            init_webhooks(APP_URL)
            flash(f"Barcha bot webhooklari muvaffaqiyatli qayta tiklandi: {APP_URL}")
        except Exception as e:
            flash(f"Webhook tiklashda xato yuz berdi: {e}")
    else:
        flash("Webhook faqat jonli / production (HTTPS) serverda ishlaydi!")
    return redirect(url_for('superadmin_dashboard'))

# --- Manager/Director Dashboard ---
@app.route('/manager')
@login_required
def manager_dashboard():
    if current_user.role not in ['manager', 'director']: return redirect(url_for('login'))
    session = Session()
    center_id = current_user.center_id
    
    teachers = session.query(Teacher).filter_by(center_id=center_id).all()
    courses = session.query(Course).filter_by(center_id=center_id).all()
    today = date.today()
    
    new_leads = session.query(Enrollment).join(Course).filter(Course.center_id == center_id, Enrollment.status == 'waitlisted').all()
    reminders = session.query(Enrollment).join(Course).filter(Course.center_id == center_id, Enrollment.callback_date == today).all()
    postponed_leads = session.query(Enrollment).join(Course).filter(Course.center_id == center_id, Enrollment.status == 'postponed', Enrollment.callback_date > today).all()
    
    cats = session.query(Category).filter_by(center_id=center_id).all()
    grouped = {cat.name: [] for cat in cats}
    for c in courses:
        if c.category in grouped: grouped[c.category].append(c)
        else: grouped.setdefault(c.category, []).append(c)
    
    return render_template('manager_dashboard.html', teachers=teachers, grouped_courses=grouped, categories=[cat.name for cat in cats], new_leads=new_leads, reminders=reminders, postponed_leads=postponed_leads, date_today=today.strftime('%Y-%m-%d'))

@app.route('/manager/student/add_manual', methods=['POST'])
@login_required
def add_manual_student():
    session = Session()
    center_id = current_user.center_id
    phone = request.form.get('phone_number')
    course_id = int(request.form.get('course_id'))

    course = session.get(Course, course_id)
    if not course or course.center_id != center_id:
        flash("Ruxsat berilmagan guruh!")
        return redirect(url_for('manager_dashboard'))

    s = session.query(Student).filter_by(phone_number=phone, center_id=center_id).first()
    full_name = request.form.get('full_name')
    if not s:
        s = Student(full_name=full_name, phone_number=phone, center_id=center_id, added_by=current_user.username)
        session.add(s); session.flush()
    session.add(Enrollment(student_id=s.id, course_id=course_id, status='accepted', joined_date=date.today(), next_payment_date=date.today() + timedelta(days=30)))
    log_action(session, center_id, current_user.username, current_user.role,
               "O'quvchi qo'shildi", f"{full_name} → {course.title}")
    session.commit()
    flash(f"Muvaffaqiyatli qo'shildi.")
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/enrollment/accept', methods=['POST'])
@login_required
def accept_lead():
    session = Session()
    en = session.get(Enrollment, int(request.form.get('enrollment_id')))
    if en and en.course.center_id == current_user.center_id:
        en.course_id = int(request.form.get('course_id'))
        en.status = 'accepted'
        en.joined_date = datetime.strptime(request.form.get('joined_date'), '%Y-%m-%d').date()
        en.next_payment_date = en.joined_date + timedelta(days=30)
        log_action(session, current_user.center_id, current_user.username, current_user.role,
                   "Ariza qabul qilindi", f"{en.student.full_name} → {en.course.title}")
        session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/enrollment/pay/<int:eid>')
@login_required
def confirm_payment(eid):
    session = Session()
    en = session.get(Enrollment, eid)
    if en and en.course.center_id == current_user.center_id:
        en.next_payment_date = (en.next_payment_date or date.today()) + timedelta(days=30)
        session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/manager/course/<int:cid>/attendance')
@login_required
def manager_course_attendance(cid):
    session = Session()
    course = session.get(Course, cid)
    if not course or course.center_id != current_user.center_id: return redirect(url_for('manager_dashboard'))
    uz_to_idx = {'dushanba':0,'seshanba':1,'chorshanba':2,'payshanba':3,'juma':4,'shanba':5,'yakshanba':6}
    c_days = [uz_to_idx.get(d.strip().lower()) for d in course.days.split(',') if d.strip().lower() in uz_to_idx]
    dates = [d for d in [date.today() - timedelta(days=i) for i in range(30)] if d.weekday() in c_days]
    students = [e.student for e in course.enrollments if e.status == 'accepted']
    atts = session.query(Attendance).filter(Attendance.course_id == cid, Attendance.date >= (dates[-1] if dates else date.today())).all()
    att_map = {}
    for a in atts:
        d_str = a.date.strftime('%Y-%m-%d')
        att_map.setdefault(d_str, {})[a.student_id] = a.is_present
    return render_template('manager_attendance.html', course=course, students=students, dates=dates, att_map=att_map)

# --- Director Specific ---
@app.route('/director/dashboard')
@login_required
def director_dashboard():
    if current_user.role != 'director': return redirect(url_for('index'))
    session = Session()
    center_id = current_user.center_id
    courses = session.query(Course).filter_by(center_id=center_id).all()
    teachers = session.query(Teacher).filter_by(center_id=center_id).all()
    managers = session.query(Admin).filter_by(role='manager', center_id=center_id).all()
    students = session.query(Student).filter_by(center_id=center_id).all()
    stats = {
        'total_students': len(students),
        'active_courses': len([c for c in courses if c.status == 'active']),
        'waitlist_count': session.query(Enrollment).join(Course).filter(Course.center_id == center_id, Enrollment.status == 'waitlisted').count(),
        'total_teachers': len(teachers),
        'total_managers': len(managers)
    }
    logs = session.query(ActivityLog).filter_by(center_id=center_id).order_by(ActivityLog.created_at.desc()).limit(100).all()
    return render_template('director_dashboard.html', courses=courses, stats=stats, teachers=teachers, managers=managers, all_students=students, logs=logs)

@app.route('/director/manager/update', methods=['POST'])
@login_required
def update_manager_login():
    if current_user.role != 'director': return redirect(url_for('index'))
    session = Session()
    center_id = current_user.center_id
    mid, user, passw = request.form.get('manager_id'), request.form.get('username'), request.form.get('password')
    m = session.query(Admin).filter_by(id=mid, role='manager', center_id=center_id).first()
    if m:
        m.username = user
        if passw and passw.strip():
            m.password_hash = hash_password_if_needed(passw.strip())
    elif mid == "0":
        p = passw.strip() if (passw and passw.strip()) else "manager123"
        session.add(Admin(username=user, password_hash=hash_password_if_needed(p), role='manager', full_name="Manager", center_id=center_id))
    session.commit()
    return redirect(url_for('director_dashboard'))

# --- Common Actions ---
@app.route('/manager/add_teacher', methods=['POST'])
@login_required
def add_teacher():
    session = Session()
    full_name = request.form.get('full_name')
    session.add(Teacher(full_name=full_name, subject=request.form.get('subject'), username=request.form.get('username'), password_hash=hash_password_if_needed(request.form.get('password')), center_id=current_user.center_id))
    log_action(session, current_user.center_id, current_user.username, current_user.role,
               "O'qituvchi qo'shildi", full_name)
    session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/delete_teacher/<int:tid>')
@login_required
def delete_teacher(tid):
    session = Session()
    t = session.query(Teacher).filter_by(id=tid, center_id=current_user.center_id).first()
    if t:
        log_action(session, current_user.center_id, current_user.username, current_user.role,
                   "O'qituvchi o'chirildi", t.full_name)
        session.query(Course).filter_by(teacher_id=tid, center_id=current_user.center_id).update({"teacher_id": None})
        session.delete(t); session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/manager/course/update_teacher', methods=['POST'])
@login_required
def update_course_teacher():
    session = Session()
    c = session.query(Course).filter_by(id=int(request.form.get('course_id')), center_id=current_user.center_id).first()
    if c: c.teacher_id = int(request.form.get('teacher_id')); session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/add_category', methods=['POST'])
@login_required
def add_category():
    session = Session()
    name = request.form.get('category_name', '').strip()
    if name and not session.query(Category).filter_by(name=name, center_id=current_user.center_id).first():
        session.add(Category(name=name, center_id=current_user.center_id)); session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/delete_category/<cat_name>')
@login_required
def delete_category(cat_name):
    session = Session()
    c = session.query(Category).filter_by(name=cat_name, center_id=current_user.center_id).first()
    if c: session.delete(c); session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/manager/add_course', methods=['POST'])
@login_required
def add_course():
    session = Session()
    title = request.form.get('title')
    session.add(Course(title=title, teacher_id=request.form.get('teacher_id'), start_date=request.form.get('start_date'), schedule_time=request.form.get('schedule_time'), max_students=request.form.get('max_students'), category=request.form.get('category'), days=request.form.get('days'), center_id=current_user.center_id))
    log_action(session, current_user.center_id, current_user.username, current_user.role,
               "Guruh ochildi", title)
    session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/course/delete/<int:cid>')
@login_required
def delete_course(cid):
    session = Session()
    c = session.query(Course).filter_by(id=cid, center_id=current_user.center_id).first()
    if c: session.query(Enrollment).filter_by(course_id=cid).delete(); session.delete(c); session.commit()
    return redirect(url_for('manager_dashboard'))

# --- All remaining endpoints & features ---

@app.route('/manager/enrollment/reject/<int:eid>')
@login_required
def reject_lead(eid):
    session = Session()
    en = session.query(Enrollment).join(Course).filter(Enrollment.id == eid, Course.center_id == current_user.center_id).first()
    if en:
        log_action(session, current_user.center_id, current_user.username, current_user.role,
                   "Ariza rad etildi", f"{en.student.full_name} ({en.course.title})")
        en.status = 'rejected'
        session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/manager/enrollment/postpone', methods=['POST'])
@login_required
def postpone_lead():
    session = Session()
    eid = int(request.form.get('enrollment_id'))
    callback_date_str = request.form.get('callback_date')
    en = session.query(Enrollment).join(Course).filter(Enrollment.id == eid, Course.center_id == current_user.center_id).first()
    if en and callback_date_str:
        en.status = 'postponed'
        en.callback_date = datetime.strptime(callback_date_str, '%Y-%m-%d').date()
        session.commit()
    return redirect(url_for('manager_dashboard'))

@app.route('/manager/course/students/<int:cid>')
@login_required
def manager_course_students(cid):
    session = Session()
    course = session.query(Course).filter_by(id=cid, center_id=current_user.center_id).first()
    if not course:
        return jsonify([])
    
    enrollments = session.query(Enrollment).filter(Enrollment.course_id == cid, Enrollment.status == 'accepted').all()
    students_data = []
    today_val = date.today()
    for en in enrollments:
        days_left = 30
        if en.next_payment_date:
            days_left = (en.next_payment_date - today_val).days
        students_data.append({
            "id": en.id,
            "full_name": en.student.full_name,
            "phone": en.student.phone_number,
            "joined_date": en.joined_date.strftime('%Y-%m-%d') if en.joined_date else '—',
            "next_payment": en.next_payment_date.strftime('%Y-%m-%d') if en.next_payment_date else '—',
            "days_left": days_left
        })
    return jsonify(students_data)

@app.route('/manager/enrollment/delete/<int:eid>')
@login_required
def delete_enrollment(eid):
    session = Session()
    en = session.query(Enrollment).join(Course).filter(Enrollment.id == eid, Course.center_id == current_user.center_id).first()
    if en:
        session.delete(en)
        session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/update_teacher_login', methods=['POST'])
@login_required
def update_teacher_login():
    session = Session()
    tid = request.form.get('teacher_id')
    username = request.form.get('username')
    password = request.form.get('password')
    if tid:
        t = session.query(Teacher).filter_by(id=int(tid), center_id=current_user.center_id).first()
        if t:
            t.username = username
            if password and password.strip():
                t.password_hash = hash_password_if_needed(password.strip())
            session.commit()
    return redirect(request.referrer or url_for('manager_dashboard'))

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher': return redirect(url_for('index'))
    session = Session()
    courses = session.query(Course).filter_by(teacher_id=current_user.id).all()
    
    uz_to_idx = {'dushanba':0,'seshanba':1,'chorshanba':2,'payshanba':3,'juma':4,'shanba':5,'yakshanba':6}
    weekday_idx = date.today().weekday()
    
    today_courses = []
    other_courses = []
    
    for c in courses:
        c_days = [uz_to_idx.get(d.strip().lower()) for d in c.days.split(',') if d.strip().lower() in uz_to_idx]
        if weekday_idx in c_days:
            today_courses.append(c)
        else:
            other_courses.append(c)
            
    return render_template('teacher_dashboard.html', today_courses=today_courses, other_courses=other_courses)

@app.route('/teacher/course/<int:cid>')
@login_required
def teacher_course_view(cid):
    if current_user.role != 'teacher': return redirect(url_for('index'))
    session = Session()
    course = session.query(Course).filter_by(id=cid, teacher_id=current_user.id).first()
    if not course:
        flash("Sizga bu guruhga kirishga ruxsat berilmagan!")
        return redirect(url_for('teacher_dashboard'))
        
    uz_to_idx = {'dushanba':0,'seshanba':1,'chorshanba':2,'payshanba':3,'juma':4,'shanba':5,'yakshanba':6}
    c_days = [uz_to_idx.get(w.strip().lower()) for w in course.days.split(',') if w.strip().lower() in uz_to_idx]
    today = date.today()
    is_scheduled_today = today.weekday() in c_days
    
    students = [e.student for e in course.enrollments if e.status == 'accepted']
    
    # Fetch today's attendance if it exists
    atts = session.query(Attendance).filter(Attendance.course_id == cid, Attendance.date == today).all()
    att_dict = {a.student_id: a.is_present for a in atts}
    
    return render_template('teacher_course.html', course=course, students=students, today=today, is_scheduled_today=is_scheduled_today, att_dict=att_dict)

@app.route('/teacher/attendance/save', methods=['POST'])
@login_required
def save_attendance():
    if current_user.role != 'teacher':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json
    course_id = int(data.get('course_id'))
    attendance_data = data.get('attendance', [])
    
    session = Session()
    course = session.query(Course).filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course:
        return jsonify({"success": False, "message": "Forbidden"}), 403
        
    today = date.today()
    for item in attendance_data:
        student_id = int(item.get('student_id'))
        is_present = int(item.get('status'))
        
        # Check if attendance already exists for today
        att = session.query(Attendance).filter_by(course_id=course_id, student_id=student_id, date=today).first()
        if att:
            att.is_present = is_present
        else:
            att = Attendance(course_id=course_id, student_id=student_id, date=today, is_present=is_present)
            session.add(att)
            
    session.commit()
    return jsonify({"success": True})

@app.route('/api/students')
@login_required
def get_all_students_api():
    session = Session()
    center_id = current_user.center_id
    enrollments = session.query(Enrollment).join(Course).filter(Course.center_id == center_id, Enrollment.status == 'accepted').all()
    students_data = []
    today_val = date.today()
    for en in enrollments:
        days_left = 30
        if en.next_payment_date:
            days_left = (en.next_payment_date - today_val).days
        students_data.append({
            "id": en.id,
            "full_name": en.student.full_name,
            "phone": en.student.phone_number,
            "course": en.course.title if en.course else '—',
            "days_left": days_left
        })
    return jsonify(students_data)

@app.route('/api/new_lead', methods=['POST'])
def notify_new_lead():
    data = request.json
    center_id = data.get('center_id')
    if center_id:
        socketio.emit(f'new_lead_alert_{center_id}', data)
    else:
        socketio.emit('new_lead_alert', data)
    return jsonify({"status": "ok"})

# ── Webhook receiver for per-center Telegram bots (production / RAM-efficient)
@app.route('/bot_webhook/<int:center_id>', methods=['POST'])
def bot_webhook(center_id):
    from bot import active_bots
    bot = active_bots.get(center_id)
    if not bot:
        return 'Bot not configured', 404
    try:
        import json
        update = telebot.types.Update.de_json(request.data.decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook error for center {center_id}: {e}")
    return 'OK', 200

# ── Director: Broadcast announcement to all students via Telegram
@app.route('/director/announce', methods=['POST'])
@login_required
def send_announcement_route():
    if current_user.role != 'director':
        return jsonify({'error': 'Access denied'}), 403
    text = request.form.get('message', '').strip()
    if not text:
        flash("E'lon matni bo'sh bo'lishi mumkin emas!")
        return redirect(url_for('director_dashboard'))
    from bot import send_announcement
    sent, err = send_announcement(current_user.center_id, text)
    session = Session()
    log_action(session, current_user.center_id, current_user.username, current_user.role,
               "E'lon yuborildi", f"{sent} ta o'quvchiga: {text[:80]}")
    session.commit()
    flash(f"✅ E'lon {sent} ta o'quvchiga yuborildi!" if not err else f"⚠️ Xato: {err}")
    return redirect(url_for('director_dashboard') + '#logs')

# ── Startup: Webhook (production) or Polling (local)
import threading

APP_URL = os.getenv('APP_URL', '').strip()
if not APP_URL:
    APP_URL = os.getenv('RENDER_EXTERNAL_URL', '').strip()

if APP_URL and (APP_URL.startswith('https://') or 'onrender.com' in APP_URL):
    # PRODUCTION — use webhooks (no polling threads = much less RAM!)
    try:
        from bot import init_webhooks, send_payment_reminders
        t = threading.Thread(target=lambda: (init_webhooks(APP_URL)), daemon=True)
        t.start()
        print(f"Telegram bots: WEBHOOK mode → {APP_URL}")

        # Schedule daily payment reminders at 09:00
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler()
        sched.add_job(send_payment_reminders, 'cron', hour=9, minute=0)
        sched.start()
        print("Payment reminder scheduler started (09:00 daily).")
    except Exception as e:
        print("Webhook init failed:", e)
else:
    # LOCAL DEV — use polling ONLY if RUN_LOCAL_BOTS=true is set (to prevent local workspace from breaking production webhooks)
    if os.getenv('RUN_LOCAL_BOTS', 'false').lower() == 'true':
        try:
            from bot import supervisor_loop
            bt = threading.Thread(target=supervisor_loop, daemon=True)
            bt.start()
            print("Telegram bots: POLLING mode (local dev) active.")
        except Exception as e:
            print("Bot polling start failed:", e)
    else:
        print("Telegram bots: POLLING mode disabled locally to avoid production Webhook conflicts. Set RUN_LOCAL_BOTS=true in .env to enable.")

# Super Admin Control Bot (always polling, single bot)
try:
    from superadmin_bot import start_superadmin_bot
    sa_thread = threading.Thread(target=start_superadmin_bot, daemon=True)
    sa_thread.start()
    print("Super Admin control bot started.")
except Exception as e:
    print("Super Admin bot failed:", e)

if __name__ == '__main__':
    socketio.run(app, debug=True, port=3000)
