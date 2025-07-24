import pandas as pd
import re

# Load data
df = pd.read_csv("c:/Users/GOVT LAW COLLEGE 107/Documents/exam/attestation_data_combined.csv")

# ----------------------
# STEP 1: Simplify Fields
# ----------------------

# Extract Class Group and Year like "BSC", "2YEAR"
def simplify_class(text):
    match = re.match(r'([A-Z]+)\s*-\s*.*?(\d+YEAR)', str(text).upper())
    if match:
        return match.group(1), match.group(2)
    return "UNKNOWN", "UNKNOWN"

df["Class"] = df["Exam Name"].str.upper().str.strip()
df["Regular/Backlog"] = df["Regular/Backlog"].str.upper().str.strip()
df["College Name"] = df["College Name"].str.upper().str.strip()

df[["Class Group", "Year"]] = df["Class"].apply(lambda x: pd.Series(simplify_class(x)))

# --------------------------
# STEP 2: Prepare Class Blocks
# --------------------------

class_groups = sorted(df["Class Group"].dropna().unique())
college_list = sorted(df["College Name"].dropna().unique())

# Helper to count per college/class group/year
def get_counts(df, college, group, year):
    subset = df[(df["College Name"] == college) & (df["Class Group"] == group) & (df["Year"] == year)]
    total = len(subset)
    regular = len(subset[subset["Regular/Backlog"] == "REGULAR"])
    ex = len(subset[subset["Regular/Backlog"] == "EX"])
    supp = len(subset[subset["Regular/Backlog"] == "SUPP"])
    return [total, regular, ex, supp]

# -----------------------
# STEP 3: Build CSV Rows
# -----------------------

output_rows = []

for group in class_groups:
    years = sorted(df[df["Class Group"] == group]["Year"].dropna().unique())

    # Header rows
    header_row1 = ["Class"] + [f"{group} - {year}" for year in years for _ in range(4)]
    header_row2 = ["College", "Grand Total"] + ["Total", "Regular", "EX", "SUPP"] * len(years)

    block_data = []
    for college in college_list:
        row = [college]
        grand_total = 0
        for year in years:
            t, r, e, s = get_counts(df, college, group, year)
            row += [t, r, e, s]
            grand_total += t
        row.insert(1, grand_total)
        block_data.append(row)

    # Append this group block
    output_rows.append(header_row1)
    output_rows.append(header_row2)
    output_rows += block_data
    output_rows.append([])  # Spacer row

# Final Summary Block
output_rows.append(["College", "Total of all"])
for college in college_list:
    total = len(df[df["College Name"] == college])
    output_rows.append([college, total])

# --------------------------
# STEP 4: Save to CSV
# --------------------------

output_path = "c:/Users/GOVT LAW COLLEGE 107/Documents/exam/college_statistics_fancy.csv"
pd.DataFrame(output_rows).to_csv(output_path, index=False, header=False)
print(f"✅ Statistics saved in layout format to:\n{output_path}")
