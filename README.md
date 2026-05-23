# AurexAi

Sun'iy intellekt platformasi — Python (Flask) + HTML / CSS / JavaScript.
Liquid-glass + neon UI, light/dark/auto rejim, 4-bosqichli loader,
admin panel, ko'p provayder API (OpenRouter va boshqalar), API kalit
papkalari va tasodifiy rotatsiya, obunalar (ODDIY/PRO/PLUS), Codex
funksiyasi (PLUS, kunlik 4 soat).

## Tezkor boshlash (lokal)

```bash
git clone https://github.com/<siz>/aurexai.git
cd aurexai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # tahrirlang
python app.py              # http://localhost:8000
```

Default admin: `owner@aurexai.uz` / `BelizardjonAstro`
(.env orqali o'zgartiring!)

## Productionga deploy

To'liq yoriqnoma + barcha komandalar:

- [`deploy/roadlocal.yml`](deploy/roadlocal.yml) — lokalda ishga tushirish
- [`deploy/roadglobaldomainssl.yml`](deploy/roadglobaldomainssl.yml) — domain + SSL bilan VPS

Asosiy texnologiyalar: Nginx + Gunicorn + systemd + Let's Encrypt.

## Loyiha tuzilmasi

```
aurexai/
├── app.py                  Flask entrypoint
├── config.py               Sozlamalar
├── core/                   Backend logikasi
│   ├── db.py models.py
│   ├── auth.py admin.py chat.py codex.py
│   ├── ai_service.py memory.py
├── templates/              HTML shablonlari
├── static/css|js|img/      Frontend
├── deploy/                 Nginx, systemd, Docker, deploy yo'riqnomalari
├── requirements.txt
└── .env.example
```

## Asosiy imkoniyatlar

- **Auth**: ro'yxatdan o'tish / kirish / sessiya (Flask-Login).
- **Loader**: 4 bosqich — internet tezligi, asset yuklash, qurilma aniqlash, animatsiyali ochilish.
- **Chat**: SSE streaming + token-token animatsiyali yozish.
- **Modellar**: admin paneldan AI xizmat (provayder), API kalit papkalari va modellarni boshqarish; har bir model uchun minimal tarif.
- **Tasodifiy kalit rotatsiyasi**: bir papkadagi ko'p kalitlar orasidan random tanlanadi, xato bo'lsa qayta urinish.
- **Obunalar**: ODDIY (tekin), PRO (30 000 so'm), PLUS (50 000 so'm). Sotib olish telegramda admin bilan.
- **Xotira**: ODDIY 100 MB, PRO 500 MB, PLUS 1 GB. AI xotira 3 kunda eskiradi.
- **Codex**: faqat PLUS. GitHub PAT tutorial; kunlik 4 soat limit (24 soatda reset). Worker stub TODO sifatida belgilangan.
- **Admin panel**: sayt nomi/logo, foydalanuvchilar (30 kunlik tarif berish, chatlarni tozalash), API xizmatlar / kalit papkalar / modellar.
- **Day/Night/Auto**: OS rejimini avtomatik kuzatadi.

## Codex haqida

Ushbu skeletda Codex'ning UI, limit hisoblash va job navbati yozilgan.
GitHub OAuth + Codespaces + auto-debug pipeline keyingi qadamlar uchun
`core/codex.py` ichida `# TODO` sifatida aniq joylanadi:

1. GitHub App / OAuth ro'yxatdan o'tkazib `client_id/secret` ni `.env` ga qo'ying.
2. `/codex/api/github/connect` ni real OAuth callbackka almashtiring.
3. Worker (RQ / Celery) qo'shing va shu yerda repo yaratish, codespace
   boshqarish, test loop ishlashini implement qiling.

## Litsenziya

MIT (siz xohlagandek).
