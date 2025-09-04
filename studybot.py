import json
import os
from typing import Dict, Any, List
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =================== CONFIG ===================

TOKEN = "7714600486:AAEdqqXvADjwb5rzr907NLHEi2i4jVKHq9s"
OWNER_ID = 6651946441
DATA_FILE = "materials.json"

# =================== DATA MODEL ===================

DEFAULT_STRUCTURE: Dict[str, Any] = {
    "_meta": {"admins": [OWNER_ID], "users": []},
    "IIT JEE": {
        "Physics": {},
        "Chemistry": {},
        "Math": {},
    },
    "NEET": {
        "Physics": {},
        "Chemistry": {},
        "Biology": {},
    },
}

def load_materials() -> Dict[str, Any]:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = DEFAULT_STRUCTURE.copy()
            
        # ensure _meta
        data.setdefault("_meta", {"admins": [OWNER_ID], "users": []})
        
        # ensure top-level exams and subjects from default
        for exam, subjects in DEFAULT_STRUCTURE.items():
            if exam == "_meta":
                continue
            data.setdefault(exam, {})
            for subject, pubs in subjects.items():
                if isinstance(data[exam], dict):
                    data[exam].setdefault(subject, {})
                
        return data
    except Exception as e:
        print(f"Error loading materials: {e}")
        return DEFAULT_STRUCTURE.copy()

def save_materials() -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(MATERIALS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving materials: {e}")

MATERIALS: Dict[str, Any] = load_materials()

# user_state keeps temporary interaction states
user_state: Dict[int, Dict[str, Any]] = {}

# =================== KEYBOARDS ===================

def kb(rows: List[List[str]]):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def main_menu_kb():
    return kb([["📘 IIT JEE", "📗 NEET"], ["👥 Community", "ℹ️ Credits"]])

def exams_from_data() -> List[str]:
    return [k for k in MATERIALS.keys() if k != "_meta" and isinstance(MATERIALS[k], dict)]

def subjects_for_exam(exam: str) -> List[str]:
    exam_data = MATERIALS.get(exam, {})
    if isinstance(exam_data, dict):
        return sorted(list(exam_data.keys()))
    return []

def publishers_for(exam: str, subject: str) -> List[str]:
    exam_data = MATERIALS.get(exam, {})
    if isinstance(exam_data, dict):
        subject_data = exam_data.get(subject, {})
        if isinstance(subject_data, dict):
            return sorted(list(subject_data.keys()))
    return []

def chunk(lst: List[str], n: int) -> List[List[str]]:
    return [lst[i:i+n] for i in range(0, len(lst), n)]

def subjects_kb(exam: str):
    items = subjects_for_exam(exam)
    rows = chunk(items, 3)
    rows.append(["⬅️ Back", "🏠 Menu"])
    return kb(rows)

def publishers_kb(exam: str, subject: str, include_add: bool = False):
    items = publishers_for(exam, subject)
    if include_add:
        items = ["➕ Add New Publisher"] + items
    rows = chunk(items, 3)
    rows.append(["⬅️ Back", "🏠 Menu"])
    return kb(rows)

# =================== HELPERS ===================

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    admins = MATERIALS.get("_meta", {}).get("admins", [])
    return user_id in admins

def add_user_to_meta(user_id: int):
    users = MATERIALS.setdefault("_meta", {}).setdefault("users", [])
    if user_id not in users:
        users.append(user_id)
        save_materials()

def reset_state(user_id: int):
    user_state[user_id] = {
        "mode": None,
        "step": None,
        "exam": None,
        "subject": None,
        "publisher": None,
        "awaiting_new_publisher_name": False,
        "upload_active": False,
        "awaiting_text": False,
    }

def ensure_publisher(exam: str, subject: str, publisher: str):
    if exam not in MATERIALS:
        MATERIALS[exam] = {}
    if subject not in MATERIALS[exam]:
        MATERIALS[exam][subject] = {}
    if publisher not in MATERIALS[exam][subject]:
        MATERIALS[exam][subject][publisher] = []

def ensure_subject(exam: str, subject: str):
    if exam not in MATERIALS:
        MATERIALS[exam] = {}
    if subject not in MATERIALS[exam]:
        MATERIALS[exam][subject] = {}

def ensure_exam(exam: str):
    if exam not in MATERIALS:
        MATERIALS[exam] = {}

# =================== COMMANDS ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        reset_state(uid)
    add_user_to_meta(uid)
    await update.message.reply_text(
        "Welcome! Choose an option 👇",
        reply_markup=main_menu_kb()
    )

async def cmd_addmaterial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ You are not authorized.")
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "add"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    if not exams:
        await update.message.reply_text("No exams found. Admin can add exams using /addsubject with an exam name and subject.")
        return
        
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text("Select Exam:", reply_markup=kb(rows))

async def cmd_deletefile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ You are not authorized.")
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_file"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text("🗑️ Delete File → Select Exam:", reply_markup=kb(rows))

async def cmd_deletepublisher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ You are not authorized.")
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_publisher"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text("🗑️ Delete Publisher → Select Exam:", reply_markup=kb(rows))

async def cmd_addsubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Only admins can add subjects.")
        return
        
    text = " ".join(context.args) if context.args else ""
    if ">" in text:
        parts = [p.strip() for p in text.split(">")]
        if len(parts) >= 2:
            exam = parts[0]
            subject = parts[1]
            ensure_subject(exam, subject)
            save_materials()
            await update.message.reply_text(f"✅ Subject '{subject}' added under exam '{exam}'.")
            return
            
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "add_subject"
    st["step"] = "ask_exam"
    await update.message.reply_text("Send exam name (existing or new) for which you want to add a subject:")

async def cmd_deletesubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Only admins can delete subjects.")
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_subject"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text("Select Exam to delete a subject from:", reply_markup=kb(rows))

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text("❌ Only bot owner can add admins.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <telegram_user_id>")
        return
        
    try:
        new_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Provide a numeric Telegram user id.")
        return
        
    admins = MATERIALS.setdefault("_meta", {}).setdefault("admins", [])
    if new_admin in admins:
        await update.message.reply_text("⚠️ This user is already an admin.")
        return
        
    admins.append(new_admin)
    save_materials()
    await update.message.reply_text(f"✅ Added admin: {new_admin}")

async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text("❌ Only bot owner can remove admins.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <telegram_user_id>")
        return
        
    try:
        rem = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Provide a numeric Telegram user id.")
        return
        
    admins = MATERIALS.setdefault("_meta", {}).setdefault("admins", [])
    if rem not in admins:
        await update.message.reply_text("⚠️ This user is not an admin.")
        return
        
    admins.remove(rem)
    save_materials()
    await update.message.reply_text(f"✅ Removed admin: {rem}")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text("❌ Only bot owner can broadcast messages.")
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "broadcast"
    st["step"] = "await_text"
    st["awaiting_text"] = True
    await update.message.reply_text("✉️ Send the message you want to broadcast to all users. It can be text only.")

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = user_state.get(uid)
    if not st:
        await update.message.reply_text("ℹ️ Nothing to finish.")
        return
        
    if st.get("mode") == "add" and st.get("upload_active"):
        st["upload_active"] = False
        await update.message.reply_text(f"✅ Upload finished for {st['exam']} > {st['subject']} > {st['publisher']}")
        return
        
    await update.message.reply_text("✅ Done.")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    reset_state(uid)
    await update.message.reply_text("❎ Cancelled.", reply_markup=main_menu_kb())

# =================== FILE HANDLER (UPLOAD) ===================

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = user_state.get(uid)
    
    if not st or st.get("mode") != "add" or not st.get("upload_active"):
        return
        
    exam = st["exam"]
    subject = st["subject"]
    publisher = st["publisher"]
    
    file_id = None
    ftype = None
    fname = None
    
    if update.message.document:
        file_id = update.message.document.file_id
        ftype = "document"
        fname = update.message.document.file_name
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        ftype = "photo"
        fname = "photo.jpg"
    elif update.message.video:
        file_id = update.message.video.file_id
        ftype = "video"
        fname = getattr(update.message.video, "file_name", "video.mp4")
        
    if file_id:
        ensure_publisher(exam, subject, publisher)
        MATERIALS[exam][subject][publisher].append({
            "id": file_id,
            "type": ftype,
            "name": fname or ftype,
            "caption": update.message.caption or "",
        })
        save_materials()
        await update.message.reply_text(f"✅ Saved to {exam} > {subject} > {publisher}")
    else:
        await update.message.reply_text("❌ Only PDF/Image/Video allowed.")

# =================== TEXT HANDLER (STATE MACHINE + PUBLIC BROWSING) ===================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = (update.message.text or "").strip()
    
    if uid not in user_state:
        reset_state(uid)
        
    st = user_state[uid]

    add_user_to_meta(uid)

    if txt in ("🏠 Menu", "Menu", "/menu"):
        reset_state(uid)
        await update.message.reply_text("Main Menu:", reply_markup=main_menu_kb())
        return
        
    if txt == "⬅️ Back":
        if st["step"] == "choose_subject":
            st["step"] = "choose_exam"
            st["exam"] = None
            exams = exams_from_data()
            rows = chunk(exams, 2)
            rows.append(["🏠 Menu"])
            await update.message.reply_text("Select Exam:", reply_markup=kb(rows))
            return
        elif st["step"] == "choose_publisher":
            st["step"] = "choose_subject"
            st["subject"] = None
            await update.message.reply_text(f"{st['exam']} – Select Subject:", reply_markup=subjects_kb(st["exam"]))
            return
        elif st["step"] == "choose_file":
            st["step"] = "choose_publisher"
            st["publisher"] = None
            await update.message.reply_text(
                f"{st['exam']} > {st['subject']} – Select Publisher:",
                reply_markup=publishers_kb(st["exam"], st["subject"], include_add=(st["mode"]=="add"))
            )
            return
            
        reset_state(uid)
        await update.message.reply_text("Main Menu:", reply_markup=main_menu_kb())
        return

    if st.get("mode") == "add":
        if st.get("awaiting_new_publisher_name"):
            new_pub = txt
            if new_pub in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text("⚠️ Publisher already exists. Choose another name.")
                return
                
            ensure_publisher(st["exam"], st["subject"], new_pub)
            save_materials()
            st["publisher"] = new_pub
            st["awaiting_new_publisher_name"] = False
            st["upload_active"] = True
            st["step"] = "choose_file"
            await update.message.reply_text(
                f"✅ Publisher \"{new_pub}\" created. Now send files (PDF/Image/Video).\n\nSend /done when finished.", 
                reply_markup=kb([["⬅️ Back", "🏠 Menu"]])
            )
            return
            
        if st["step"] == "choose_exam":
            if txt not in exams_from_data():
                await update.message.reply_text("❌ Invalid exam. Choose from buttons.")
                return
                
            st["exam"] = txt
            st["step"] = "choose_subject"
            await update.message.reply_text(f"{st['exam']} – Select Subject:", reply_markup=subjects_kb(st["exam"]))
            return
            
        if st["step"] == "choose_subject":
            if txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text("❌ Invalid subject. Choose from buttons.")
                return
                
            st["subject"] = txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(
                f"{st['exam']} > {st['subject']} – Select Publisher or add new:",
                reply_markup=publishers_kb(st["exam"], st["subject"], include_add=True)
            )
            return
            
        if st["step"] == "choose_publisher":
            if txt == "➕ Add New Publisher":
                st["awaiting_new_publisher_name"] = True
                await update.message.reply_text("✍️ Send the new publisher name:", reply_markup=kb([["⬅️ Back", "🏠 Menu"]]))
                return
                
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text("❌ Invalid publisher. Choose from buttons or add new.")
                return
                
            st["publisher"] = txt
            st["upload_active"] = True
            st["step"] = "choose_file"
            await update.message.reply_text(
                f"📤 Upload mode ON for {st['exam']} > {st['subject']} > {st['publisher']}\nSend files now. Use /done when finished.", 
                reply_markup=kb([["⬅️ Back", "🏠 Menu"]])
            )
            return
            
        if st["step"] == "choose_file":
            await update.message.reply_text("ℹ️ Send PDF/Image/Video files. Use /done when finished.")
            return

    if st.get("mode") == "delete_publisher":
        if st["step"] == "choose_exam":
            if txt not in exams_from_data():
                await update.message.reply_text("❌ Invalid exam. Choose from buttons.")
                return
                
            st["exam"] = txt
            st["step"] = "choose_subject"
            await update.message.reply_text(f"{st['exam']} – Select Subject:", reply_markup=subjects_kb(st["exam"]))
            return
            
        if st["step"] == "choose_subject":
            if txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text("❌ Invalid subject. Choose from buttons.")
                return
                
            st["subject"] = txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(f"{st['exam']} > {st['subject']} – Select Publisher to DELETE:", reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return
            
        if st["step"] == "choose_publisher":
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text("❌ Invalid publisher. Choose from buttons.")
                return
                
            del MATERIALS[st["exam"]][st["subject"]][txt]
            save_materials()
            await update.message.reply_text(f"✅ Deleted publisher \"{txt}\" from {st['exam']} > {st['subject']}", reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return

    if st.get("mode") == "delete_file":
        if st["step"] == "choose_exam":
            if txt not in exams_from_data():
                await update.message.reply_text("❌ Invalid exam. Choose from buttons.")
                return
                
            st["exam"] = txt
            st["step"] = "choose_subject"
            await update.message.reply_text(f"{st['exam']} – Select Subject:", reply_markup=subjects_kb(st["exam"]))
            return
            
        if st["step"] == "choose_subject":
            if txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text("❌ Invalid subject. Choose from buttons.")
                return
                
            st["subject"] = txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(f"{st['exam']} > {st['subject']} – Select Publisher:", reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return
            
        if st["step"] == "choose_publisher":
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text("❌ Invalid publisher. Choose from buttons.")
                return
                
            st["publisher"] = txt
            st["step"] = "choose_file"
            items = MATERIALS.get(st["exam"], {}).get(st["subject"], {}).get(st["publisher"], [])
            if not items:
                await update.message.reply_text("⚠️ No files in this publisher.")
                return
                
            lines = ["Select file number to DELETE:"]
            for i, it in enumerate(items, start=1):
                label = it.get("name") or it.get("type") or "file"
                lines.append(f"{i}. {label}")
                
            await update.message.reply_text("\n".join(lines), reply_markup=kb([["⬅️ Back", "🏠 Menu"]]))
            return
            
        if st["step"] == "choose_file":
            items = MATERIALS.get(st["exam"], {}).get(st["subject"], {}).get(st["publisher"], [])
            try:
                idx = int(txt) - 1
            except ValueError:
                await update.message.reply_text("❌ Send a valid number from the list.")
                return
                
            if idx < 0 or idx >= len(items):
                await update.message.reply_text("❌ Number out of range.")
                return
                
            removed = items.pop(idx)
            save_materials()
            await update.message.reply_text(f"✅ Deleted: {removed.get('name') or removed.get('type')}")
            
            if not items:
                await update.message.reply_text("(Folder now empty)")
            else:
                lines = ["Remaining files:"]
                for i, it in enumerate(items, start=1):
                    label = it.get("name") or it.get("type") or "file"
                    lines.append(f"{i}. {label}")
                await update.message.reply_text("\n".join(lines))
            return

    if st.get("mode") == "add_subject":
        if st.get("step") == "ask_exam":
            exam = txt
            st["exam"] = exam
            st["step"] = "ask_subject"
            await update.message.reply_text(f"Send subject name to add under exam '{exam}':", reply_markup=kb([["⬅️ Back", "🏠 Menu"]]))
            return
            
        if st.get("step") == "ask_subject":
            subject = txt
            ensure_subject(st["exam"], subject)
            save_materials()
            await update.message.reply_text(f"✅ Subject '{subject}' added under exam '{st['exam']}'")
            reset_state(uid)
            return

    if st.get("mode") == "delete_subject":
        if st.get("step") == "choose_exam":
            if txt not in exams_from_data():
                await update.message.reply_text("❌ Invalid exam. Choose from buttons.")
                return
                
            st["exam"] = txt
            st["step"] = "choose_subject_to_delete"
            await update.message.reply_text(f"Select subject to DELETE from {txt}:", reply_markup=subjects_kb(txt))
            return
            
        if st.get("step") == "choose_subject_to_delete":
            if txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text("❌ Invalid subject.")
                return
                
            del MATERIALS[st["exam"]][txt]
            save_materials()
            await update.message.reply_text(f"✅ Deleted subject '{txt}' from exam '{st['exam']}'")
            reset_state(uid)
            return

    if st.get("mode") == "broadcast" and st.get("awaiting_text"):
        msg = txt
        users = MATERIALS.get("_meta", {}).get("users", [])
        sent = 0
        failed = 0
        
        for u in users:
            try:
                await context.bot.send_message(int(u), msg)
                sent += 1
            except Exception:
                failed += 1
                
        await update.message.reply_text(f"📣 Broadcast complete. Sent: {sent}, Failed: {failed}")
        reset_state(uid)
        return

    if txt == "📘 IIT JEE":
        await update.message.reply_text("IIT JEE – Subjects:", reply_markup=subjects_kb("IIT JEE"))
        return
    elif txt == "📗 NEET":
        await update.message.reply_text("NEET – Subjects:", reply_markup=subjects_kb("NEET"))
        return
    elif txt == "👥 Community":
        await update.message.reply_text("Join our Community: https://t.me/yourcommunity")
        return
    elif txt == "ℹ️ Credits":
        await update.message.reply_text("This bot is created by Admin.")
        return

    for exam in exams_from_data():
        if txt in subjects_for_exam(exam):
            await update.message.reply_text(f"{exam} > {txt} – Publishers:", reply_markup=publishers_kb(exam, txt))
            return

    for exam in exams_from_data():
        for subject in subjects_for_exam(exam):
            if txt in publishers_for(exam, subject):
                files = MATERIALS.get(exam, {}).get(subject, {}).get(txt, [])
                if files:
                    for item in files:
                        fid = item.get("id")
                        ftype = item.get("type")
                        if ftype == "document":
                            await update.message.reply_document(fid, caption=item.get("caption", ""))
                        elif ftype == "photo":
                            await update.message.reply_photo(fid, caption=item.get("caption", ""))
                        elif ftype == "video":
                            await update.message.reply_video(fid, caption=item.get("caption", ""))
                    return
                else:
                    await update.message.reply_text("⚠️ No materials uploaded yet.")
                    return

    await update.message.reply_text("Please choose from menu 👇", reply_markup=main_menu_kb())

# =================== MAIN ===================

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addmaterial", cmd_addmaterial))
    application.add_handler(CommandHandler("deletefile", cmd_deletefile))
    application.add_handler(CommandHandler("deletepublisher", cmd_deletepublisher))
    application.add_handler(CommandHandler("addsubject", cmd_addsubject))
    application.add_handler(CommandHandler("deletesubject", cmd_deletesubject))
    application.add_handler(CommandHandler("addadmin", cmd_addadmin))
    application.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    application.add_handler(CommandHandler("broadcast", cmd_broadcast))
    application.add_handler(CommandHandler("done", cmd_done))
    application.add_handler(CommandHandler("cancel", cmd_cancel))

    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_files))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot is starting...")
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30,
        )
    except Exception as e:
        print(f"Error: {e}")
        print("Restarting in 5 seconds...")
        import time
        time.sleep(5)
        main()

if __name__ == "__main__":
    main()
