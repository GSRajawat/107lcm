import pandas as pd
import re

# Load data
df = pd.read_csv("E:/Users/acer/Downloads/attestation_data_combined.csv")

# ----------------------
# STEP 1: Clean & Normalize
# ----------------------

def simplify_class(text):
    match = re.match(r'([A-Z]+)\s*-\s*.*?(\d+YEAR)', str(text).upper())
    if match:
        return match.group(1), match.group(2)
    return "UNKNOWN", "UNKNOWN"

df["Class"] = df["Exam Name"].str.upper().str.strip()
df["Regular/Backlog"] = df["Regular/Backlog"].astype(str).str.upper().str.strip()
df["College Name"] = df["College Name"].str.upper().str.strip()

df[["Class Group", "Year"]] = df["Class"].apply(lambda x: pd.Series(simplify_class(x)))

# --------------------------
# STEP 2: Prepare Class Blocks
# --------------------------

class_groups = sorted(df["Class Group"].dropna().unique())
college_list = sorted(df["College Name"].dropna().unique())

# 🧠 Updated to count EXR instead of EX
def get_counts(df, college, group, year):
    subset = df[(df["College Name"] == college) & (df["Class Group"] == group) & (df["Year"] == year)]
    total = len(subset)
    regular = len(subset[subset["Regular/Backlog"] == "REGULAR"])
    private = len(subset[subset["Regular/Backlog"] == "PRIVATE"])
    exr = len(subset[subset["Regular/Backlog"] == "EXR"])  # Updated here
    supp = len(subset[subset["Regular/Backlog"] == "SUPP"])
    return [total, regular, private, exr, supp]

# -----------------------
# STEP 3: Build CSV Rows
# -----------------------

output_rows = []

for group in class_groups:
    years = sorted(df[df["Class Group"] == group]["Year"].dropna().unique())

    # Header rows with EXR
    header_row1 = ["Class"] + [f"{group} - {year}" for year in years for _ in range(5)]
    header_row2 = ["College", "Grand Total"] + ["Total", "Regular", "Private", "EXR", "SUPP"] * len(years)

    block_data = []
    for college in college_list:
        row = [college]
        grand_total = 0
        for year in years:
            t, r, p, x, s = get_counts(df, college, group, year)
            row += [t, r, p, x, s]
            grand_total += t
        row.insert(1, grand_total)
        block_data.append(row)

    output_rows.append(header_row1)
    output_rows.append(header_row2)
    output_rows += block_data
    output_rows.append([])

# Final Summary Block
output_rows.append(["College", "Total of all"])
for college in college_list:
    total = len(df[df["College Name"] == college])
    output_rows.append([college, total])

# --------------------------
# STEP 4: Save to CSV
# --------------------------

output_path = "E:/Users/acer/Downloads/college_statistics_fancy.csv"
pd.DataFrame(output_rows).to_csv(output_path, index=False, header=False)
print(f"✅ Statistics saved to:\n{output_path}")
