import os
import fitz  # PyMuPDF
import re
import pandas as pd

# Folder containing the PDFs organized in subfolders
ROOT_DIR = "c:/Users/GOVT LAW COLLEGE 107/Documents/exam/pdf_folder"

# --- Helper: Extract metadata from PDF text ---
def extract_metadata(text):
    class_match = re.search(r'([A-Z]+)\s*/?\s*(\d+YEAR)', text)
    class_val = f"{class_match.group(1)} {class_match.group(2)}" if class_match else "To be filled"

    # Detect mode/type: REGULAR, PRIVATE, SUPP, EXR
    mode_type = "To be filled"
    for keyword in ["REGULAR", "SUPP", "EXR", "PRIVATE"]:
        if keyword in text.upper():
            mode_type = keyword
            break

    paper_code = re.search(r'Paper Code[:\s]*([\d]+)', text)
    paper_code = paper_code.group(1) if paper_code else "To be filled"

    paper_name = re.search(r'Paper Name[:\s]*(.+?)(?:\n|$)', text)
    paper_name = paper_name.group(1).strip() if paper_name else "To be filled"

    return {
        "class": class_val,
        "mode": mode_type,
        "type": mode_type,
        "room_number": "To be filled",
        "seat_numbers": ["To be filled"] * 10,
        "paper_code": paper_code,
        "paper_name": paper_name
    }

# --- Helper: Extract roll numbers ---
def extract_roll_numbers(text):
    return re.findall(r'\b\d{9}\b', text)

# --- Helper: Format student CSV rows (grouped by 10) ---
def format_rows(rolls, paper, meta):
    rows = []
    for i in range(0, len(rolls), 10):
        row = rolls[i:i+10]
        while len(row) < 10:
            row.append("")
        row.extend([
            meta["class"],
            meta["mode"],
            meta["type"],
            meta["room_number"]
        ])
        row.extend(meta["seat_numbers"])
        row.append(paper)
        row.append(meta["paper_code"])
        row.append(meta["paper_name"])
        rows.append(row)
    return rows

# 🧾 Prepare column headers
columns = [f"Roll Number {i+1}" for i in range(10)]
columns += ["Class", "Mode", "Type", "Room Number"]
columns += [f"Seat Number {i+1}" for i in range(10)]
columns += ["Paper", "Paper Code", "Paper Name"]

# --- Collect all student data and timetable entries ---
all_rows = []
timetable_entries = []

for folder in os.listdir(ROOT_DIR):
    folder_path = os.path.join(ROOT_DIR, folder)
    if os.path.isdir(folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(folder_path, file)
                try:
                    doc = fitz.open(pdf_path)
                    full_text = "\n".join(page.get_text() for page in doc)
                    doc.close()

                    rolls = extract_roll_numbers(full_text)
                    meta = extract_metadata(full_text)

                    # Append student data
                    student_rows = format_rows(rolls, folder, meta)
                    all_rows.extend(student_rows)

                    # Append timetable entry
                    timetable_entries.append({
                        "Class": meta["class"],
                        "Paper": folder,
                        "Paper Code": meta["paper_code"],
                        "Paper Name": meta["paper_name"]
                    })

                    print(f"✔ Processed: {pdf_path} ({len(rolls)} rolls)")

                except Exception as e:
                    print(f"❌ Failed: {pdf_path} — {e}")

# --- Write sitting plan CSV ---
df = pd.DataFrame(all_rows, columns=columns)
sitting_plan_csv = "c:/Users/GOVT LAW COLLEGE 107/Documents/exam/sitting_plan.csv"
df.to_csv(sitting_plan_csv, index=False)
print(f"✅ Saved: {sitting_plan_csv}")

# --- Create deduplicated timetable CSV ---
df_tt = pd.DataFrame(timetable_entries).drop_duplicates(subset=["Class", "Paper Code"])
df_tt.insert(0, "SN", range(1, len(df_tt)+1))
df_tt.insert(1, "Date", "")
df_tt.insert(2, "Shift", "")

timetable_csv = "c:/Users/GOVT LAW COLLEGE 107/Documents/exam/timetable.csv"
df_tt.to_csv(timetable_csv, index=False)
print(f"✅ Saved: {timetable_csv}")
