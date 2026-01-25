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

Dasturni turli operatsion tizimlarda o'rnatish bo'yicha qo'llanma.

### 🪟 Windows Foydalanuvchilari uchun

**1-usul: Avtomatik (Tavsiya etiladi)**
Bu eng oson va tez usul.
1. Loyiha papkasidagi **`run_app.bat`** faylini toping.
2. Uni sichqoncha bilan ikki marta bosing.
3. Skript avtomatik ravishda barcha kerakli kutubxonalarni o'rnatadi va dasturni ishga tushiradi. Brauzer avtomatik ochiladi.

**2-usul: Qo'lda (Manual)**
Agar buyruqlar satri (CMD) bilan ishlashni xohlasangiz:

1. **Virtual muhit yaratish:**
   ```cmd
   python -m venv venv
   ```
2. **Faollashtirish:**
   ```cmd
   venv\Scripts\activate
   ```
3. **Kutubxonalarni o'rnatish:**
   ```cmd
   pip install -r requirements.txt
   ```
4. **Bazani sozlash:** Papkada `.env` fayl yarating (namuna quyida).
5. **Ishga tushirish:**
   ```cmd
   uvicorn main:app --reload --port 8005
   ```

---

### 🐧 Linux (Server / Ubuntu / Debian)

Linux serverlarida LibreOffice o'rnatilishi shart (fayllarni konvertatsiya qilish uchun).

1. **Kerakli dasturlarni o'rnatish:**
   ```bash
   sudo apt update
   sudo apt install libreoffice python3-venv -y
   ```
2. **Loyiha papkasiga kirish va muhit yaratish:**
   ```bash
   cd moodle-quiz-create
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Kutubxonalarni o'rnatish:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Eslatma: `pywin32` xatosi bo'lsa e'tibor bermang, Linuxda ishlatilmaydi)*

4. **.env faylini sozlash** (Ma'lumotlar bazasi ulanishi).

5. **Ishga tushirish:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8005
   ```

---

### 🍎 macOS Foydalanuvchilari uchun

1. **LibreOffice o'rnatish (Homebrew orqali):**
   ```bash
   brew install --cask libreoffice
   ```
   *Yoki rasmiy saytdan yuklab oling.*

2. **Terminalda sozlash:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Ishga tushirish:**
   ```bash
   uvicorn main:app --reload --port 8005
   ```

---

## ⚙️ Sozlamalar (.env)

Loyiha papkasida `.env` faylini yarating va quyidagi ma'lumotlarni kiriting:

```env
# Ma'lumotlar bazasi (PostgreSQL)
DB_NAME=moodle_db
DB_USER=postgres
DB_PASSWORD=sizning_parolingiz
DB_HOST=localhost
DB_PORT=5432

# Xavfsizlik
SECRET_KEY=maxfiy_kalit_uchun_istalgan_uzun_satr

# Email sozlamalari (Ixtiyoriy)
MAIL_USERNAME=email@gmail.com
MAIL_PASSWORD=app_password
MAIL_FROM=email@gmail.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
```

---

## 📞 Aloqa va Yordam

Loyihada muammo chiqsa yoki savollaringiz bo'lsa, biz bilan bog'laning:

*   **Telefon:** [+998 90 696 00 10](tel:+998906960010)
*   **Telegram:** [@auzcoder](https://t.me/auzcoder)
*   **Email:** [auz.offical@gmail.com](mailto:auz.offical@gmail.com)

---
© 2026 TestConverter. Barcha huquqlar himoyalangan.
