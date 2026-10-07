# forjo-monitor

أداة فحص ذاتي **لموقع تملكه أنت**. تزحف إلى صفحات موقعك فقط، تقيس أداءها، تتحقّق من أن شبكات الإعلانات تُحمَّل فعلاً، تحفظ كل تشغيل في MongoDB Atlas، وتنبّهك على Telegram عند تدهور أي شيء.

> **ما لا تفعله هذه الأداة، أبداً:** لا تنقر على إعلان، ولا تُنشئ ظهوراً وهمياً، ولا تزيّف جلسة متصفّح، ولا تدوّر بروكسيات، ولا تملأ نماذج. كل ما تفعله هو قراءة الصفحة كما يقرأها زائر حقيقي واحد، بتروٍّ، من عنوان IP واحد.

---

## الفكرة في سطر واحد

كل دولار تكسبه من Adsterra أو Monetag يعتمد على أمرين: أن تُحمَّل خانة الإعلان فعلاً في متصفّح الزائر، وأن يبقى الزائر على الصفحة بما يكفي لرؤيتها. هذا المشروع يقيس هذين الأمرين على موقعك، ويسجّل التاريخ، ويخبرك بالضبط أي صفحة تفقدك المال.

## ما تقيسه الأداة

| المجموعة | أمثلة على الفحوصات |
| --- | --- |
| SEO | وجود العنوان وطوله، الوصف التعريفي، canonical، وسم `noindex`، عدد H1، البيانات المنظمة JSON-LD، Open Graph، خاصية `lang` |
| الإعلانات | هل هناك مورد من شبكة إعلانية في الصفحة أصلاً، هل خانة الإعلان بعرض وارتفاع > 0، هل هي فوق الطيّة |
| الأداء | TTFB، LCP، CLS، عدد أخطاء JavaScript، عدد الطلبات، حجم الصفحة المنقول |
| الروابط | عدد الروابط الداخلية، والروابط الخارجية المكسورة |
| الوصول | نسبة الصور التي تفتقد وسم `alt` |

كل فحص يُصنَّف: `pass` / `warn` / `fail` / `skip`، مع درجة خطورة `critical` / `major` / `minor`، حتى تعرف ما يُصلَح أولاً.

## المعمارية

```
forjo_monitor/
├── config.py              قراءة الإعدادات من .env مع تحقق صارم
├── checks.py              مفردات النتيجة (حالة + خطورة + فحوصات)
├── models.py              سجلات مُهيّأة للـ JSON و MongoDB
├── discovery.py           اكتشاف الصفحات من sitemap.xml وتغذية Blogger
├── page_audit.py          فحص صفحة واحدة: جلب، قياس، تصنيف
├── audit.py               المنسّق: اكتشاف → فحص → تخزين → تقرير → تنبيه
├── browser_auditor.py     Chromium بلا واجهة لقياس Core Web Vitals وموقع الإعلان
├── browser_scripts.py     مجسّات JavaScript للقراءة فقط
├── storage.py             MongoDB Atlas (مجموعتا runs و pages)
├── alerts.py              ملخص Telegram بنص عادي
├── reporting.py           تقرير Markdown + JSON + سجل تاريخي
├── cli.py / __main__.py   واجهة سطر الأوامر
├── analyzers/
│   ├── html_facts.py      استخراج حقائق SEO من الـ HTML
│   ├── ad_detector.py     التعرف على موارد شبكات الإعلانات
│   ├── link_checker.py    فحص الروابط (HEAD ثم GET)
│   ├── rules.py           قواعد SEO والوصول والروابط
│   ├── rules_monetization.py  قواعد الإعلانات والأداء
│   ├── aggregate.py       تجميع كل الفحوصات لصفحة واحدة
│   └── keywords.py        استخراج الموضوعات مع تطبيع عربي
└── crawler/               بلوك Scrapy: جرد المحتوى والموضوعات
```

## التثبيت

المتطلبات: Python 3.10 أو أحدث.

```bash
cd forjo-monitor
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

ثم:

```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux/macOS
```

## الإعداد

افتح `.env` واملأ القيم التالية. لا ترفع هذا الملف إلى Git أبداً (موجود في `.gitignore`).

```dotenv
SITE_BASE_URL=https://www.forjo.tech
MONGODB_URI=mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=forjo_monitor
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

| المتغيّر | إلزامي؟ | الغرض |
| --- | --- | --- |
| `SITE_BASE_URL` | نعم | جذر الموقع المملوك لك |
| `SITE_EXTRA_HOSTS` | لا | مضيفات تابعة لنفس الموقع (تُعتبر روابط داخلية) |
| `MONGODB_URI` | لا* | سلسلة اتصال Atlas لحفظ التاريخ |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | لا | ملخص فوري بعد كل تشغيل |
| `BROWSER_AUDIT_ENABLED` | لا | `false` لتشغيل سريع بلا متصفّح |
| `CRAWL_MAX_PAGES` | لا | سقف عدد الصفحات (افتراضي 300) |
| `CRAWL_DELAY_SECONDS` | لا | المهلة بين الطلبات (افتراضي 2) |

\* بدون `MONGODB_URI` تعمل الأداة لكن بلا تاريخ وبلا مقارنة بالتشغيل السابق.

> **مهم:** إن كانت كلمة مرور Atlas تحتوي رموزاً خاصة، رمّزها في الرابط: `@` تصبح `%40`، و`#` تصبح `%23`، و`:` تصبح `%3A`.

## الاستخدام

### فحص كامل

```bash
python -m forjo_monitor audit
```

يُنتج:

- `reports/latest.md` — تقرير عربي مقروء
- `reports/latest.json` — كل التفاصيل لكل صفحة
- `reports/history.jsonl` — سطر واحد لكل تشغيل، لرسم الاتجاه الزمني
- `artifacts/page-*.png` — لقطة شاشة تُحفظ تلقائياً عند وجود خطأ JavaScript أو عند غياب الإعلانات، كدليل

خيارات مفيدة:

```bash
# أسرع تشغيل ممكن: بلا متصفّح وبلا فحص روابط خارجية
python -m forjo_monitor audit --http-only --no-links

# جرّب على 3 صفحات فقط قبل تشغيل كامل
python -m forjo_monitor audit --limit 3

# اجعله يفشل بكود 1 إن وُجدت حالات فشل (مناسب لـ CI)
python -m forjo_monitor audit --fail-on-findings
```

### جرد المحتوى (Scrapy)

```bash
python -m forjo_monitor inventory
```

يمرّ على كل صفحة في `sitemap.xml` مرة واحدة، ويستخرج العنوان، عدد الكلمات، عدد الصور بلا `alt`، عدد الروابط، وأكثر الموضوعات تكراراً (مع تطبيع عربي: إزالة التشكيل وتوحيد الهمزات). النتيجة:

- `reports/content-inventory.jsonl`
- مجموعة `content` في MongoDB Atlas

هذا هو الجزء الذي يخبرك بما تكتب عنه مدونتك فعلاً، وما العناوين التي يمكنك التوسّع فيها.

### عرض مكان التقرير

```bash
python -m forjo_monitor show
```

## الأتمتة عبر GitHub Actions

المشروع جاهز للتشغيل المجاني على GitHub:

1. ارفع المشروع إلى مستودع GitHub (تأكّد أن `.env` غير مرفوع).
2. من `Settings → Secrets and variables → Actions` أضف:

   | الاسم | القيمة |
   | --- | --- |
   | `SITE_BASE_URL` | `https://www.forjo.tech` |
   | `MONGODB_URI` | سلسلة اتصال Atlas |
   | `MONGODB_DATABASE` | `forjo_monitor` |
   | `TELEGRAM_BOT_TOKEN` | رمز البوت (اختياري) |
   | `TELEGRAM_CHAT_ID` | معرّف المحادثة (اختياري) |

3. شغّل الـ workflow يدوياً أول مرة من `Actions → Site audit → Run workflow` مع `limit = 3` للتجربة، ثم اتركه يعمل تلقائياً كل يوم اثنين 06:00 UTC.

كل تشغيل يرفع ملفات `reports/` و`artifacts/` كـ artifact لمدة 30 يوماً.

## إعداد MongoDB Atlas (طبقة M0 المجانية)

1. أنشئ حساباً على <https://www.mongodb.com/atlas/database> وأنشئ عنقود **M0** (مجاني للأبد، 512 ميغابايت).
2. `Database Access → Add New Database User` — أنشئ مستخدماً بكلمة مرور قوية.
3. `Network Access → Add IP Address` — أضف `0.0.0.0/0` مؤقتاً للتشغيل من GitHub Actions (أو أضف نطاقات GitHub الرسمية لاحقاً لتضييق الوصول).
4. `Connect → Drivers → Python` وانسخ **SRV Connection String**.
5. استبدل `<db_password>` بكلمة المرور الحقيقية، وضع السلسلة في `MONGODB_URI`.

عند التسجيل عبر GitHub Student Pack تحصل على رصيد إضافي بعد إدخال الكود `GITHUBSTUDENT50-8F0K5N` في منظمة Atlas.

> إن كانت كلمة المرور تحتوي `@` أو `#` أو `:` فيجب ترميزها (`%40`, `%23`, `%3A`) وإلا سيفشل الاتصال.

## إعداد تنبيهات Telegram

```
1) أنشئ بوتاً: افتح محادثة مع @BotFather ثم /newbot وانسخ الرمز.
2) أرسل أي رسالة إلى بوتك، ثم افتح:
   https://api.telegram.org/bot<TOKEN>/getUpdates
   وانسخ قيمة "chat":{"id": ...}
```

ضع القيمتين في `.env` أو في أسرار GitHub. سيصلك بعد كل تشغيل ملخص مثل:

```
forjo-monitor — https://www.forjo.tech
pages audited: 12
pass: 168  warn: 21  fail: 3  skip: 8
failures vs previous run: -2

worst pages:
• https://www.forjo.tech/2026/08/blog-post_502.html (2 fail) — ads.script_present, seo.meta_description
```

## كيفية قراءة التقرير

ابدأ من الأعلى:

1. **`fail` بدرجة `critical`** — هذه تكسر الدخل أو الفهرسة. مثال: `ads.script_present` يعني أن الصفحة لا تحمّل أي إعلان، فمهما زادت زياراتها ستكسب صفراً منها. أو `http.status_ok` يعني أن الصفحة لا تُرجع 200.
2. **`fail` بدرجة `major`** — تخسر جزءاً من الحركة أو العرض. مثال: `perf.lcp` فوق 4 ثوانٍ، أو `seo.canonical` مفقود.
3. **`warn`** — تحسينات مكسبها تراكمي: طول الوصف التعريفي، Open Graph، `alt` للصور.
4. **`skip`** — فحص لم يُنفَّذ لهذا التشغيل (عادةً لأن المتصفّح كان معطّلاً). ليس نجاحاً وليس فشلاً.

## استكشاف الأخطاء

| العرض | السبب المرجّح | الحل |
| --- | --- | --- |
| `MONGODB_URI is not set` | ملف `.env` غير موجود أو المتغيّر فارغ | انسخ `.env.example` إلى `.env` |
| `ServerSelectionTimeoutError` | عنوان IP غير مسموح في Atlas | أضف العنوان في `Network Access` |
| `auth failed` | كلمة مرور غير مرمّزة في الرابط | رمّز الرموز الخاصة (`%40` للـ `@`) |
| فحوصات المتصفّح كلها `skip` | Playwright غير مثبّت | `python -m playwright install chromium` |
| توقّف السكربت بعد أول صفحة | استثناء غير متوقع | شغّل مع `-v` واقرأ التتبّع |
| `Scrapy's reactor can only be started once` | تشغيل `inventory` مرتين في نفس العملية | شغّل كل مرة في عملية منفصلة (الافتراضي) |

## ملاحظات قانونية ومهنية

- هذه الأداة تقرأ موقعك أنت. استخدامها على موقع لا تملكه يعتبر زحفاً غير مصرّح به، وقد يخالف شروط الخدمة.
- تحترم `robots.txt` افتراضياً (`CRAWL_RESPECT_ROBOTS=true`) وتبطئ الطلبات عمداً.
- كل تشغيل يستخدم عنوان IP واحداً ووكيل مستخدم واحد يصحّح نفسه — وهذا هو السلوك الذي تتوقّعه شبكات الإعلانات من زائر حقيقي.

## الترخيص

MIT.
