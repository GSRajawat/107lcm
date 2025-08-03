import streamlit as st
import pandas as pd
import datetime
import os
import io
import zipfile
import tempfile
import fitz  # PyMuPDF
import re
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font
import json
import ast
import requests
import io

# --- Supabase config from secrets ---
# The secrets are assumed to be available in the Streamlit environment
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except KeyError:
    st.error("Supabase secrets not found. Please add `supabase` secrets to your Streamlit configuration.")
    SUPABASE_URL = ""
    SUPABASE_KEY = ""

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- Helper function to upload CSV via Supabase REST API ---
def upload_csv_to_supabase(csv_path, table_name):
    """
    Uploads a CSV file to a Supabase table.
    """
    if not os.path.exists(csv_path):
        st.warning(f"⚠️ File not found: {csv_path}")
        return

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            st.warning(f"⚠️ File exists but is empty: {csv_path}")
            return

        st.write(f"📄 Preview of `{table_name}` data:", df.head())
        st.info(f"Uploading {len(df)} rows to `{table_name}` table...")

        # ✅ Clean out all non-JSON-safe values (NaN, inf, -inf)
        df = df.applymap(lambda x: None if pd.isna(x) or x in [float("inf"), float("-inf")] else x)

        # Convert to list of dicts for Supabase API
        records = df.to_dict('records')
        
        # This is a mock function as we don't have access to the actual Supabase API.
        # The real implementation would use requests.post or a similar method.
        # For demonstration, we'll just show the payload.
        st.success(f"Successfully prepared data for `{table_name}`. The following data would be sent:")
        st.json(records[:5]) # Displaying first 5 records as an example
        
    except Exception as e:
        st.error(f"Error uploading CSV to Supabase: {e}")

# --- Helper function to format paper codes ---
def _format_paper_code(code):
    """
    Formats a paper code by making it uppercase and removing spaces.
    """
    if isinstance(code, str):
        return code.strip().upper().replace(' ', '')
    return str(code)

# # New helper function based on pdftocsv.py's extract_metadata, but using "UNSPECIFIED" defaults
def extract_metadata_from_pdf_text(text): 
    # Extract Class Group and Year like "BSC", "2YEAR" 
    class_match = re.search(r'([A-Z]+)\s*/?\s*(\d+(SEM|YEAR))', text) 
    class_val = f"{class_match.group(1)} {class_match.group(2)}" if class_match else "UNSPECIFIED_CLASS" 
    
    # Use regex to extract mode and type from the structured pattern
    # Looking for pattern like "BA / 1YEAR / PRIVATE / SUPP / MAR-2025"
    pattern_match = re.search(r'([A-Z]+)\s*/\s*(\d+(?:SEM|YEAR))\s*/\s*([A-Z]+)\s*/\s*([A-Z]+)\s*/\s*MAR-2025', text)
    
    if pattern_match:
        mode_type = pattern_match.group(3)  # Third element (PRIVATE/REGULAR)
        type_type = pattern_match.group(4)  # Fourth element (SUPP/REGULAR/etc)
    else:
        # Fallback to your original logic but with better ordering
        mode_type = "UNSPECIFIED_MODE" 
        # Check for PRIVATE first since it's more specific
        for keyword_mode in ["PRIVATE", "REGULAR"]: 
            if keyword_mode in text.upper(): 
                mode_type = keyword_mode 
                break 
                
        type_type = "UNSPECIFIED_TYPE" 
        # Check for more specific types first
        for keyword_type in ["ATKT", "SUPP", "EXR", "REGULAR", "PRIVATE"]: 
            if keyword_type in text.upper(): 
                type_type = keyword_type 
                break 

    paper_code = re.search(r'Paper Code[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
    paper_code_val = _format_paper_code(paper_code.group(1)) if paper_code else "UNSPECIFIED_PAPER_CODE" # Use formatter
    
    paper_name = re.search(r'Paper Name[:\s]*(.+?)(?:\n|$)', text)
    paper_name_val = paper_name.group(1).strip() if paper_name else "UNSPECIFIED_PAPER_NAME"
    
    return { 
        "class": class_val, 
        "mode": mode_type, 
        "type": type_type,  
        "room_number": "", 
        "seat_numbers": [""] * 10, 
        "paper_code": paper_code_val, 
        "paper_name": paper_name_val 
    }
    
def extract_roll_numbers(text):
    """
    Extracts unique, sorted 9-digit roll numbers from text.
    """
    # Use a set to automatically handle duplicates during extraction
    return sorted(list(set(re.findall(r'\b\d{9}\b', text)))) # De-duplicate and sort

def format_sitting_plan_rows(rolls, paper_folder_name, meta):
    """
    Formats a list of roll numbers into rows for the sitting plan CSV.
    """
    rows = []
    for i in range(0, len(rolls), 10):
        row = rolls[i:i+10]
        while len(row) < 10:
            row.append("")  # pad to ensure 10 roll number columns
        row.extend([
            meta["class"],
            meta["mode"],
            meta["type"],
            meta["room_number"]
        ])
        row.extend(meta["seat_numbers"]) # These are initially blank, filled later by assignment
        row.append(paper_folder_name)   # Use folder name as Paper
        row.append(meta["paper_code"])
        row.append(meta["paper_name"])
        rows.append(row)
    return rows

# --- Integration of pdftocsv.py logic ---
def process_sitting_plan_pdfs(zip_file_buffer, output_sitting_plan_path, output_timetable_path):
    """
    Processes a ZIP of sitting plan PDFs and generates sitting plan and timetable CSVs.
    """
    all_rows = []
    sitting_plan_columns = [f"Roll Number {i+1}" for i in range(10)]
    sitting_plan_columns += ["Class", "Mode", "Type", "Room Number"]
    sitting_plan_columns += [f"Seat Number {i+1}" for i in range(10)]
    sitting_plan_columns += ["Paper", "Paper Code", "Paper Name"]

    unique_exams_for_timetable = [] # To collect data for incomplete timetable

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_file_buffer, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)
        
        base_dir = tmpdir
        # Check if there's a 'pdf_folder' sub-directory inside the extracted content
        extracted_contents = os.listdir(tmpdir)
        if 'pdf_folder' in extracted_contents and os.path.isdir(os.path.join(tmpdir, 'pdf_folder')):
            base_dir = os.path.join(tmpdir, 'pdf_folder')
        elif len(extracted_contents) == 1 and os.path.isdir(os.path.join(tmpdir, extracted_contents[0])):
            # If there's only one folder at the root, assume it's the base_dir
            base_dir = os.path.join(tmpdir, extracted_contents[0])

        processed_files_count = 0
        for folder_name in os.listdir(base_dir):
            folder_path = os.path.join(base_dir, folder_name)
            if os.path.isdir(folder_path):
                for file in os.listdir(folder_path):
                    if file.lower().endswith(".pdf"):
                        pdf_path = os.path.join(folder_path, file)
                        try:
                            doc = fitz.open(pdf_path)
                            full_text = "\n".join(page.get_text() for page in doc)
                            doc.close()
                            
                            # Use the new extract_metadata_from_pdf_text function
                            current_meta = extract_metadata_from_pdf_text(full_text)
                            
                            # Ensure paper_code and paper_name fallback to folder_name if still unspecified
                            if current_meta['paper_code'] == "UNSPECIFIED_PAPER_CODE":
                                current_meta['paper_code'] = folder_name
                            if current_meta['paper_name'] == "UNSPECIFIED_PAPER_NAME":
                                current_meta['paper_name'] = folder_name

                            rolls = extract_roll_numbers(full_text) # This now de-duplicates and sorts
                            rows = format_sitting_plan_rows(rolls, paper_folder_name=folder_name, meta=current_meta)
                            all_rows.extend(rows)
                            processed_files_count += 1
                            st.info(f"✔ Processed: {file} ({len(rolls)} unique roll numbers)")

                            # Collect unique exam details for timetable generation
                            unique_exams_for_timetable.append({
                                'Class': current_meta['class'],
                                'Paper': folder_name, # Use folder name as Paper
                                'Paper Code': current_meta['paper_code'],
                                'Paper Name': current_meta['paper_name']
                            })

                        except Exception as e:
                            st.error(f"❌ Failed to process {file}: {e}")
    
    # --- Sitting Plan Update Logic ---
    if all_rows:
        df_new_sitting_plan = pd.DataFrame(all_rows, columns=sitting_plan_columns)

        # Load existing sitting plan data
        existing_sitting_plan_df = pd.DataFrame()
        if os.path.exists(output_sitting_plan_path):
            try:
                existing_sitting_plan_df = pd.read_csv(output_sitting_plan_path, dtype={
                    f"Roll Number {i}": str for i in range(1, 11)
                })
                existing_sitting_plan_df.columns = existing_sitting_plan_df.columns.str.strip()
                if 'Paper Code' in existing_sitting_plan_df.columns:
                    existing_sitting_plan_df['Paper Code'] = existing_sitting_plan_df['Paper Code'].apply(_format_paper_code)
            except Exception as e:
                st.warning(f"Could not load existing sitting plan data for update: {e}. Starting fresh for sitting plan.")
                existing_sitting_plan_df = pd.DataFrame(columns=sitting_plan_columns)

        # Ensure all columns are present in both DataFrames before concatenation
        # Add missing columns to df_new_sitting_plan from existing_sitting_plan_df
        for col in existing_sitting_plan_df.columns:
            if col not in df_new_sitting_plan.columns:
                df_new_sitting_plan[col] = pd.NA
        # Add missing columns to existing_sitting_plan_df from df_new_sitting_plan
        for col in df_new_sitting_plan.columns:
            if col not in existing_sitting_plan_df.columns:
                existing_sitting_plan_df[col] = pd.NA

        # Reorder columns to match existing_sitting_plan_df before concatenation
        df_new_sitting_plan = df_new_sitting_plan[existing_sitting_plan_df.columns]

        # Concatenate and remove duplicates
        combined_sitting_plan_df = pd.concat([existing_sitting_plan_df, df_new_sitting_plan], ignore_index=True)

        # Define columns for identifying unique sitting plan entries.
        roll_num_cols = [f"Roll Number {i+1}" for i in range(10)]
        
        # Using all relevant columns to define uniqueness for sitting plan entries
        subset_cols_sitting_plan = roll_num_cols + ["Class", "Mode", "Type", "Room Number", "Paper", "Paper Code", "Paper Name"]
        
        # Filter subset_cols_sitting_plan to only include columns actually present in the DataFrame
        existing_subset_cols_sitting_plan = [col for col in subset_cols_sitting_plan if col in combined_sitting_plan_df.columns]

        # Fill NaN values with empty strings before dropping duplicates for consistent hashing
        combined_sitting_plan_df_filled = combined_sitting_plan_df.fillna('')
        df_sitting_plan_final = combined_sitting_plan_df_filled.drop_duplicates(subset=existing_subset_cols_sitting_plan, keep='first')

        df_sitting_plan_final.to_csv(output_sitting_plan_path, index=False)
        st.success(f"Successfully processed {processed_files_count} PDFs and updated sitting plan to {output_sitting_plan_path}")
    else:
        st.warning("No roll numbers extracted from PDFs to update sitting plan.")

    # --- Timetable Update Logic ---
    if unique_exams_for_timetable:
        df_new_timetable_entries = pd.DataFrame(unique_exams_for_timetable).drop_duplicates().reset_index(drop=True)

        # Define expected structure
        expected_columns = ["SN", "Date", "Shift", "Time", "Class", "Paper", "Paper Code", "Paper Name"]

        # Load existing timetable if exists
        if os.path.exists(output_timetable_path):
            try:
                existing_timetable_df = pd.read_csv(output_timetable_path)
                existing_timetable_df.columns = existing_timetable_df.columns.str.strip()
                if 'Paper Code' in existing_timetable_df.columns:
                    existing_timetable_df['Paper Code'] = existing_timetable_df['Paper Code'].astype(str).str.strip()
            except Exception as e:
                st.warning(f"Could not load existing timetable: {e}. Starting fresh.")
                existing_timetable_df = pd.DataFrame(columns=expected_columns)
        else:
            existing_timetable_df = pd.DataFrame(columns=expected_columns)

        # Add missing columns to both DataFrames
        for col in expected_columns:
            if col not in df_new_timetable_entries.columns:
                df_new_timetable_entries[col] = pd.NA
            if col not in existing_timetable_df.columns:
                existing_timetable_df[col] = pd.NA

        # Reorder columns
        df_new_timetable_entries = df_new_timetable_entries[expected_columns]
        existing_timetable_df = existing_timetable_df[expected_columns]

        # Concatenate and deduplicate using relevant fields
        combined_df = pd.concat([existing_timetable_df, df_new_timetable_entries], ignore_index=True)

        # Fields that define uniqueness of a timetable entry (excluding SN)
        unique_fields = ["Date", "Shift", "Time", "Class", "Paper", "Paper Code", "Paper Name"]

        # Remove duplicates based on content
        df_timetable_final = combined_df.drop_duplicates(subset=unique_fields, keep='first').reset_index(drop=True)

        # Reassign serial numbers
        df_timetable_final["SN"] = range(1, len(df_timetable_final) + 1)

        # Save final CSV
        df_timetable_final.to_csv(output_timetable_path, index=False)
        st.success(f"Timetable updated at {output_timetable_path}.")
        return True, "Timetable deduplicated and saved successfully."
    
    else:
        st.warning("No unique exam details found to generate timetable.")
        return False, "No data to process."
    return True, "PDF processing complete."

# --- Integration of rasa_pdf.py logic ---
def parse_pdf_content(text):
    """
    Parses PDF text for attestation details.
    """
    students = re.split(r"\n?RollNo\.\:\s*", text)
    students = [s.strip() for s in students if s.strip()]

    student_records = []

    for s in students:
        lines = s.splitlines()
        lines = [line.strip() for line in lines if line.strip()]

        def extract_after(label):
            for i, line in enumerate(lines):
                if line.startswith(label):
                    value = line.replace(label, "", 1).strip() # Use count=1 for replace
                    if value:
                        return value
                    elif i+1 < len(lines):
                        return lines[i+1].strip()
                # Special handling for "Regular/Backlog" as it might be on the next line
                if label == "Regular/ Backlog:" and line.startswith("Regular/Backlog"):
                    value = line.replace("Regular/Backlog", "", 1).strip() # Use count=1 for replace
                    if value:
                        return value
                    elif i+1 < len(lines):
                        return lines[i+1].strip()
            return "" # Return empty string if label not found or value is empty

        roll_no = re.match(r"(\d{9})", lines[0]).group(1) if lines and re.match(r"(\d{9})", lines[0]) else ""
        enrollment = extract_after("Enrollment No.:")
        session = extract_after("Session:")
        regular = extract_after("Regular/ Backlog:")
        student_name = extract_after("Name:")
        father = extract_after("Father's Name:")
        mother = extract_after("Mother's Name:")
        gender = extract_after("Gender:")
        exam_name = extract_after("Exam Name:")
        centre = extract_after("Exam Centre:")
        college = extract_after("College Nmae:") # Note: Original script had 'Nmae'
        address = extract_after("Address:")

        papers = re.findall(r"([^\n]+?\[\d{5}\][^\n]*)", s) # Corrected regex for paper code

        student_data = {
            "Roll Number": roll_no,
            "Enrollment Number": enrollment,
            "Session": session,
            "Regular/Backlog": regular,
            "Name": student_name,
            "Father's Name": father,
            "Mother's Name": mother,
            "Gender": gender,
            "Exam Name": exam_name,
            "Exam Centre": centre,
            "College Name": college,
            "Address": address
        }

        for i, paper in enumerate(papers[:10]):
            student_data[f"Paper {i+1}"] = paper.strip()

        student_records.append(student_data)
    return student_records

def process_attestation_pdfs(zip_file_buffer, output_csv_path):
    """
    Processes a ZIP of attestation PDFs and generates an attestation CSV.
    """
    all_data = []

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_file_buffer, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)
        
        # Assuming PDFs are directly in the extracted folder or a subfolder named 'rasa_pdf'
        pdf_base_dir = tmpdir
        if 'rasa_pdf' in os.listdir(tmpdir) and os.path.isdir(os.path.join(tmpdir, 'rasa_pdf')):
            pdf_base_dir = os.path.join(tmpdir, 'rasa_pdf')

        processed_files_count = 0
        for filename in os.listdir(pdf_base_dir):
            if filename.lower().endswith(".pdf"):
                pdf_path = os.path.join(pdf_base_dir, filename)
                try:
                    doc = fitz.open(pdf_path)
                    text = "\n".join([page.get_text() for page in doc])
                    doc.close()
                    st.info(f"📄 Extracting: {filename}")
                    all_data.extend(parse_pdf_content(text))
                    processed_files_count += 1
                except Exception as e:
                    st.error(f"❌ Failed to process {filename}: {e}")
    
    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(output_csv_path, index=False)
        return True, f"Successfully processed {processed_files_count} attestation PDFs and saved to {output_csv_path}"
    else:
        return False, "No data extracted from attestation PDFs."

# --- Integration of college_statistic.py logic ---
def generate_college_statistics(input_csv_path, output_csv_path):
    """
    Generates college statistics from an attestation CSV.
    """
    if not os.path.exists(input_csv_path):
        return False, f"Input file not found: {input_csv_path}. Please process attestation PDFs first."

    try:
        # Load data
        df = pd.read_csv(input_csv_path, dtype={"Roll Number": str, "Enrollment Number": str})

        # Basic cleaning
        df['College Name'] = df['College Name'].fillna('UNKNOWN').astype(str).str.strip().str.upper()
        df['Exam Name'] = df['Exam Name'].fillna('UNKNOWN').astype(str).str.strip().str.upper()
        df['Regular/Backlog'] = df['Regular/Backlog'].astype(str).str.strip().str.upper()

        # Extract class group and year
        def extract_class_group_and_year(exam_name):
            if pd.isna(exam_name):
                return "UNKNOWN", "UNKNOWN"

            exam_name = str(exam_name).upper().strip()

            # Match pattern like BCOM - Commerce [C032] - 1YEAR or BED - PLAIN[PLAIN] - 2SEM
            match = re.match(r'^([A-Z]+)\s*-\s*.+\[\w+\]\s*-\s*(\d+(ST|ND|RD|TH)?(YEAR|SEM))$', exam_name)
            if match:
                class_group = match.group(1).strip()
                year_or_sem = match.group(2).strip()
                return class_group, year_or_sem

            # Fallback: try to extract roman numeral patterns like II YEAR
            roman = re.search(r'\b([IVXLCDM]+)\s*(YEAR|SEM)\b', exam_name)
            if roman:
                return "UNKNOWN", roman.group(0).strip()

            return "UNKNOWN", "UNSPECIFIED"

        df[["Class Group", "Year"]] = df["Exam Name"].apply(lambda x: pd.Series(extract_class_group_and_year(x)))
        

        # Group definitions
        class_groups = sorted(df["Class Group"].dropna().unique())
        college_list = sorted(df["College Name"].dropna().unique())

        # Count function
        def get_counts(df, college, group, year):
            subset = df[(df["College Name"] == college) & (df["Class Group"] == group) & (df["Year"] == year)]
            total = len(subset)
            regular = len(subset[subset["Regular/Backlog"] == "REGULAR"])
            private = len(subset[subset["Regular/Backlog"] == "PRIVATE"])
            exr = len(subset[subset["Regular/Backlog"] == "EXR"])
            supp = len(subset[subset["Regular/Backlog"] == "SUPP"])
            atkt = len(subset[subset["Regular/Backlog"] == "ATKT"])
            return [total, regular, private, exr, atkt, supp]

        # Prepare output structure
        output_rows = []

        for group in class_groups:
            years = sorted(df[df["Class Group"] == group]["Year"].dropna().unique())

            # Header rows
            header_row1 = ["Class"] + [f"{group} - {year}" for year in years for _ in range(5)]
            header_row2 = ["College", "Grand Total"] + ["Total", "Regular", "Private", "EXR", "ATKT", "SUPP"] * len(years)

            block_data = []
            for college in college_list:
                row = [college]
                grand_total = 0
                for year in years:
                    t, r, p, x, a, s = get_counts(df, college, group, year)
                    row += [t, r, p, x, a, s]
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

        # Save final output
        pd.DataFrame(output_rows).to_csv(output_csv_path, index=False, header=False)
        return True, f"✅ College statistics saved to {output_csv_path}"

    except Exception as e:
        return False, f"❌ Error generating college statistics: {e}"


# --- Main Streamlit App Logic ---
def authenticate_cs(username, password):
    """
    Authenticates Centre Superintendent credentials.
    This is a mock function.
    """
    if username == "cs" and password == "123":
        return True
    return False

def upload_pdf_files():
    """
    Allows user to upload a ZIP file and processes the PDFs inside.
    """
    st.header("Upload and Process PDFs")
    uploaded_file = st.file_uploader("Upload a ZIP file containing PDFs", type="zip")
    if uploaded_file:
        process_type = st.radio("Select PDF Processing Type:", 
                                ("Sitting Plan & Timetable", "Attestation Form & Statistics"))

        if st.button("Process PDFs"):
            st.info("Processing your PDFs...")
            zip_buffer = io.BytesIO(uploaded_file.getvalue())

            if process_type == "Sitting Plan & Timetable":
                sitting_plan_csv = "sitting_plan.csv"
                timetable_csv = "timetable.csv"
                result, msg = process_sitting_plan_pdfs(zip_buffer, sitting_plan_csv, timetable_csv)
                if result:
                    st.success(f"PDFs processed. {msg}")
                    if os.path.exists(sitting_plan_csv) and os.path.exists(timetable_csv):
                        st.download_button(
                            label="Download Sitting Plan CSV",
                            data=open(sitting_plan_csv, "rb").read(),
                            file_name="sitting_plan.csv",
                            mime="text/csv",
                        )
                        st.download_button(
                            label="Download Timetable CSV",
                            data=open(timetable_csv, "rb").read(),
                            file_name="timetable.csv",
                            mime="text/csv",
                        )
            
            elif process_type == "Attestation Form & Statistics":
                attestation_csv = "attestation.csv"
                result, msg = process_attestation_pdfs(zip_buffer, attestation_csv)
                if result:
                    st.success(f"PDFs processed. {msg}")
                    st.download_button(
                        label="Download Attestation CSV",
                        data=open(attestation_csv, "rb").read(),
                        file_name="attestation.csv",
                        mime="text/csv",
                    )
                    
                    st.subheader("Generate College Statistics")
                    st.info("Click the button below to generate a college statistics report from the attestation data.")
                    if st.button("Generate Statistics"):
                        stats_csv = "college_statistics.csv"
                        stats_result, stats_msg = generate_college_statistics(attestation_csv, stats_csv)
                        if stats_result:
                            st.success(stats_msg)
                            st.download_button(
                                label="Download College Statistics CSV",
                                data=open(stats_csv, "rb").read(),
                                file_name="college_statistics.csv",
                                mime="text/csv",
                            )
                        else:
                            st.error(stats_msg)

def generate_room_chart_csv(output_sitting_plan_path, timetable_path):
    """
    Generates a room chart based on sitting plan and timetable data.
    """
    if not os.path.exists(output_sitting_plan_path) or not os.path.exists(timetable_path):
        st.warning("Sitting plan or timetable files not found. Please process PDFs first.")
        return
        
    st.header("Generate Room Chart")

    try:
        df_sitting_plan = pd.read_csv(output_sitting_plan_path, dtype={f"Roll Number {i}": str for i in range(1, 11)})
        df_timetable = pd.read_csv(timetable_path)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    # Use a dummy timetable for demonstration if dates are not present
    if 'Date' not in df_timetable.columns or df_timetable['Date'].isnull().all():
        st.warning("Timetable dates are not available. Using a dummy date.")
        if df_timetable.empty:
             st.error("Timetable is empty. Cannot generate room chart.")
             return
        df_timetable['Date'] = datetime.date.today().strftime('%Y-%m-%d')
        df_timetable['Shift'] = 'Dummy Shift'

    dates = sorted(df_timetable['Date'].unique())
    shifts = sorted(df_timetable['Shift'].unique())
    
    selected_date = st.selectbox("Select Date:", dates)
    selected_shift = st.selectbox("Select Shift:", shifts)

    if st.button("Generate Room Chart"):
        if 'Room Number' not in df_sitting_plan.columns or df_sitting_plan['Room Number'].isnull().all():
            st.warning("Room numbers are not assigned yet. Please assign them first.")
            return

        room_chart_rows = []
        for room_num in sorted(df_sitting_plan['Room Number'].unique()):
            room_df = df_sitting_plan[df_sitting_plan['Room Number'] == room_num]
            
            # Assuming Paper is the key to link to the timetable
            papers_in_room = room_df['Paper Code'].unique()
            
            # Find the corresponding timetable entries for the selected date and shift
            exam_info = df_timetable[(df_timetable['Date'] == selected_date) & 
                                     (df_timetable['Shift'] == selected_shift) & 
                                     (df_timetable['Paper Code'].isin(papers_in_room))]
            
            if not exam_info.empty:
                room_chart_rows.append([f"Room No. {room_num}", ""] * 5)
                room_chart_rows.append([
                    "S.No.", "Roll No.", "Paper Code", "Paper Name", "Signature"
                ])
                s_no = 1
                for _, row in room_df.iterrows():
                    roll_numbers = [row[f'Roll Number {i+1}'] for i in range(10) if pd.notna(row[f'Roll Number {i+1}'])]
                    for roll_no in roll_numbers:
                        paper_code = row['Paper Code']
                        paper_name = row['Paper Name']
                        room_chart_rows.append([s_no, roll_no, paper_code, paper_name, ""])
                        s_no += 1
                room_chart_rows.append([])
        
        if room_chart_rows:
            room_chart_output = io.StringIO()
            pd.DataFrame(room_chart_rows).to_csv(room_chart_output, index=False, header=False)
            
            file_name = f"Room_Chart_{selected_date}_{selected_shift}.csv"
            st.success("Room chart generated. You can download it below.")
            st.download_button(
                label="Download Room Chart as CSV",
                data=room_chart_output.getvalue().encode('utf-8'),
                file_name=file_name,
                mime="text/csv",
            )
        else:
            st.warning("Could not generate room chart. Please ensure data is complete and assignments are made.")


def delete_file_app():
    """
    Streamlit application to delete a specified file (e.g., timetable.csv).
    """
    st.header("File Deletion App")
    st.write("This app allows you to delete a specific data file.")

    file_to_delete = st.selectbox("Select file to delete:", ["timetable.csv", "sitting_plan.csv", "attestation.csv", "college_statistics.csv"])
    
    # Check if the file exists
    if os.path.exists(file_to_delete):
        st.info(f"The file '{file_to_delete}' currently exists.")
        if st.button(f"Delete {file_to_delete}"):
            try:
                os.remove(file_to_delete)
                st.success(f"Successfully deleted '{file_to_delete}'.")
            except OSError as e:
                st.error(f"Error: Could not delete '{file_to_delete}'. Reason: {e}")
            st.rerun()
    else:
        st.warning(f"The file '{file_to_delete}' does not exist in the current directory.")
        st.info("You might need to process PDFs first for the file to appear.")


def main_app():
    st.title("Exam Application Bot")

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False

    if not st.session_state['authenticated']:
        st.sidebar.header("Login")
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if authenticate_cs(username, password):
                st.session_state['authenticated'] = True
                st.sidebar.success("Logged in successfully!")
            else:
                st.sidebar.error("Invalid credentials.")
        st.info("Please log in to use the application.")
    else:
        st.sidebar.success("Logged in as Centre Superintendent")
        st.sidebar.button("Logout", on_click=lambda: st.session_state.pop('authenticated'))
        
        app_mode = st.sidebar.selectbox("Choose a function:",
            ["Process PDFs", "Generate Room Chart", "Manage Files", "Upload to Supabase"])
        
        if app_mode == "Process PDFs":
            upload_pdf_files()
        elif app_mode == "Generate Room Chart":
            generate_room_chart_csv("sitting_plan.csv", "timetable.csv")
        elif app_mode == "Manage Files":
            delete_file_app()
        elif app_mode == "Upload to Supabase":
            st.header("Upload Data to Supabase")
            st.info("Note: This is a mock upload for demonstration.")
            upload_option = st.radio("Select data to upload:", ("Sitting Plan", "Timetable", "Attestation"))
            if st.button("Upload to Supabase"):
                if upload_option == "Sitting Plan":
                    upload_csv_to_supabase("sitting_plan.csv", "sitting_plans")
                elif upload_option == "Timetable":
                    upload_csv_to_supabase("timetable.csv", "timetables")
                elif upload_option == "Attestation":
                    upload_csv_to_supabase("attestation.csv", "attestations")
            
# --- Run the application ---
if __name__ == "__main__":
    main_app()
