# 🚀 Moodle & Hemis Test Konvertori

Word (.docx/.doc) formatidagi test savollarini avtomatik ravishda **Moodle (GIFT)** va **Hemis** tizimlari formatiga o'tkazuvchi zamonaviy veb-platforma.

## ✨ Imkoniyatlar

### 👤 Foydalanuvchilar uchun:
*   **Zamonaviy Dashboard:** Chiroyli va qulay boshqaruv paneli.
*   **Formatlar:** Moodle (GIFT) va Hemis formatlarini qo'llab-quvvatlash.
*   **Avtomatik Konvertatsiya:** Word fayllarni bir zumda test formatiga o'tkazish.
*   **Rasmlar bilan ishlash:** Test ichidagi rasmlar avtomatik saqlanadi.
*   **Checklar:** To'lov chekini yuklash va admin tasdiqini kutish tizimi.
*   **Statistika:** Foydalanuvchi balansi va kunlik limitlar nazorati.
*   **Responsive:** Mobil va kompyuterda qulay ishlash.

### 🛡 Admin Panel:
*   Foydalanuvchilarni boshqarish.
*   Tariflarni yaratish va o'zgartirish.
*   To'lovlarni tasdiqlash yoki rad etish.
*   Umumiy statistika.

---

## 🛠 Texnologiyalar

Loyiha quyidagi zamonaviy texnologiyalar asosida qurilgan:
*   **Backend:** Python (FastAPI), PostgreSQL
*   **Frontend:** HTML5, TailwindCSS, Vue.js 3
*   **Fayl Tizimi:** python-docx, win32com (Windows), LibreOffice (Linux/Mac)

---

## 📥 O'rnatish va Ishga tushirish

### 1. Talablar
*   Python 3.8+
*   PostgreSQL
*   Microsoft Word (Windows uchun) yoki LibreOffice (Linux/Mac uchun)

### 2. O'rnatish
```bash
# Loyihani yuklab olish
git clone https://github.com/auzcoder/moodle-quiz-create.git
cd moodle-quiz-create

# Virtual muhit yaratish
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Kutubxonalarni o'rnatish
pip install -r requirements.txt
```

### 3. Bazani sozlash (.env)
Loyiha papkasida `.env` faylini yarating va quyidagi ma'lumotlarni kiriting:
```env
DB_NAME=moodle_db
DB_USER=postgres
DB_PASSWORD=sizning_parolingiz
DB_HOST=localhost
DB_PORT=5432
SECRET_KEY=maxfiy_kalit
```

### 4. Ishga tushirish
```bash
uvicorn main:app --reload --port 8005
```
Brauzerda: `http://localhost:8005` (yoki sozlangan portda)

---

## 📞 Aloqa va Yordam

Loyihada muammo chiqsa yoki savollaringiz bo'lsa, biz bilan bog'laning:

*   **Telefon:** [+998 90 696 00 10](tel:+998906960010)
*   **Telegram:** [@auzcoder](https://t.me/auzcoder)
*   **Email:** [auz.offical@gmail.com](mailto:auz.offical@gmail.com)

---
© 2026 TestConverter. Barcha huquqlar himoyalangan.
