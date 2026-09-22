# runtime-verify (ایده — فعلاً اجرا نکن)

وضعیت: **پارک‌شده**. اول اپ را درست کنیم؛ این فاز ژانگولر است تا پارسا بگوید برو.

Playwright و کد verify را استارت نکنید مگر دستور صریح.

## هدف
بعد از اینکه از روی *کد* گفتیم «کاربر این مسیر را برود»، یک‌بار UI زنده را چک کنیم تا راهنمای دروغ ندهیم.

## اسکوپ مینیمال (قفل‌شده در بحث تیم)

1. **۳–۵ مسیر طلایی** از ExternalService — نه کرال کل اپ.
2. مسیرها فاز ۱ = **لیست ثابت دستی** از `Route`/`label` همان graph ایندکس‌شده (مثلاً داشبورد / تنظیمات / لاگ)، نه auto-pick.
3. **Playwright**: باز شدن صفحه + وجود selector لیبل/دکمه کلیدی.
4. نتیجه → evidence روی همان `workspace_id` + `revision` با وضعیت `verified` یا `drift`.
5. `/ask`: اگر evidence=`drift` یا fail → abstain؛ اگر `verified` → conf↑.
6. شاخهٔ فرزند زیر `feature/planner-intent-rescue` · **نه main** · **τ دست نزن**.

## چه وقت ران می‌شود؟
- **نه** روی هر چت / هر `/ask` (latency/cost می‌ترکد).
- یک‌بار بعد از index/revision (یا job دستی).
- `/ask` فقط evidence کش‌شده را از store می‌خواند — صفر مرورگر سر هر پیام.

## پیش‌نیاز سخت
- پوشهٔ سورس فقط برای **index** است؛ Playwright اپ را از سورس روشن نمی‌کند.
- نیاز به **`BASE_URL` زنده‌ی UI** (مثلاً `http://localhost:…` روی Dev-04).
- بدون URL زنده = verify هوایی است.

## trade-off
- accuracy↑ روی همان چند مسیر طلایی.
- latency/cost فقط روی همان job یک‌بار.
- کل اپ را crawl نکنید.

## Done وقتی برگشتیم به این ایده
- اسکلت job + config مسیرها (`runtime_verify.paths.json` یا معادل).
- evidence روی knowledge contract.
- قلاب `/ask` برای drift → abstain.
- تست روی ۳–۵ مسیر ExternalService با BASE_URL واقعی.

## صریح ممنوع تا دستور
- پیاده‌سازی Playwright
- merge به main بدون اجازهٔ پارسا
