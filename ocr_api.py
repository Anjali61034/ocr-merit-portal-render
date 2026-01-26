from fastapi import FastAPI, UploadFile, File, Form
from PIL import Image
import pytesseract
import re
import io
from typing import Optional
from pdf2image import convert_from_bytes

app = FastAPI()

# =============================
# OCR HELPERS (SAME AS STREAMLIT)
# =============================
def normalize_text(text: str) -> str:
    t = text.replace("|", " ").replace(";", ":")
    t = t.replace("W", "II").replace("mM", "III").replace("Vv", "IV")
    t = t.replace("l", "I")
    return t


def apply_common_fixes(text: str) -> str:
    COMMON_FIXES = {
        "piast": "first",
        "frist": "first",
        "fi rst": "first",
        "1 st": "1st",
        "internationa!": "international",
        "intemationai": "international",
        "voiunteer": "volunteer",
        "iiorld": "world",
        "attendifs": "attending",
    }
    t = text.lower()
    for wrong, right in COMMON_FIXES.items():
        t = t.replace(wrong, right)
    return t


# =============================
# STREAMLIT CERTIFICATE LOGIC (COPIED AS-IS)
# =============================
LEADERSHIP_WORDS = [
    "captain", "organizer", "leadership", "head", "sub head", "sub-head",
    "president", "vice president", "vice-president"
]

PARTICIPATION_WORDS = [
    "participated", "participation", "participating", "contribution", "member",
    "completed", "completion", "participate", "part", "attending", "attended", "attendifs"
]

RANK_WORDS = {
    "1": ["1st Rank", "first", "first position", "winner", "gold"],
    "2": ["2nd Rank", "second", "runner", "silver"],
    "3": ["3rd Rank", "third", "bronze"]
}

ORGANIZING_WORDS = [
    "organizing committee", "organizing", "volunteer",
]

CATEGORY_KEYWORDS = {
    "Industry Experience": ["intern", "internship", "trainee", "industry"],
    "National Cadet Corps": ["ncc", "cadet"],
    "Sports": ["sport", "tournament", "match", "cricket", "football"],
    "Outreach Activities": ["volunteer", "community", "social", "blood"],
    "Academic Engagement and Research": [
        "research", "paper", "seminar", "conference",
        "workshop", "online course", "course", "training", "international"
    ],
    "Extra-Curricular Activities": ["cultural", "dance", "music", "debate", "club"]
}

LEVEL_KEYWORDS = {
    "International": ["international", "abroad", "overseas"],
    "National": ["national"],
    "Local": ["college", "university", "state"]
}


def analyze_certificate(text: str):
    low = text.lower()

    # Leadership
    lead_hits = [w for w in LEADERSHIP_WORDS if w in low]
    is_lead = len(lead_hits) > 0

    # Participation
    part_hits = [w for w in PARTICIPATION_WORDS if w in low]
    cert_type = "Participation" if part_hits else "Merit"

    # Rank
    rank = None
    for r, words in RANK_WORDS.items():
        for w in words:
            if w in low:
                rank = r

    # Category
    category = "Extra-Curricular Activities"

    if any(w in low for w in ["wwf", "volunteer", "ngo", "awareness", "outreach"]):
        category = "Outreach Activities"

    elif any(w in low for w in ORGANIZING_WORDS):
        category = "Extra-Curricular Activities"

    else:
        for cat, words in CATEGORY_KEYWORDS.items():
            for w in words:
                if re.search(rf'\b{re.escape(w)}\b', low):
                    category = cat
                    break

    # Level
    level = "Local"
    for lvl, words in LEVEL_KEYWORDS.items():
        for w in words:
            if w in low:
                level = lvl
                break

    return {
        "cert_type": cert_type,
        "rank": rank,
        "category": category,
        "level": level,
        "is_lead": is_lead,
    }


def calculate_certificate_points(info):
    pts = 0.0

    if info["cert_type"] == "Participation":
        pts += 0.5

    if info["rank"] == "1":
        pts += 2
    elif info["rank"] == "2":
        pts += 1.5
    elif info["rank"] == "3":
        pts += 1

    if info["level"] == "International":
        pts += 2
    elif info["level"] == "National":
        pts += 1.5

    if info["is_lead"]:
        pts += 1

    return min(pts, 5)


# =============================
# FASTAPI ENDPOINT
# =============================
@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    doc_type: str = Form(...)
):
    file_bytes = await file.read()
    mime = file.content_type
    text = ""

    if mime == "application/pdf":
        images = convert_from_bytes(file_bytes)
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
    else:
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img)

    clean_text = apply_common_fixes(normalize_text(text))

    if doc_type == "certificate":
        info = analyze_certificate(clean_text)
        points = calculate_certificate_points(info)

        return {
            "type": "certificate",
            "points": points,
            **info,
            "text": clean_text
        }

    return {"error": "Unsupported document type", "points": 0}
