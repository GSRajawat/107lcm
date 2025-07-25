import os
import fitz  # PyMuPDF
import re
import pandas as pd

# 🔧 Define the root folder where PDFs are stored in subfolders named by "Paper"
ROOT_DIR = "pdf_folder"  # Example: ./pdf_folder/Zoology or ./pdf_folder/Botany

# 🔧 Default metadata (can be extended per folder or PDF if needed)
DEFAULT_METADATA = {
    "class": "BSC 1YEAR",
    "mode": "REGULAR",
    "type": "REGULAR",
    "room_number": "To be filled",
    "seat_numbers": ["To be filled"] * 10,
    "paper_code": "To be filled",
    "paper_name": "To be filled"
}

# 🧠 Extract roll numbers (9-digit numbers)
def extract_roll_numbers(text):
    return re.findall(r'\b\d{9}\b', text)

# 🧱 Format 10-per-row with metadata
def format_rows(rolls, paper, meta):
    rows = []
    for i in range(0, len(rolls), 10):
        row = rolls[i:i+10]
        while len(row) < 10:
            row.append("")  # pad
        row.extend([
            meta["class"],
            meta["mode"],
            meta["type"],
            meta["room_number"]
        ])
        row.extend(meta["seat_numbers"])
        row.append(paper)  # 👈 folder name as Paper
        row.append(meta["paper_code"])
        row.append(meta["paper_name"])
        rows.append(row)
    return rows

# 🪜 Columns
columns = [f"Roll Number {i+1}" for i in range(10)]
columns += ["Class", "Mode", "Type", "Room Number"]
columns += [f"Seat Number {i+1}" for i in range(10)]
columns += ["Paper", "Paper Code", "Paper Name"]

# 📦 Collect rows
all_rows = []

# 🔍 Walk through folder structure
for folder_name in os.listdir(ROOT_DIR):
    folder_path = os.path.join(ROOT_DIR, folder_name)
    if os.path.isdir(folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(folder_path, file)
                try:
                    doc = fitz.open(pdf_path)
                    full_text = "\n".join(page.get_text() for page in doc)
                    doc.close()
                    rolls = extract_roll_numbers(full_text)
                    rows = format_rows(rolls, paper=folder_name, meta=DEFAULT_METADATA)
                    all_rows.extend(rows)
                    print(f"✔ Processed: {pdf_path} ({len(rolls)} roll numbers)")
                except Exception as e:
                    print(f"❌ Failed: {pdf_path} — {e}")

# 💾 Save to CSV
df = pd.DataFrame(all_rows, columns=columns)
df.to_csv("all_pdfs_sitting_plan.csv", index=False)
print("\n✅ File saved: all_pdfs_sitting_plan.csv")
