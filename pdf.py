import os
import fitz  # PyMuPDF
import re
import pandas as pd

ROOT_DIR = "pdf_folder"

# 🧠 Extract metadata from text
def extract_metadata(text):
    meta = {
        "class": "UNKNOWN",
        "mode": "UNKNOWN",
        "type": "UNKNOWN",
        "paper_code": "UNKNOWN",
        "paper_name": "UNKNOWN"
    }

    # Match Class / Mode / Type
    class_match = re.search(r'([A-Z]+)\s*/\s*(\d+YEAR)\s*/\s*([A-Z]+)\s*/\s*([A-Z]+)', text)
    if class_match:
        meta["class"] = f"{class_match.group(1)} {class_match.group(2)}"
        meta["mode"] = class_match.group(3)
        meta["type"] = class_match.group(4)

    # Paper Code
    code_match = re.search(r'Paper Code:\s*(\d+)', text)
    if code_match:
        meta["paper_code"] = code_match.group(1)

    # Paper Name
    name_match = re.search(r'Paper Name:\s*(.+?)(?:\n|$)', text)
    if name_match:
        meta["paper_name"] = name_match.group(1).strip()

    return meta

# 📋 Extract all 9-digit roll numbers
def extract_roll_numbers(text):
    return re.findall(r'\b\d{9}\b', text)

# 🧱 Format sitting plan rows (10 per row)
def format_sitting_rows(rolls, meta, paper):
    rows = []
    for i in range(0, len(rolls), 10):
        row = rolls[i:i+10]
        while len(row) < 10:
            row.append("")
        row.extend([
            meta["class"],
            meta["mode"],
            meta["type"],
            "To be filled"  # Room Number
        ])
        row.extend(["To be filled"] * 10)  # Seat Numbers
        row.append(paper)
        row.append(meta["paper_code"])
        row.append(meta["paper_name"])
        rows.append(row)
    return rows

# 📘 Deduplicate by paper code, keeping the longest paper name
def deduplicate_by_paper_code(entries):
    df = pd.DataFrame(entries)
    df["name_len"] = df["Paper Name"].str.len()
    df = df.sort_values(by="name_len", ascending=False)
    df = df.drop_duplicates(subset="Paper Code", keep="first")
    df = df.drop(columns="name_len")
    return df

# 🔍 Process PDFs
sitting_plan_rows = []
time_table_entries = []

for folder in os.listdir(ROOT_DIR):
    folder_path = os.path.join(ROOT_DIR, folder)
    if not os.path.isdir(folder_path):
        continue

    for file in os.listdir(folder_path):
        if not file.lower().endswith(".pdf"):
            continue

        file_path = os.path.join(folder_path, file)
        try:
            doc = fitz.open(file_path)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()

            meta = extract_metadata(text)
            rolls = extract_roll_numbers(text)

            # Collect for time_table
            time_table_entries.append({
                "Class": meta["class"],
                "Paper": folder,
                "Paper Code": meta["paper_code"],
                "Paper Name": meta["paper_name"]
            })

            # Collect for sitting plan
            sitting_plan_rows.extend(format_sitting_rows(rolls, meta, folder))

            print(f"✅ Parsed: {file_path} ({len(rolls)} roll numbers)")

        except Exception as e:
            print(f"❌ Error: {file_path} — {e}")

# 📝 Save time_table.csv
tt_df = deduplicate_by_paper_code(time_table_entries)
tt_df.insert(0, "SN", range(1, len(tt_df) + 1))
tt_df.insert(1, "Date", "")
tt_df.insert(2, "Shift", "")
tt_df.to_csv("time_table.csv", index=False)
print("✅ time_table.csv created.")

# 📝 Save final_sitting_plan.csv
sitting_headers = [f"Roll Number {i+1}" for i in range(10)] + \
                  ["Class", "Mode", "Type", "Room Number"] + \
                  [f"Seat Number {i+1}" for i in range(10)] + \
                  ["Paper", "Paper Code", "Paper Name"]

sitting_df = pd.DataFrame(sitting_plan_rows, columns=sitting_headers)
sitting_df = deduplicate_by_paper_code(sitting_df)  # Optional deduplication
sitting_df.to_csv("final_sitting_plan.csv", index=False)
print("✅ final_sitting_plan.csv created.")
