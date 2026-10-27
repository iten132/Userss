#!/usr/bin/env python3
"""
رادار ولوحة تحكم فاحص يوزرات تيليجرام الاحترافي (v8.0 Master Edition)
المطور: جمال القفاف
Instagram: @_vedt
Telegram: @sn_ee
"""

import asyncio
import html as html_lib
import json
import logging
import os
import random
import re
import sys
from datetime import datetime
import aiohttp
from colorama import Fore, Style, init

try:
    from telethon import TelegramClient, functions as tg_functions
    from telethon.errors import (
        FloodWaitError,
        BotMethodInvalidError,
        RPCError,
        UsernameInvalidError,
        UsernameOccupiedError,
        UsernameNotOccupiedError,
        UsernamePurchaseAvailableError,
    )
    TELETHON_AVAILABLE = True
except ImportError:
    TelegramClient = None
    tg_functions = None
    FloodWaitError = BotMethodInvalidError = RPCError = UsernameInvalidError = UsernameOccupiedError = Exception
    UsernameNotOccupiedError = UsernamePurchaseAvailableError = Exception
    TELETHON_AVAILABLE = False

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("MasterChecker")

CONFIG_FILE = "bot_config.json"
RESULTS_FILE = "available.txt"
USER_SESSION_FILE = "username_checker_user_v2.session"

# متغيرات إدارة الحالة والإعدادات
state = "IDLE"  # IDLE, RUNNING, PAUSED
current_task = None
current_target_file = ""
speed_profile = "TURBO"  # TURBO (0.2s), FAST (0.4s), SAFE (0.8s)
scan_direction = "BOTTOM_TO_TOP"  # BOTTOM_TO_TOP (من النهاية ⬆️) or TOP_TO_BOTTOM (من البداية ⬇️)
stats = {"checked": 0, "available": 0, "total": 0, "start_time": None}


def print_banner():
    """طباعة معلومات المطور في الطرفية بتصميم متقن."""
    print(Fore.CYAN + "╔" + "═" * 62 + "╗")
    print(Fore.CYAN + "║" + Fore.WHITE + Style.BRIGHT + "   ⚡ رادار فاحص اليوزرات المطور (Control Panel v8.0 Master) ".center(54) + Fore.CYAN + "║")
    print(Fore.CYAN + "╠" + "═" * 62 + "╣")
    print(Fore.CYAN + "║  " + Fore.YELLOW + Style.BRIGHT + "👤 المطور   : " + Fore.WHITE + "جمال القفاف".ljust(44) + Fore.CYAN + "║")
    print(Fore.CYAN + "║  " + Fore.MAGENTA + Style.BRIGHT + "📸 انستقرام : " + Fore.WHITE + "@_vedt".ljust(44) + Fore.CYAN + "║")
    print(Fore.CYAN + "║  " + Fore.BLUE + Style.BRIGHT + "✈️ تيليجرام : " + Fore.WHITE + "@sn_ee".ljust(44) + Fore.CYAN + "║")
    print(Fore.CYAN + "╚" + "═" * 62 + "╝\n" + Style.RESET_ALL)


def is_username_available(content: str, username: str) -> tuple:
    """توافق خلفي محدود لفحص HTML؛ الفحص الفعلي يتم عبر MTProto أدناه."""
    page = html_lib.unescape(content).lower()
    if "tgme_page_photo_image" in page or "tgme_page_extra" in page or "tgme_page_action" in page:
        return False, "محجوز/موجود"
    return None, "تعذر التحقق عبر صفحة الويب؛ يلزم فحص Telegram API"


async def verify_token_and_chat(session: aiohttp.ClientSession, token: str, chat_id: int):
    """التحقق من صحة التوكن ومراسلة الحساب لأول مرة."""
    me_url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with session.get(me_url, timeout=10) as resp:
            data = await resp.json()
            if not data.get("ok"):
                return False, "التوكن غير صالح! تأكد من نسخه بشكل صحيح من @BotFather.", None
            bot_username = data.get("result", {}).get("username")
    except Exception as e:
        return False, f"فشل الاتصال بسيرفرات تيليجرام: {e}", None

    msg_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": (
            "✅ <b>تم ربط لوحة التحكم بنجاح!</b>\n\n"
            "👨‍💻 <b>المطور:</b> جمال القفاف\n"
            "📸 <b>انستقرام:</b> @_vedt\n"
            "✈️ <b>تيليجرام:</b> @sn_ee\n\n"
            "⚡ <b>لوحة التحكم الإصدار Master v8.0:</b>\n"
            "• دعم كامل للثلاثيات (targets_3.txt) والسداسيات والخماسيات.\n"
            "• إمكانية تحديد اتجاه الفحص (من البداية ⬇️ أو من النهاية ⬆️).\n"
            "• إيقاف مؤقت واستئناف وتحكم فائق بالسرعة.\n"
            "• فحص فوري لأي يوزر ترسله في الشات."
        ),
        "parse_mode": "HTML"
    }

    try:
        async with session.post(msg_url, json=payload, timeout=10) as resp:
            data = await resp.json()
            if not data.get("ok"):
                desc = data.get("description", "")
                if "chat not found" in desc or "blocked" in desc:
                    return False, f"البوت (@{bot_username}) لا يمكنه مراسلتك! ادخل للبوت واضغط Start أولاً.", bot_username
                return False, f"خطأ من تيليجرام: {desc}", bot_username
    except Exception as e:
        return False, f"فشل إرسال رسالة التحقق: {e}", bot_username

    return True, "تم التحقق والاتصال بنجاح!", bot_username


async def setup_credentials():
    """معالج إعدادات تفاعلي لتخزين البيانات ومنع الأخطاء."""
    print_banner()
    saved = {}

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            t = saved.get("bot_token", "")
            c = saved.get("admin_id")
            api_id = saved.get("api_id")
            api_hash = saved.get("api_hash", "")
            phone = saved.get("phone_number", "")
            if t and c and api_id and api_hash and phone:
                print(Fore.GREEN + f"✓ تم العثور على إعدادات سابقة مسجلة للآيدي: {c}" + Style.RESET_ALL)
                print(Fore.CYAN + f"   الحساب الشخصي المحفوظ: {phone}" + Style.RESET_ALL)
                change = input(Fore.YELLOW + "[?] تغيير التوكن أو الآيدي أو رقم الهاتف؟ (y/N): " + Style.RESET_ALL).strip().lower()
                if change not in {"y", "yes", "نعم", "اي"}:
                    return t, int(c), int(api_id), api_hash, phone
        except Exception:
            pass

    print(Fore.CYAN + "┌" + "─" * 58 + "┐")
    print(Fore.CYAN + "│" + Fore.YELLOW + Style.BRIGHT + "          🛠️ معالج ضبط التوكن والآيدي الذكي          ".center(52) + Fore.CYAN + "│")
    print(Fore.CYAN + "└" + "─" * 58 + "┘" + Style.RESET_ALL)
    print(Fore.YELLOW + "يحتاج الفحص الدقيق api_id وapi_hash من my.telegram.org (مرة واحدة فقط)." + Style.RESET_ALL)
    if not TELETHON_AVAILABLE:
        print(Fore.RED + "❌ مكتبة Telethon غير مثبتة. ثبّتها بالأمر: pip install telethon" + Style.RESET_ALL)
        sys.exit(1)

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            token = input("\n" + Fore.GREEN + "[1] ألصق توكن البوت (Bot Token): " + Style.RESET_ALL).strip()
            token = token.replace("'", "").replace('"', "").replace("bot", "").strip()
            if ":" not in token:
                print(Fore.RED + "❌ صيغة التوكن غير صحيحة! تأكد من نسخه كاملاً من @BotFather." + Style.RESET_ALL)
                continue

            chat_id_raw = input(Fore.GREEN + "[2] أدخل الآيدي الخاص بك (Chat ID): " + Style.RESET_ALL).strip()
            chat_id_raw = chat_id_raw.replace("'", "").replace('"', "").strip()
            try:
                chat_id = int(chat_id_raw)
            except ValueError:
                print(Fore.RED + "❌ الآيدي يجب أن يتكون من أرقام فقط (مثال: 123456789)!" + Style.RESET_ALL)
                continue

            try:
                api_id = int(input(Fore.GREEN + "[3] أدخل api_id من my.telegram.org: " + Style.RESET_ALL).strip())
                api_hash = input(Fore.GREEN + "[4] أدخل api_hash من my.telegram.org: " + Style.RESET_ALL).strip()
                if api_id <= 0 or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
                    raise ValueError
            except ValueError:
                print(Fore.RED + "❌ api_id أو api_hash غير صالح. api_hash يجب أن يكون 32 رمزًا سداسيًا." + Style.RESET_ALL)
                continue

            phone = input(Fore.GREEN + "[5] أدخل رقم هاتف الحساب الشخصي مع مفتاح الدولة: " + Style.RESET_ALL).strip()
            phone = phone.replace(" ", "").replace("-", "")
            if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
                print(Fore.RED + "❌ رقم الهاتف يجب أن يكون بصيغة دولية مثل +9627XXXXXXXX." + Style.RESET_ALL)
                continue

            print(Fore.YELLOW + "\n[*] جارٍ اختبار التوكن والاتصال بالحساب..." + Style.RESET_ALL)
            ok, msg, bot_user = await verify_token_and_chat(session, token, chat_id)

            if ok:
                print(Fore.GREEN + Style.BRIGHT + f"✓ {msg} (اسم البوت: @{bot_user})" + Style.RESET_ALL)
                old_phone = saved.get("phone_number", "")
                api_changed = saved.get("api_id") != api_id or saved.get("api_hash", "") != api_hash
                if ((not old_phone and os.path.exists(USER_SESSION_FILE))
                        or (old_phone and old_phone != phone)
                        or api_changed):
                    if os.path.exists(USER_SESSION_FILE):
                        os.remove(USER_SESSION_FILE)
                        print(Fore.YELLOW + "✓ تم حذف جلسة الحساب القديمة لتسجيل الدخول بالبيانات الجديدة." + Style.RESET_ALL)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "bot_token": token,
                        "admin_id": chat_id,
                        "api_id": api_id,
                        "api_hash": api_hash,
                        "phone_number": phone,
                    }, f, indent=4)
                print(Fore.GREEN + f"✓ تم حفظ البيانات في {CONFIG_FILE} بنجاح!\n" + Style.RESET_ALL)
                return token, chat_id, api_id, api_hash, phone
            else:
                print(Fore.RED + f"❌ {msg}" + Style.RESET_ALL)
                retry = input(Fore.YELLOW + "[?] هل تريد إعادة المحاولة؟ (Y/n): " + Style.RESET_ALL).strip().lower()
                if retry in {"n", "no", "لا"}:
                    print(Fore.RED + "[!] تم إلغاء الإعداد." + Style.RESET_ALL)
                    sys.exit(1)


class DashboardBot:
    def __init__(self, token: str, admin_id: int, api_id: int, api_hash: str, phone_number: str):
        self.token = token
        self.admin_id = admin_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.mtproto = None
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    async def api_call(self, session: aiohttp.ClientSession, endpoint: str, data: dict):
        url = f"{self.api_url}/{endpoint}"
        try:
            async with session.post(url, json=data, timeout=15) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"خطأ في طلب {endpoint}: {e}")
            return {}

    async def send_document(self, session: aiohttp.ClientSession, file_path: str, caption: str):
        url = f"{self.api_url}/sendDocument"
        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(self.admin_id))
            data.add_field("caption", caption)
            data.add_field("parse_mode", "HTML")
            data.add_field("document", open(file_path, "rb"), filename=os.path.basename(file_path))
            async with session.post(url, data=data, timeout=30) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"فشل إرسال الملف: {e}")
            return {}

    async def check_user_online(self, session: aiohttp.ClientSession, username: str):
        username = username.strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
            return None, "صيغة اليوزر غير صالحة (5-32 حرفًا/رقمًا أو underscore)"
        if self.mtproto is None:
            return None, "فحص Telegram API غير متصل"

        try:
            result = await self.mtproto(tg_functions.account.CheckUsernameRequest(username=username))
            if bool(result):
                return True, "متاح للحجز العادي حسب Telegram API"
            return None, "نتيجة غير حاسمة من Telegram API"
        except UsernameOccupiedError:
            return False, "محجوز/موجود في Telegram API"
        except UsernamePurchaseAvailableError:
            return False, "Collectible ومتاح للشراء عبر Fragment، وليس متاحًا عاديًا"
        except UsernameInvalidError:
            return None, "اسم المستخدم غير صالح حسب Telegram API"
        except BotMethodInvalidError:
            return None, "BOT_SESSION: هذه الجلسة جلسة بوت؛ يلزم تسجيل دخول حساب شخصي"
        except FloodWaitError as e:
            return None, f"RATE_LIMIT:{max(1, int(e.seconds))}"
        except RPCError as e:
            return None, f"تعذر التحقق من Telegram API: {e.__class__.__name__}"
        except Exception as e:
            logger.error("MTProto username check failed: %s", e)
            return None, "تعذر التحقق من Telegram API"

    async def send_dashboard(self, session: aiohttp.ClientSession):
        dir_text = "من النهاية ⬆️" if scan_direction == "BOTTOM_TO_TOP" else "من البداية ⬇️"

        if state == "RUNNING":
            status_label = f"🟢 شغال الآن ({dir_text})"
        elif state == "PAUSED":
            status_label = "⏸ متوقف مؤقتاً"
        else:
            status_label = "🔴 متوقف تماماً"

        if speed_profile == "TURBO":
            speed_str = "⚡ تيربو صاروخي (0.2s)"
        elif speed_profile == "FAST":
            speed_str = "🚀 سريع (0.4s)"
        else:
            speed_str = "🛡️ آمن (0.8s)"

        dashboard_text = (
            f"🎛 <b>لوحة تحكم رادار اليوزرات الاحترافي (v8.0 Master)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>المطور:</b> جمال القفاف\n"
            f"📸 <b>انستقرام:</b> @_vedt | ✈️ <b>تيليجرام:</b> @sn_ee\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <b>حالة الفاحص:</b> {status_label}\n"
            f"📂 <b>الملف الحالي:</b> <code>{current_target_file or 'لم يُحدد'}</code>\n"
            f"🔄 <b>اتجاه الفحص المختار:</b> <b>{dir_text}</b>\n"
            f"⏱ <b>السرعة:</b> {speed_str}\n"
            f"🔢 <b>تم فحصه:</b> <code>{stats['checked']:,} / {stats['total']:,}</code>\n"
            f"🎉 <b>المتاح المكتشف:</b> <code>{stats['available']:,}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>أرسل أي يوزر للمحادثة الآن لفحصه فوراً وبشكل مستقل!</i>"
        )

        direction_btn_text = "🔄 الاتجاه: من النهاية ⬆️" if scan_direction == "BOTTOM_TO_TOP" else "🔄 الاتجاه: من البداية ⬇️"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔥 ثلاثيات (targets_3.txt)", "callback_data": "start_targets_3.txt"},
                    {"text": "🚀 سداسيات (targets_6.txt)", "callback_data": "start_targets_6.txt"}
                ],
                [
                    {"text": "⚡ خماسيات (targets_5.txt)", "callback_data": "start_targets_5.txt"}
                ],
                [
                    {"text": "⏸ إيقاف مؤقت", "callback_data": "pause_checker"},
                    {"text": "▶️ استئناف", "callback_data": "resume_checker"},
                    {"text": "⏹ إنهاء الفحص", "callback_data": "stop_checker"}
                ],
                [
                    {"text": direction_btn_text, "callback_data": "toggle_direction"},
                    {"text": f"🎚 السرعة: {speed_profile}", "callback_data": "cycle_speed"}
                ],
                [
                    {"text": "📊 تحديث اللوحة", "callback_data": "refresh_panel"},
                    {"text": "📥 تنزيل المتاح (.txt)", "callback_data": "export_file"}
                ],
                [
                    {"text": "🗑 تفريغ ملف المتاح", "callback_data": "clear_results"}
                ]
            ]
        }

        await self.api_call(session, "sendMessage", {
            "chat_id": self.admin_id,
            "text": dashboard_text,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        })

    async def run_checker(self, session: aiohttp.ClientSession, filename: str):
        """محرك الفحص الذي يلتزم بالاتجاه والسرعة وحماية الـ Rate Limit."""
        global state, stats, current_target_file
        state = "RUNNING"
        current_target_file = filename
        stats = {"checked": 0, "available": 0, "total": 0, "start_time": datetime.now()}

        if not os.path.exists(filename):
            state = "IDLE"
            await self.api_call(session, "sendMessage", {
                "chat_id": self.admin_id,
                "text": f"❌ خطأ: الملف <code>{filename}</code> غير موجود في المجلد الحالي!",
                "parse_mode": "HTML"
            })
            return

        with open(filename, "r", encoding="utf-8") as f:
            targets = [line.strip().lstrip("@") for line in f if line.strip() and not line.startswith("#")]

        # تطبيق الاتجاه المختار
        if scan_direction == "BOTTOM_TO_TOP":
            targets.reverse()
            dir_desc = "من أسفل الملف إلى أعلاه ⬆️"
        else:
            dir_desc = "من بداية الملف إلى نهايته ⬇️"

        stats["total"] = len(targets)

        print(Fore.GREEN + f"\n[+] انطلق الفحص لملف {filename} ({dir_desc}) | الأهداف: {stats['total']:,}" + Style.RESET_ALL)
        await self.api_call(session, "sendMessage", {
            "chat_id": self.admin_id,
            "text": f"🚀 <b>بدأ الفحص الآن!</b>\n📂 الملف: <code>{filename}</code>\n🔄 الاتجاه: <b>{dir_desc}</b>\n🎯 الإجمالي: <code>{stats['total']:,}</code> يوزر.",
            "parse_mode": "HTML"
        })

        for idx, username in enumerate(targets, 1):
            if state == "IDLE":
                break

            while state == "PAUSED":
                await asyncio.sleep(0.8)
                if state == "IDLE":
                    break

            if state == "IDLE":
                break

            now = datetime.now().strftime("%H:%M:%S")

            # لا نتخطى اليوزر عند FloodWait؛ نعيد نفس الطلب بعد المدة التي
            # يحددها تيليجرام، ولا نضيف استراحة ثابتة من عندنا.
            while True:
                is_avail, desc = await self.check_user_online(session, username)
                if is_avail is not None:
                    break

                rate_match = re.fullmatch(r"RATE_LIMIT:(\d+)", str(desc))
                if not rate_match:
                    break

                wait_seconds = int(rate_match.group(1))
                print(Fore.YELLOW + f"[!] تيليجرام طلب انتظار {wait_seconds} ثانية؛ سيتم استكمال نفس اليوزر تلقائياً." + Style.RESET_ALL)
                await asyncio.sleep(wait_seconds)

            stats["checked"] += 1

            if is_avail is True:
                stats["available"] += 1
                with open(RESULTS_FILE, "a", encoding="utf-8") as out:
                    out.write(f"{username}\n")

                print(f"[{now}] ({idx:,}/{stats['total']:,}) @{username:<15} ➜ {Fore.GREEN + Style.BRIGHT}متاح للتسجيل! 🎉{Style.RESET_ALL}")
                
                await self.api_call(session, "sendMessage", {
                    "chat_id": self.admin_id,
                    "text": (
                        f"🎉 <b>يوزر متاح للتسجيل ومؤكد 100%!</b>\n\n"
                        f"👤 <b>اليوزر:</b> <code>@{username}</code>\n"
                        f"⏰ <b>التوقيت:</b> <code>{now}</code>\n"
                        f"👨‍💻 <b>المطور:</b> جمال القفاف (@_vedt)\n\n"
                        f"⚡ <i>سارع بالتسجيل من التطبيق فوراً!</i>"
                    ),
                    "parse_mode": "HTML"
                })
            elif is_avail is False:
                print(f"[{now}] ({idx:,}/{stats['total']:,}) @{username:<15} ➜ {Fore.LIGHTBLACK_EX}محجوز{Style.RESET_ALL}")
            else:
                if str(desc).startswith("BOT_SESSION:"):
                    state = "IDLE"
                    await self.api_call(session, "sendMessage", {
                        "chat_id": self.admin_id,
                        "text": "❌ تم إيقاف الفحص: جلسة Telegram API الحالية بوت. احذف ملف username_checker_user.session وسجّل دخول حساب شخصي برقم الهاتف مرة واحدة.",
                        "parse_mode": "HTML"
                    })
                    break
                print(Fore.YELLOW + f"[{now}] تعذر التحقق لهذا اليوزر: {desc}" + Style.RESET_ALL)

            # زمن التأخير حسب البروفايل
            if speed_profile == "TURBO":
                base_delay = 0.20
            elif speed_profile == "FAST":
                base_delay = 0.40
            else:
                base_delay = 0.80

            await asyncio.sleep(base_delay + random.uniform(0.02, 0.08))

        state = "IDLE"
        print(Fore.CYAN + f"\n[!] انتهى فحص الملف {filename} بالكامل." + Style.RESET_ALL)
        await self.api_call(session, "sendMessage", {
            "chat_id": self.admin_id,
            "text": f"🏁 <b>اكتمل فحص الملف:</b> <code>{filename}</code>\n🎉 <b>المتاح المكتشف:</b> <code>{stats['available']}</code>",
            "parse_mode": "HTML"
        })

    async def handle_callback(self, session: aiohttp.ClientSession, query: dict):
        """معالجة جميع ضغطات الأزرار من الأدمن."""
        global current_task, state, speed_profile, scan_direction
        sender_id = query.get("from", {}).get("id")
        qid = query.get("id")
        data = query.get("data", "")

        if sender_id != self.admin_id:
            return

        if data.startswith("start_"):
            target_f = data.replace("start_", "")
            if state == "RUNNING":
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "⚠️ الفحص يعمل بالفعل حالياً!"
                })
                return
            current_task = asyncio.create_task(self.run_checker(session, target_f))
            await self.api_call(session, "answerCallbackQuery", {
                "callback_query_id": qid,
                "text": f"تم بدء فحص {target_f}"
            })
            await self.send_dashboard(session)

        elif data == "toggle_direction":
            scan_direction = "TOP_TO_BOTTOM" if scan_direction == "BOTTOM_TO_TOP" else "BOTTOM_TO_TOP"
            d_name = "من البداية ⬇️" if scan_direction == "TOP_TO_BOTTOM" else "من النهاية ⬆️"
            await self.api_call(session, "answerCallbackQuery", {
                "callback_query_id": qid,
                "text": f"تم ضبط الاتجاه: {d_name}"
            })
            await self.send_dashboard(session)

        elif data == "pause_checker":
            if state == "RUNNING":
                state = "PAUSED"
                print(Fore.YELLOW + "[!] تم إيقاف الفحص مؤقتاً." + Style.RESET_ALL)
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "⏸ تم إيقاف الفحص مؤقتاً."
                })
                await self.send_dashboard(session)
            else:
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "الفاحص ليس قيد التشغيل حالياً."
                })

        elif data == "resume_checker":
            if state == "PAUSED":
                state = "RUNNING"
                print(Fore.GREEN + "[!] تم استئناف الفحص بنجاح." + Style.RESET_ALL)
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "▶️ تم استئناف الفحص."
                })
                await self.send_dashboard(session)
            else:
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "الفاحص ليس موقوفاً مؤقتاً."
                })

        elif data == "stop_checker":
            if state in {"RUNNING", "PAUSED"}:
                state = "IDLE"
                if current_task:
                    current_task.cancel()
                print(Fore.RED + "[!] تم إنهاء الفحص يدوياً." + Style.RESET_ALL)
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "⏹ تم إنهاء الفحص بنجاح."
                })
                await self.send_dashboard(session)
            else:
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "الفاحص متوقف أصلاً."
                })

        elif data == "cycle_speed":
            modes = ["TURBO", "FAST", "SAFE"]
            idx = modes.index(speed_profile)
            speed_profile = modes[(idx + 1) % len(modes)]
            await self.api_call(session, "answerCallbackQuery", {
                "callback_query_id": qid,
                "text": f"السرعة الحالية: {speed_profile}"
            })
            await self.send_dashboard(session)

        elif data == "refresh_panel":
            await self.send_dashboard(session)
            await self.api_call(session, "answerCallbackQuery", {
                "callback_query_id": qid,
                "text": "تم تحديث اللوحة"
            })

        elif data == "export_file":
            if os.path.exists(RESULTS_FILE) and os.path.getsize(RESULTS_FILE) > 0:
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "جارٍ إرسال الملف..."
                })
                await self.send_document(
                    session,
                    RESULTS_FILE,
                    f"📁 <b>ملف اليوزرات المتاحة المحفوظة</b>\n👨‍💻 المطور: جمال القفاف (@_vedt)"
                )
            else:
                await self.api_call(session, "answerCallbackQuery", {
                    "callback_query_id": qid,
                    "text": "لا توجد يوزرات متاحة مسجلة حتى الآن."
                })

        elif data == "clear_results":
            if os.path.exists(RESULTS_FILE):
                os.remove(RESULTS_FILE)
            stats["available"] = 0
            await self.api_call(session, "answerCallbackQuery", {
                "callback_query_id": qid,
                "text": "تم مسح وتفريغ ملف المتاح بنجاح."
            })
            await self.send_dashboard(session)

    async def handle_message(self, session: aiohttp.ClientSession, msg: dict):
        sender_id = msg.get("from", {}).get("id")
        if sender_id != self.admin_id:
            return

        text = msg.get("text", "").strip()

        if text in {"/start", "لوحة التحكم", "/panel", "panel"}:
            await self.send_dashboard(session)
            return

        if text == "/status":
            uptime_str = str(datetime.now() - stats["start_time"]).split(".")[0] if stats["start_time"] else "متوقف"
            dir_text = "من النهاية ⬆️" if scan_direction == "BOTTOM_TO_TOP" else "من البداية ⬇️"
            msg_text = (
                f"📊 <b>تقرير الحالة المباشر:</b>\n"
                f"• حالة النظام: <code>{state}</code>\n"
                f"• مدة الجلسة: <code>{uptime_str}</code>\n"
                f"• الاتجاه المعتمد: <b>{dir_text}</b>\n"
                f"• المفحوص: <code>{stats['checked']:,} / {stats['total']:,}</code>\n"
                f"• المتاح: <code>{stats['available']:,}</code>\n"
                f"• بروفايل السرعة: <code>{speed_profile}</code>"
            )
            await self.api_call(session, "sendMessage", {
                "chat_id": self.admin_id,
                "text": msg_text,
                "parse_mode": "HTML"
            })
            return

        # فحص مباشر: يوزر فردي أو قائمة سطور
        lines = [line.strip().lstrip("@") for line in text.split("\n") if line.strip()]
        if lines:
            if len(lines) == 1:
                u = lines[0]
                await self.api_call(session, "sendMessage", {
                    "chat_id": self.admin_id,
                    "text": f"🔍 جارٍ فحص اليوزر: <code>@{u}</code>...",
                    "parse_mode": "HTML"
                })
                is_avail, desc = await self.check_user_online(session, u)
                if is_avail is True:
                    resp_text = (
                        f"🎉 <b>النتيجة: اليوزر متاح للتسجيل!</b>\n\n"
                        f"👤 <b>اليوزر:</b> <code>@{u}</code>\n"
                        f"✅ <b>التأكيد:</b> متاح 100% في قاعدة تيليجرام\n"
                        f"👨‍💻 <b>المطور:</b> جمال القفاف"
                    )
                elif is_avail is False:
                    resp_text = (
                        f"❌ <b>النتيجة: اليوزر غير متاح!</b>\n\n"
                        f"👤 <b>اليوزر:</b> <code>@{u}</code>\n"
                        f"ℹ️ <b>الحالة:</b> {desc}"
                    )
                else:
                    resp_text = f"⚠️ تعذر الفحص حالياً لليوزر @{u}: {desc}"

                await self.api_call(session, "sendMessage", {
                    "chat_id": self.admin_id,
                    "text": resp_text,
                    "parse_mode": "HTML"
                })
            else:
                targets_batch = lines[:50]
                await self.api_call(session, "sendMessage", {
                    "chat_id": self.admin_id,
                    "text": f"⏳ جارٍ فحص قائمة سريعة مكونة من {len(targets_batch)} يوزر...",
                    "parse_mode": "HTML"
                })
                found = []
                for tu in targets_batch:
                    is_av, _ = await self.check_user_online(session, tu)
                    if is_av is True:
                        found.append(tu)
                    await asyncio.sleep(0.2)

                if found:
                    found_str = "\n".join([f"• <code>@{x}</code>" for x in found])
                    res_msg = f"🎉 <b>اليوزرات المتاحة المكتشفة ({len(found)}):</b>\n\n{found_str}"
                else:
                    res_msg = "❌ جميع اليوزرات في القائمة المرسلة محجوزة أو غير صالحة."

                await self.api_call(session, "sendMessage", {
                    "chat_id": self.admin_id,
                    "text": res_msg,
                    "parse_mode": "HTML"
                })

    async def start(self):
        offset = 0
        connector = aiohttp.TCPConnector(ssl=False)
        if not TELETHON_AVAILABLE:
            raise RuntimeError("Telethon غير مثبتة. شغّل: pip install telethon")

        # اسم جديد حتى لا يعيد Telethon استخدام جلسة بوت قديمة.
        self.mtproto = TelegramClient("username_checker_user_v2", self.api_id, self.api_hash)
        await self.mtproto.start(phone=self.phone_number)
        me = await self.mtproto.get_me()
        if getattr(me, "bot", False):
            await self.mtproto.disconnect()
            self.mtproto = None
            raise RuntimeError(
                "تم تسجيل الدخول بجلسة بوت. احذف username_checker_user_v2.session "
                "وسجّل الدخول برقم هاتف حساب Telegram شخصي."
            )
        print(Fore.GREEN + f"[*] تم تشغيل فحص Telegram API عبر الحساب @{me.username or me.id}." + Style.RESET_ALL)

        async with aiohttp.ClientSession(connector=connector) as session:
            print(Fore.GREEN + f"[*] لوحة التحكم متصلة بحسابك (ID: {self.admin_id}) وتعمل الآن..." + Style.RESET_ALL)
            print(Fore.CYAN + "[*] يمكنك كتابة /start في البوت أو استخدام الأزرار في أي وقت.\n" + Style.RESET_ALL)

            await self.send_dashboard(session)

            while True:
                try:
                    updates = await self.api_call(session, "getUpdates", {"offset": offset, "timeout": 20})
                    for item in updates.get("result", []):
                        offset = item["update_id"] + 1

                        if "message" in item:
                            await self.handle_message(session, item["message"])

                        elif "callback_query" in item:
                            await self.handle_callback(session, item["callback_query"])

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"خطأ أثناء استقبال التحديثات: {e}")
                    await asyncio.sleep(2)
        await self.mtproto.disconnect()


async def main():
    token, admin_id, api_id, api_hash, phone_number = await setup_credentials()
    bot = DashboardBot(token, admin_id, api_id, api_hash, phone_number)
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n[!] تم إيقاف لوحة التحكم بنجاح." + Style.RESET_ALL)
