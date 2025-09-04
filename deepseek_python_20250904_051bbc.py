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

TOKEN = "7714600486:AAEZxM0HKDW_F49lM0MpUUWfZo0JTQUQ4j4"
OWNER_ID = 6651946441
DATA_FILE = "materials.json"

# =================== TEXT STYLING ===================

def style_text(text):
    # Map characters to stylized versions
    style_map = {
        'A': '𝘈', 'B': '𝘉', 'C': '𝘊', 'D': '𝘋', 'E': '𝘌', 'F': '𝘍', 'G': '𝘎', 'H': '𝘏', 'I': '𝘐', 'J': '𝘑', 
        'K': '𝘒', 'L': '𝘓', 'M': '𝘔', 'N': '𝘕', 'O': '𝘖', 'P': '𝘗', 'Q': '𝘘', 'R': '𝘙', 'S': '𝘚', 'T': '𝘛', 
        'U': '𝘜', 'V': '𝘝', 'W': '𝘞', 'X': '𝘟', 'Y': '𝘠', 'Z': '𝘡',
        'a': '𝘢', 'b': '𝘣', 'c': '𝘤', 'd': '𝘥', 'e': '𝘦', 'f': '𝘧', 'g': '𝘨', 'h': '𝘩', 'i': '𝘪', 'j': '𝘫', 
        'k': '𝘬', 'l': '𝘭', 'm': '𝘮', 'n': '𝘯', 'o': '𝘰', 'p': '𝘱', 'q': '𝘲', 'r': '𝘳', 's': '𝘴', 't': '𝘵', 
        'u': '𝘶', 'v': '𝘷', 'w': '𝘸', 'x': '𝘹', 'y': '𝘺', 'z': '𝘻',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
        '>': '➞', '<': '❮', '+': '➕', '-': '➖'
    }
    
    # Special cases for specific phrases
    special_cases = {
        "IIT JEE": "𝙄𝙄𝙏 𝙅𝙀𝙀",
        "NEET": "𝙉𝙀𝙀𝙏",
        "Physics": "𝙋𝙝𝙮𝙨𝙞𝙘𝙨",
        "Chemistry": "𝘾𝙝𝙚𝙢𝙞𝙨𝙩𝙧𝙮",
        "Math": "𝙈𝙖𝙩𝙝",
        "Biology": "𝘽𝙞𝙤𝙡𝙤𝙜𝙮",
        "Community": "𝘾𝙊𝙈𝙈𝙐𝙉𝙄𝙏𝙔",
        "Credits": "𝘾𝙍𝙀𝘿𝙄𝙏𝙎",
        "Add New Publisher": "➕ 𝘼𝙙𝙙 𝙉𝙚𝙬 𝙋𝙪𝙗𝙡𝙞𝙨𝙝𝙚𝙧",
        "Only admins can add subjects": "𝘖𝘯𝘭𝘺 𝘢𝘥𝘮𝘪𝘯𝘴 𝘤𝘢𝘯 𝘢𝘥𝘥 𝘴𝘶𝘣𝘫𝘦𝘤𝘵𝘴",
        "You are not authorized": "𝘠𝘰𝘶 𝘢𝘳𝘦 𝘯𝘰𝘵 𝘢𝘶𝘵𝘩𝘰𝘳𝘪𝘻𝘦𝘥",
        "Welcome! Choose an option": "𝘞𝘦𝘭𝘤𝘰𝘮𝘦! 𝘊𝘩𝘰𝘰𝘴𝘦 𝘢𝘯 𝘰𝘱𝘵𝘪𝘰𝘯",
        "Select Exam": "𝘚𝘦𝘭𝘦𝘤𝘵 𝘌𝘹𝘢𝘮",
        "Select Subject": "𝘚𝘦𝘭𝘦𝘤𝘵 𝘚𝘶𝘣𝘫𝘦𝘤𝘵",
        "Select Publisher": "𝘚𝘦𝘭𝘦𝘤𝘵 𝘗𝘶𝘣𝘭𝘪𝘴𝘩𝘦𝘳",
        "Send the new publisher name": "𝘚𝘦𝘯𝘥 𝘵𝘩𝘦 𝘯𝘦𝘸 𝘱𝘶𝘣𝘭𝘪𝘴𝘩𝘦𝘳 𝘯𝘢𝘮𝘦",
        "Upload mode ON for": "𝘜𝘱𝘭𝘰𝘢𝘥 𝘮𝘰𝘥𝘦 𝘖𝘕 𝘧𝘰𝘳",
        "Send files now": "𝘚𝘦𝘯𝘥 𝘧𝘪𝘭𝘦𝘴 𝘯𝘰𝘸",
        "Send PDF/Image/Video files": "𝘚𝘦𝘯𝘥 𝘗𝘋𝘍/𝘐𝘮𝘢𝘨𝘦/𝘝𝘪𝘥𝘦𝘰 𝘧𝘪𝘭𝘦𝘴",
        "Deleted publisher": "𝘋𝘦𝘭𝘦𝘵𝘦𝘥 𝘱𝘶𝘣𝘭𝘪𝘴𝘩𝘦𝘳",
        "Select file number to DELETE": "𝘚𝘦𝘭𝘦𝘤𝘵 𝘧𝘪𝘭𝘦 𝘯𝘶𝘮𝘣𝘦𝘳 𝘵𝘰 𝘋𝘌𝘓𝘌𝘛𝘦",
        "Send subject name": "𝘚𝘦𝘯𝘥 𝘴𝘶𝘣𝘫𝘦𝘤𝘵 𝘯𝘢𝘮𝘦",
        "Subject added": "𝘚𝘶𝘣𝘫𝘦𝘤𝘵 𝘢𝘥𝘥𝘦𝘥",
        "Select subject to DELETE": "𝘚𝘦𝘭𝘦𝘤𝘵 𝘴𝘶𝘣𝘫𝘦𝘤𝘵 𝘵𝘰 𝘋𝘌𝘓𝘌𝘛𝘌",
        "Deleted subject": "𝘋𝘦𝘭𝘦𝘵𝘦𝘥 𝘴𝘶𝘣𝘫𝘦𝘤𝘵",
        "Send the message you want to broadcast": "𝘚𝘦𝘯𝘥 𝘵𝘩𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 𝘺𝘰𝘶 𝘸𝘢𝘯𝘵 𝘵𝘰 𝘣𝘳𝘰𝘢𝘥𝘤𝘢𝘴𝘵",
        "Broadcast complete": "𝘉𝘳𝘰𝘢𝘥𝘤𝘢𝘴𝘵 𝘤𝘰𝘮𝘱𝘭𝘦𝘵𝘦",
        "Join our Community": "𝘑𝘰𝘪𝘯 𝘰𝘶𝘳 𝘊𝘰𝘮𝘮𝘶𝘯𝘪𝘵𝘺",
        "This bot is created by Admin": "𝘛𝘩𝘪𝘴 𝘣𝘰𝘵 𝘪𝘴 𝘤𝘳𝘦𝘢𝘵𝘦𝘥 𝘣𝘺 𝘈𝘥𝘮𝘪𝘯",
        "No materials uploaded yet": "𝘕𝘰 𝘮𝘢𝘵𝘦𝘳𝘪𝘢𝘭𝘴 𝘶𝘱𝘭𝘰𝘢𝘥𝘦𝘥 𝘺𝘦𝘵",
        "Please choose from menu": "𝘗𝘭𝘦𝘢𝘴𝘦 𝘤𝘩𝘰𝘰𝘴𝘦 𝘧𝘳𝘰𝘮 𝘮𝘦𝘯𝘶",
        "Main Menu": "𝘔𝘢𝘪𝘯 𝘔𝘦𝘯𝘶",
        "Cancel": "𝘊𝘢𝘯𝘤𝘦𝘭",
        "Done": "𝘋𝘰𝘯𝘦"
    }
    
    # Check for special cases first
    for phrase, styled in special_cases.items():
        if phrase in text:
            text = text.replace(phrase, styled)
    
    # Style remaining text character by character
    return ''.join(style_map.get(char, char) for char in text)

def destyle_text(text):
    # Reverse mapping for special cases
    special_cases = {
        "𝙄𝙄𝙏 𝙅𝙀𝙀": "IIT JEE",
        "𝙉𝙀𝙀𝙏": "NEET",
        "𝙋𝙝𝙮𝙨𝙞𝙘𝙨": "Physics",
        "𝘾𝙝𝙚𝙢𝙞𝙨𝙩𝙧𝙮": "Chemistry",
        "𝙈𝙖𝙩𝙝": "Math",
        "𝘽𝙞𝙤𝙡𝙤𝙜𝙮": "Biology",
    }
    
    # Check for special cases first
    for styled, original in special_cases.items():
        if styled in text:
            return original
    
    # If no special case found, return as is (it's probably already destyled)
    return text

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
                if isinstance(data[exam], dict):  # Ensure it's a dict, not a list
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
    # Apply styling to all keyboard text
    styled_rows = []
    for row in rows:
        styled_row = [style_text(item) for item in row]
        styled_rows.append(styled_row)
    return ReplyKeyboardMarkup(styled_rows, resize_keyboard=True)

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
        "awaiting_text": False,  # used for broadcast or similar
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
        style_text("Welcome! Choose an option 👇"),
        reply_markup=main_menu_kb()
    )

# ----- Add material -----

async def cmd_addmaterial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(style_text("❌ You are not authorized."))
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "add"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    if not exams:
        await update.message.reply_text(style_text("No exams found. Admin can add exams using /addsubject with an exam name and subject."))
        return
        
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text(style_text("Select Exam:"), reply_markup=kb(rows))

# ----- Delete file -----

async def cmd_deletefile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(style_text("❌ You are not authorized."))
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_file"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text(style_text("🗑️ Delete File → Select Exam:"), reply_markup=kb(rows))

# ----- Delete publisher -----

async def cmd_deletepublisher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(style_text("❌ You are not authorized."))
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_publisher"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text(style_text("🗑️ Delete Publisher → Select Exam:"), reply_markup=kb(rows))

# ----- Add Subject (dynamic) -----

async def cmd_addsubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(style_text("❌ Only admins can add subjects."))
        return
        
    # Expecting usage: /addsubject <Exam> > <Subject>
    text = " ".join(context.args) if context.args else ""
    if ">" in text:
        parts = [p.strip() for p in text.split(">")]
        if len(parts) >= 2:
            exam = parts[0]
            subject = parts[1]
            ensure_subject(exam, subject)
            save_materials()
            await update.message.reply_text(style_text(f"✅ Subject '{subject}' added under exam '{exam}'."))
            return
            
    # interactive flow
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "add_subject"
    st["step"] = "ask_exam"
    await update.message.reply_text(style_text("Send exam name (existing or new) for which you want to add a subject:"))

async def cmd_deletesubject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(style_text("❌ Only admins can delete subjects."))
        return
        
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "delete_subject"
    st["step"] = "choose_exam"

    exams = exams_from_data()
    rows = chunk(exams, 2)
    rows.append(["🏠 Menu"])
    await update.message.reply_text(style_text("Select Exam to delete a subject from:"), reply_markup=kb(rows))

# ----- Admin management (owner only) -----

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text(style_text("❌ Only bot owner can add admins."))
        return
        
    if not context.args:
        await update.message.reply_text(style_text("Usage: /addadmin <telegram_user_id>"))
        return
        
    try:
        new_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text(style_text("❌ Provide a numeric Telegram user id."))
        return
        
    admins = MATERIALS.setdefault("_meta", {}).setdefault("admins", [])
    if new_admin in admins:
        await update.message.reply_text(style_text("⚠️ This user is already an admin."))
        return
        
    admins.append(new_admin)
    save_materials()
    await update.message.reply_text(style_text(f"✅ Added admin: {new_admin}"))

async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text(style_text("❌ Only bot owner can remove admins."))
        return
        
    if not context.args:
        await update.message.reply_text(style_text("Usage: /removeadmin <telegram_user_id>"))
        return
        
    try:
        rem = int(context.args[0])
    except ValueError:
        await update.message.reply_text(style_text("❌ Provide a numeric Telegram user id."))
        return
        
    admins = MATERIALS.setdefault("_meta", {}).setdefault("admins", [])
    if rem not in admins:
        await update.message.reply_text(style_text("⚠️ This user is not an admin."))
        return
        
    admins.remove(rem)
    save_materials()
    await update.message.reply_text(style_text(f"✅ Removed admin: {rem}"))

# ----- Broadcast (owner only) -----

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_owner(uid):
        await update.message.reply_text(style_text("❌ Only bot owner can broadcast messages."))
        return
        
    # start interactive flow: owner will send message text next
    reset_state(uid)
    st = user_state[uid]
    st["mode"] = "broadcast"
    st["step"] = "await_text"
    st["awaiting_text"] = True
    await update.message.reply_text(style_text("✉️ Send the message you want to broadcast to all users. It can be text only."))

# ----- Done / Cancel -----

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = user_state.get(uid)
    if not st:
        await update.message.reply_text(style_text("ℹ️ Nothing to finish."))
        return
        
    if st.get("mode") == "add" and st.get("upload_active"):
        st["upload_active"] = False
        await update.message.reply_text(style_text(f"✅ Upload finished for {st['exam']} > {st['subject']} > {st['publisher']}"))
        return
        
    await update.message.reply_text(style_text("✅ Done."))

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    reset_state(uid)
    await update.message.reply_text(style_text("❎ Cancelled."), reply_markup=main_menu_kb())

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
        await update.message.reply_text(style_text(f"✅ Saved to {exam} > {subject} > {publisher}"))
    else:
        await update.message.reply_text(style_text("❌ Only PDF/Image/Video allowed."))

# =================== TEXT HANDLER (STATE MACHINE + PUBLIC BROWSING) ===================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = (update.message.text or "").strip()
    
    if uid not in user_state:
        reset_state(uid)
        
    st = user_state[uid]

    # Add user to meta (for broadcast)
    add_user_to_meta(uid)

    # Global navigation
    if txt in ("🏠 Menu", "Menu", "/menu"):
        reset_state(uid)
        await update.message.reply_text(style_text("Main Menu:"), reply_markup=main_menu_kb())
        return
        
    if txt == "⬅️ Back":
        # back logic
        if st["step"] == "choose_subject":
            st["step"] = "choose_exam"
            st["exam"] = None
            exams = exams_from_data()
            rows = chunk(exams, 2)
            rows.append(["🏠 Menu"])
            await update.message.reply_text(style_text("Select Exam:"), reply_markup=kb(rows))
            return
        elif st["step"] == "choose_publisher":
            st["step"] = "choose_subject"
            st["subject"] = None
            await update.message.reply_text(style_text(f"{st['exam']} – Select Subject:"), reply_markup=subjects_kb(st["exam"]))
            return
        elif st["step"] == "choose_file":
            st["step"] = "choose_publisher"
            st["publisher"] = None
            await update.message.reply_text(
                style_text(f"{st['exam']} > {st['subject']} – Select Publisher:"),
                reply_markup=publishers_kb(st["exam"], st["subject"], include_add=(st["mode"]=="add"))
            )
            return
            
        reset_state(uid)
        await update.message.reply_text(style_text("Main Menu:"), reply_markup=main_menu_kb())
        return

    # ========== ADD MODE ==========
    if st.get("mode") == "add":
        # awaiting new publisher name
        if st.get("awaiting_new_publisher_name"):
            new_pub = txt
            if new_pub in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text(style_text("⚠️ Publisher already exists. Choose another name."))
                return
                
            ensure_publisher(st["exam"], st["subject"], new_pub)
            save_materials()
            st["publisher"] = new_pub
            st["awaiting_new_publisher_name"] = False
            st["upload_active"] = True
            st["step"] = "choose_file"
            await update.message.reply_text(
                style_text(f"✅ Publisher \"{new_pub}\" created. Now send files (PDF/Image/Video).\n\nSend /done when finished."), 
                reply_markup=kb([["⬅️ Back", "🏠 Menu"]])
            )
            return
            
        # choose exam
        if st["step"] == "choose_exam":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in exams_from_data():
                await update.message.reply_text(style_text("❌ Invalid exam. Choose from buttons."))
                return
                
            st["exam"] = destyled_txt
            st["step"] = "choose_subject"
            await update.message.reply_text(style_text(f"{st['exam']} – Select Subject:"), reply_markup=subjects_kb(st["exam"]))
            return
            
        # choose subject
        if st["step"] == "choose_subject":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text(style_text("❌ Invalid subject. Choose from buttons."))
                return
                
            st["subject"] = destyled_txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(
                style_text(f"{st['exam']} > {st['subject']} – Select Publisher or add new:"),
                reply_markup=publishers_kb(st["exam"], st["subject"], include_add=True)
            )
            return
            
        # choose publisher or add
        if st["step"] == "choose_publisher":
            if txt == style_text("➕ Add New Publisher"):
                st["awaiting_new_publisher_name"] = True
                await update.message.reply_text(style_text("✍️ Send the new publisher name:"), reply_markup=kb([["⬅️ Back", "🏠 Menu"]]))
                return
                
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text(style_text("❌ Invalid publisher. Choose from buttons or add new."))
                return
                
            st["publisher"] = txt
            st["upload_active"] = True
            st["step"] = "choose_file"
            await update.message.reply_text(
                style_text(f"📤 Upload mode ON for {st['exam']} > {st['subject']} > {st['publisher']}\nSend files now. Use /done when finished."), 
                reply_markup=kb([["⬅️ Back", "🏠 Menu"]])
            )
            return
            
        if st["step"] == "choose_file":
            await update.message.reply_text(style_text("ℹ️ Send PDF/Image/Video files. Use /done when finished."))
            return

    # ========== DELETE PUBLISHER ==========
    if st.get("mode") == "delete_publisher":
        if st["step"] == "choose_exam":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in exams_from_data():
                await update.message.reply_text(style_text("❌ Invalid exam. Choose from buttons."))
                return
                
            st["exam"] = destyled_txt
            st["step"] = "choose_subject"
            await update.message.reply_text(style_text(f"{st['exam']} – Select Subject:"), reply_markup=subjects_kb(st["exam"]))
            return
            
        if st["step"] == "choose_subject":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text(style_text("❌ Invalid subject. Choose from buttons."))
                return
                
            st["subject"] = destyled_txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(style_text(f"{st['exam']} > {st['subject']} – Select Publisher to DELETE:"), reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return
            
        if st["step"] == "choose_publisher":
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text(style_text("❌ Invalid publisher. Choose from buttons."))
                return
                
            del MATERIALS[st["exam"]][st["subject"]][txt]
            save_materials()
            await update.message.reply_text(style_text(f"✅ Deleted publisher \"{txt}\" from {st['exam']} > {st['subject']}"), reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return

    # ========== DELETE FILE ==========
    if st.get("mode") == "delete_file":
        if st["step"] == "choose_exam":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in exams_from_data():
                await update.message.reply_text(style_text("❌ Invalid exam. Choose from buttons."))
                return
                
            st["exam"] = destyled_txt
            st["step"] = "choose_subject"
            await update.message.reply_text(style_text(f"{st['exam']} – Select Subject:"), reply_markup=subjects_kb(st["exam"]))
            return
            
        if st["step"] == "choose_subject":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text(style_text("❌ Invalid subject. Choose from buttons."))
                return
                
            st["subject"] = destyled_txt
            st["step"] = "choose_publisher"
            await update.message.reply_text(style_text(f"{st['exam']} > {st['subject']} – Select Publisher:"), reply_markup=publishers_kb(st["exam"], st["subject"], include_add=False))
            return
            
        if st["step"] == "choose_publisher":
            if txt not in publishers_for(st["exam"], st["subject"]):
                await update.message.reply_text(style_text("❌ Invalid publisher. Choose from buttons."))
                return
                
            st["publisher"] = txt
            st["step"] = "choose_file"
            items = MATERIALS.get(st["exam"], {}).get(st["subject"], {}).get(st["publisher"], [])
            if not items:
                await update.message.reply_text(style_text("⚠️ No files in this publisher."))
                return
                
            lines = [style_text("Select file number to DELETE:")]
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
                await update.message.reply_text(style_text("❌ Send a valid number from the list."))
                return
                
            if idx < 0 or idx >= len(items):
                await update.message.reply_text(style_text("❌ Number out of range."))
                return
                
            removed = items.pop(idx)
            save_materials()
            await update.message.reply_text(style_text(f"✅ Deleted: {removed.get('name') or removed.get('type')}"))
            
            if not items:
                await update.message.reply_text(style_text("(Folder now empty)"))
            else:
                lines = [style_text("Remaining files:")]
                for i, it in enumerate(items, start=1):
                    label = it.get("name") or it.get("type") or "file"
                    lines.append(f"{i}. {label}")
                await update.message.reply_text("\n".join(lines))
            return

    # ========== ADD SUBJECT INTERACTIVE FLOW ==========
    if st.get("mode") == "add_subject":
        if st.get("step") == "ask_exam":
            exam = txt
            st["exam"] = exam
            st["step"] = "ask_subject"
            await update.message.reply_text(style_text(f"Send subject name to add under exam '{exam}':"), reply_markup=kb([["⬅️ Back", "🏠 Menu"]]))
            return
            
        if st.get("step") == "ask_subject":
            subject = txt
            ensure_subject(st["exam"], subject)
            save_materials()
            await update.message.reply_text(style_text(f"✅ Subject '{subject}' added under exam '{st['exam']}'"))
            reset_state(uid)
            return

    # ========== DELETE SUBJECT INTERACTIVE FLOW ==========
    if st.get("mode") == "delete_subject":
        if st.get("step") == "choose_exam":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in exams_from_data():
                await update.message.reply_text(style_text("❌ Invalid exam. Choose from buttons."))
                return
                
            st["exam"] = destyled_txt
            st["step"] = "choose_subject_to_delete"
            await update.message.reply_text(style_text(f"Select subject to DELETE from {txt}:"), reply_markup=subjects_kb(destyled_txt))
            return
            
        if st.get("step") == "choose_subject_to_delete":
            # Convert stylized text back to original for comparison
            destyled_txt = destyle_text(txt)
            if destyled_txt not in subjects_for_exam(st["exam"]):
                await update.message.reply_text(style_text("❌ Invalid subject."))
                return
                
            del MATERIALS[st["exam"]][destyled_txt]
            save_materials()
            await update.message.reply_text(style_text(f"✅ Deleted subject '{txt}' from exam '{st['exam']}'"))
            reset_state(uid)
            return

    # ========== BROADCAST FLOW ==========
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
                
        await update.message.reply_text(style_text(f"📣 Broadcast complete. Sent: {sent}, Failed: {failed}"))
        reset_state(uid)
        return

    # ========== PUBLIC BROWSING ==========
    if txt == style_text("📘 IIT JEE"):
        await update.message.reply_text(style_text("IIT JEE – Subjects:"), reply_markup=subjects_kb("IIT JEE"))
        return
    elif txt == style_text("📗 NEET"):
        await update.message.reply_text(style_text("NEET – Subjects:"), reply_markup=subjects_kb("NEET"))
        return
    elif txt == style_text("👥 Community"):
        await update.message.reply_text(style_text("Join our Community: https://t.me/yourcommunity"))
        return
    elif txt == style_text("ℹ️ Credits"):
        await update.message.reply_text(style_text("This bot is created by Admin."))
        return

    # Subject-level navigation
    for exam in exams_from_data():
        if txt in [style_text(subject) for subject in subjects_for_exam(exam)]:
            # Convert stylized text back to original for data lookup
            destyled_txt = destyle_text(txt)
            await update.message.reply_text(style_text(f"{exam} > {destyled_txt} – Publishers:"), reply_markup=publishers_kb(exam, destyled_txt))
            return

    # Publisher-level (check both exams)
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
                    await update.message.reply_text(style_text("⚠️ No materials uploaded yet."))
                    return

    # Fallback
    await update.message.reply_text(style_text("Please choose from menu 👇"), reply_markup=main_menu_kb())

# =================== MAIN ===================

def main():
    # Create application with persistent data
    application = Application.builder().token(TOKEN).build()

    # Add handlers
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

    # File handlers
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_files))
    
    # Text handler (must be last to not interfere with other handlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot is starting...")
    
    # Run with error handling for Termux
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
        main()  # Restart the bot

if __name__ == "__main__":
    main()