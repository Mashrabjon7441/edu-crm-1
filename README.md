# Edu CRM: O'quv Markazlari uchun Avtomatlashtirilgan Tizim

Ushbu tizim o'quv markazlari faoliyatini to'liq nazorat qilish, o'qituvchilarni boshqarish va o'quvchilarni Telegram orqali ro'yxatga olish uchun mo'ljallangan.

## Imkoniyatlar
- **Menejer Paneli:** O'qituvchilar va kurslarni boshqarish, guruh to'lganini kuzatish.
- **Direktor Paneli:** Umumiy statistika va kunlik dars jadvalini monitoring qilish.
- **Telegram Bot:** O'quvchilarni avtomatik ro'yxatdan o'tkazish va kurs sig'imiga qarab "Waitlist" (navbat)ga qo'shish.
- **Xavfsizlik:** Role-Based Access Control (RBAC) va xeshlangan parollar.

## O'rnatish

1. **Kutubxonalarni o'rnatish:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ma'lumotlar bazasini va Adminlarni yaratish:**
   ```bash
   python init_db.py
   ```

3. **Ishga tushirish:**
   - Veb-panel: `python admin_app.py`
   - Telegram Bot: `python bot.py`

## Kirish Ma'lumotlari (Default)
- **Menejer:** `manager` / `manager123`
- **Direktor:** `director` / `director123`

## Texnologiyalar
- Flask (Web), Telebot (Bot), SQLAlchemy (ORM), Bootstrap 5 (UI).
