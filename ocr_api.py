from fastapi import FastAPI, UploadFile, File, Form
from PIL import Image
import pytesseract
import re
import io
from typing import Optional, Tuple
from pdf2image import convert_from_bytes

app = FastAPI()

# =========================
# TEXT NORMALIZATION
# =========================
def normalize_text(img_text: str) -> str:
    t = img_text.replace("|", " ").replace(";", ":")
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
        "attendifs": "attended",
    }
    t = text.lower()
    for wrong, right in COMMON_FIXES.items():
        t = t.replace(wrong, right)
    return t


# =========================
# MARKSHEET EXTRACTION
# =========================
def extract_sgpa_cgpas(text: str):
    pattern = r'([1IVX]+)[\s\.\)\-:]*\s*\d+\s+\d+\s+([\d.]+)\s*([\d.]+)?\s*(PASSED|FAILED|Pass|Fail)?'
    matches = re.findall(pattern, text, flags=re.IGNORECASE)

    results = []
    for m in matches:
        sem_label = m[0].upper().replace("1", "I")
        try:
            sgpa = float(m[1])
        except:
            sgpa = None

        cgpa = None
        if m[2]:
            try:
                cgpa = float(m[2])
            except:
                cgpa = None

        result = m[3] if m[3] else None
        results.append((sem_label, sgpa, cgpa, result))

    cgpa_matches = re.findall(r'cgpa[:\s]*([\d.]+)', text, flags=re.IGNORECASE)
    final_cgpa = float(cgpa_matches[-1]) if cgpa_matches else None

    return results, final_cgpa


def cgpa_points(cgpa: float, stream: str) -> float:
    if cgpa is None:
        return 0.0
    if stream.lower() == "humanities":
        if cgpa >= 8: return 5
        if cgpa >= 7: return 4
        if cgpa >= 6: return 3
    else:
        if cgpa >= 9: return 5
        if cgpa >= 8: return 4
        if cgpa >= 7: return 3
        if cgpa >= 6: return 2
    return 0.0


# =========================
# CERTIFICATE LOGIC (STREAMLIT STYLE)
# =========================
LEADERSHIP_WORDS = [
    "captain", "organizer", "leadership", "head",
    "president", "vice president", "coordinator", "incharge"
]

PARTICIPATION_WORDS = [
    "participated", "participation", "completed",
    "completion", "attended", "member", "contribution"
]

RANK_KEYWORDS = {
    "1": ["1st", "first", "winner", "gold"],
    "2": ["2nd", "second", "runner", "silver"],
    "3": ["3rd", "third", "bronze"]
}

LEVEL_KEYWORDS = {
    "International": ["international", "abroad", "overseas"],
    "National": ["national"]
}


def analyze_certificate(text: str):
    low = text.lower()

    is_lead = any(w in low for w in LEADERSHIP_WORDS)

    cert_type = (
        "Participation"
        if any(w in low for w in PARTICIPATION_WORDS)
        else "Merit"
    )

    rank = None
    for r, words in RANK_KEYWORDS.items():
        if any(w in low for w in words):
            rank = r
            break

    level = "Local"
    for lvl, words in LEVEL_KEYWORDS.items():
        if any(w in low for w in words):
            level = lvl
            break

    return cert_type, rank, is_lead, level


def certificate_points_streamlit_style(
    cert_type: str,
    rank: Optional[str],
    is_lead: bool,
    level: str
) -> float:

    pts = 0.0

    if cert_type == "Participation":
        pts += 0.5

    if rank == "1":
        pts += 2
    elif rank == "2":
        pts += 1.5
    elif rank == "3":
        pts += 1

    if level == "International":
        pts += 2
    elif level == "National":
        pts += 1.5

    if is_lead:
        pts += 1

    return min(pts, 5)


# =========================
# FASTAPI ENDPOINT
# =========================
@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    stream: str = Form("Sciences")
):
    file_bytes = await file.read()
    mime = file.content_type
    text = ""

    # ---- PDF SUPPORT ----
    if mime == "application/pdf":
        images = convert_from_bytes(file_bytes)
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
    else:
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img)

    clean_text = apply_common_fixes(normalize_text(text))

    # ---- MARKSHEET ----
    if doc_type == "marksheet":
        rows, final_cgpa_match = extract_sgpa_cgpas(clean_text)
        final_cgpa = final_cgpa_match or (
            next((r[2] for r in reversed(rows) if r[2]), None)
        )

        points = cgpa_points(final_cgpa, stream)
        last_rows = rows[-4:]

        return {
            "type": "marksheet",
            "cgpa": final_cgpa,
            "sgpas": [
                {"semester": r[0], "sgpa": r[1], "result": r[3]}
                for r in last_rows if r[1] is not None
            ],
            "points": points,
        }

    # ---- CERTIFICATE ----
    if doc_type == "certificate":
        cert_type, rank, is_lead, level = analyze_certificate(clean_text)

        points = certificate_points_streamlit_style(
            cert_type, rank, is_lead, level
        )

        return {
            "type": "certificate",
            "cert_type": cert_type,
            "rank": rank,
            "level": level,
            "is_lead": is_lead,
            "points": points,
        }

    return {"error": "Unknown document type", "points": 0}
