# Moodle Test Konvertori (GIFT Format)

**Moodle Test Konvertori** - bu Microsoft Word (.docx, .doc) fayllaridagi jadval ko'rinishidagi testlarni Moodle tizimi tushunadigan **GIFT** formatiga (.txt) o'tkazib beruvchi zamonaviy veb-dastur.

Dastur **Windows**, **Linux** va **macOS** operatsion tizimlarida ishlaydi.

---

## 📋 Talablar (Prerequisites)

Dastur ishlashi uchun kompyuteringizda quyidagilar bo'lishi kerak:
1.  **Python 3.8** yoki undan yuqori versiyasi.
2.  Ofis dasturi:
    *   **Windows uchun**: Microsoft Word o'rnatilgan bo'lishi shart.
    *   **Linux / macOS uchun**: LibreOffice o'rnatilgan bo'lishi shart.

---

## 🚀 O'rnatish va Ishga tushirish (Installation)

### 🪟 Windows Foydalanuvchilari uchun

### 🪟 Windows Foydalanuvchilari uchun

**1-usul: Buyruqlar qatori orqali (Qo'lda)**
Bu usulda siz har bir qadamni o'zingiz bajarasiz. Bu jarayonni tushunish uchun foydali.

1.  **Virtual muhit (venv) yaratish**:
    Loyiha papkasida buyruqlar qatorini (CMD) ochib, quyidagini yozing:
    ```cmd
    python -m venv venv
    ```
2.  **Virtual muhitni faollashtirish**:
    ```cmd
    venv\Scripts\activate.bat
    ```
    *(Agar muvaffaqiyatli bo'lsa, qator boshida `(venv)` yozuvi paydo bo'ladi)*

3.  **Kutubxonalarni o'rnatish**:
    ```cmd
    pip install -r requirements.txt
    ```
4.  **Dasturni ishga tushiring**:
    ```cmd
    uvicorn main:app --reload
    ```
5.  **Natija**: Brauzerni ochib [http://127.0.0.1:8000](http://127.0.0.1:8000) manziliga kiring.

**2-usul: Avtomatik skript (.bat fayl)**
Bu eng oson va tez usul.
1.  Loyiha papkasidagi **`run_app.bat`** faylini toping.
2.  Uni sichqoncha bilan ikki marta bosing.
3.  U o'zi avtomatik virtual muhit yaratadi, kerakli narsalarni o'rnatadi va dasturni ishga tushiradi.

---

### 🐧 Linux (Ubuntu/Debian/CentOS)

1.  **LibreOffice**ni o'rnating (agar yo'q bo'lsa):
    ```bash
    sudo apt update
    sudo apt install libreoffice python3-venv 
    ```
2.  Loyiha papkasiga kiring va virtual muhit yarating:
    ```bash
    python3 -m venv venv
    ```
3.  Virtual muhitni faollashtiring:
    ```bash
    source venv/bin/activate
    ```
4.  Kutubxonalarni o'rnating:
    ```bash
    pip install -r requirements.txt
    ```
    *(Eslatma: Windowsga oid `pywin32` xatolik bersa, e'tibor bermang, Linuxda u ishlatilmaydi)*
5.  Dasturni ishga tushiring:
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```

---

### 🍎 macOS

1.  **LibreOffice**ni o'rnating:
    [LibreOffice saytidan yuklab oling](https://www.libreoffice.org/download/download-libreoffice/) yoki Homebrew orqali:
    ```bash
    brew install --cask libreoffice
    ```
2.  Terminal orqali loyiha papkasiga o'ting va virtual muhit yarating:
    ```bash
    python3 -m venv venv
    ```
3.  Virtual muhitni faollashtiring:
    ```bash
    source venv/bin/activate
    ```
4.  Kutubxonalarni o'rnating:
    ```bash
    pip install -r requirements.txt
    ```
5.  Dasturni ishga tushiring:
    ```bash
    uvicorn main:app --reload
    ```

---

## 🛠 Ishlash Tamoyili

1.  **Windowsda**: Dastur `win32com` orqali orqa fonda **Microsoft Word**ni ochadi va faylni HTML formatga o'giradi.
2.  **Linux/macOSda**: Dastur `subprocess` orqali **LibreOffice**ni chaqiradi (`--headless` rejimda) va faylni HTMLga o'giradi.
3.  Hosil bo'lgan HTML fayl `BeautifulSoup` yordamida tahlil qilinadi:
    *   Rasmlar **Base64** formatiga o'tkazilib, matn ichiga joylanadi.
    *   Test savollari jadvaldan ajratib olinadi (1-ustun tashlab ketiladi).
    *   Maxsus belgilar (`, ~, =, {, })` Moodle GIFT talabiga moslab "escape" qilinadi.
4.  Natija `.txt` fayl ko'rinishida yuklab beriladi.

## 📝 Mualliflik
Ushbu dastur Moodle tizimi uchun testlarni tez va oson tayyorlash maqsadida yaratildi.
