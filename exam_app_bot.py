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

# --- Supabase config from secrets ---
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"  # Ensure we get the inserted/updated record back
}

# --- Generic Supabase Helper Functions ---
def fetch_data_from_supabase(table_name):
    """Fetches all data from a specified Supabase table."""
    try:
        response = requests.get(f"{SUPABASE_URL}/rest/v1/{table_name}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            df = pd.DataFrame(data)
            return df
        else:
            return pd.DataFrame()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.warning(f"Supabase table '{table_name}' not found. Please ensure it exists.")
        else:
            st.error(f"❌ Error fetching from Supabase table '{table_name}': {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ An unexpected error occurred while fetching data for '{table_name}': {e}")
        return pd.DataFrame()

def save_data_to_supabase(table_name, data_list):
    """
    Saves a list of dictionaries to a Supabase table.
    Performs a full table refresh by deleting existing data first.
    
    Args:
        table_name (str): The name of the table.
        data_list (list): The list of dictionaries to be saved.
    
    Returns:
        bool: True if successful, False otherwise.
        str: A message indicating success or failure.
    """
    if not data_list:
        return False, "Data list is empty, nothing to upload."

    try:
        # Delete existing data for a full refresh
        response = requests.delete(f"{SUPABASE_URL}/rest/v1/{table_name}?id=not.is.null", headers=headers)
        response.raise_for_status()

        # Insert new data
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table_name}",
            headers=headers,
            json=data_list
        )
        response.raise_for_status()
        return True, f"✅ Uploaded {len(data_list)} records to `{table_name}` successfully!"
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Supabase API error for table '{table_name}': {e}")
        return False, f"❌ Error uploading to Supabase table '{table_name}': {e}"
    except Exception as e:
        st.error(f"❌ An unexpected error occurred while saving data for '{table_name}': {e}")
        return False, f"❌ An unexpected error occurred while saving data for '{table_name}': {e}"

# --- Supabase-specific Load/Save Functions for each table ---
def load_shift_assignments_supabase():
    df = fetch_data_from_supabase("shift_assignments")
    if not df.empty:
        # Convert string representations of lists back to actual lists for roles
        for role in ["senior_center_superintendent", "center_superintendent", "assistant_center_superintendent",
                     "permanent_invigilator", "assistant_permanent_invigilator",
                     "class_3_worker", "class_4_worker"]:
            if role in df.columns:
                df[role] = df[role].apply(lambda x: ast.literal_eval(x) if pd.notna(x) and x.strip() else [])
    return df

def save_shift_assignment_supabase(date, shift, assignments):
    data_for_db = {
        'date': date,
        'shift': shift,
        'senior_center_superintendent': str(assignments.get('senior_center_superintendent', [])),
        'center_superintendent': str(assignments.get('center_superintendent', [])),
        'assistant_center_superintendent': str(assignments.get('assistant_center_superintendent', [])),
        'permanent_invigilator': str(assignments.get('permanent_invigilator', [])),
        'assistant_permanent_invigilator': str(assignments.get('assistant_permanent_invigilator', [])),
        'class_3_worker': str(assignments.get('class_3_worker', [])),
        'class_4_worker': str(assignments.get('class_4_worker', []))
    }
    
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/shift_assignments?date=eq.{date}&shift=eq.{shift}",
            headers=headers
        )
        response.raise_for_status()
        existing_records = response.json()

        if existing_records:
            # Update existing record (PATCH)
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/shift_assignments?date=eq.{date}&shift=eq.{shift}",
                headers=headers,
                json=data_for_db
            )
            response.raise_for_status()
            return True, "Shift assignments updated in Supabase successfully!"
        else:
            # Insert new record (POST)
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/shift_assignments",
                headers=headers,
                json=data_for_db
            )
            response.raise_for_status()
            return True, "Shift assignments saved to Supabase successfully!"
    except requests.exceptions.HTTPError as e:
        return False, f"Error saving shift assignments to Supabase: {e}"


def load_data_supabase():
    sitting_plan_df = fetch_data_from_supabase("sitting_plan")
    timetable_df = fetch_data_from_supabase("timetable")
    assigned_seats_df = fetch_data_from_supabase("assigned_seats")

    if not sitting_plan_df.empty:
        sitting_plan_df.columns = sitting_plan_df.columns.str.strip()
        if 'Paper Code' in sitting_plan_df.columns:
            sitting_plan_df['Paper Code'] = sitting_plan_df['Paper Code'].apply(_format_paper_code)
    
    if not timetable_df.empty:
        timetable_df.columns = timetable_df.columns.str.strip()
        if 'Paper Code' in timetable_df.columns:
            timetable_df['Paper Code'] = timetable_df['Paper Code'].apply(_format_paper_code)
    
    if not assigned_seats_df.empty:
        assigned_seats_df['Paper Code'] = assigned_seats_df['Paper Code'].apply(_format_paper_code)
    else:
        assigned_seats_df = pd.DataFrame(columns=["Roll Number", "Paper Code", "Paper Name", "Room Number", "Seat Number", "Date", "Shift"])
        
    return sitting_plan_df, timetable_df, assigned_seats_df

# --- PDF Extraction and Supabase Upload Logic (New) ---
def _format_paper_code(code_str):
    if pd.isna(code_str) or not code_str:
        return ""
    s = str(code_str).strip()
    if s.endswith('.0') and s[:-2].isdigit():
        return s[:-2]
    return s

def _extract_sitting_plan_data(pdf_path):
    """Extracts sitting plan data from a single PDF."""
    sitting_plan_data = []
    
    # Simple regex patterns to identify key information
    class_pattern = re.compile(r'Class:\s*([\w\s]+)', re.IGNORECASE)
    paper_pattern = re.compile(r'Paper\s*Code:\s*([\w-]+)\s*,\s*Paper\s*Name:\s*([\w\s]+)', re.IGNORECASE)
    room_pattern = re.compile(r'Room\s*No:\s*(\w+)', re.IGNORECASE)
    student_pattern = re.compile(r'(\d+)\s+\|\s+([A-Z\d]+)') # Roll No | Seat No

    doc = fitz.open(pdf_path)
    current_class = None
    current_paper_code = None
    current_paper_name = None
    current_room = None
    
    for page in doc:
        text = page.get_text()
        
        # Find class and paper info
        class_match = class_pattern.search(text)
        if class_match:
            current_class = class_match.group(1).strip()
        
        paper_match = paper_pattern.search(text)
        if paper_match:
            current_paper_code = paper_match.group(1).strip()
            current_paper_name = paper_match.group(2).strip()

        # Find room info
        room_match = room_pattern.search(text)
        if room_match:
            current_room = room_match.group(1).strip()

        # Find student entries
        for line in text.split('\n'):
            student_match = student_pattern.search(line)
            if student_match and current_room and current_paper_code:
                roll_number = student_match.group(1).strip()
                seat_number = student_match.group(2).strip()
                
                # Check for existing data to see if we can fill in a row
                # The PDF extraction logic here is simplified.
                # A more robust solution would track seat number columns more accurately.
                # For now, we'll create a simple row per student
                
                sitting_plan_data.append({
                    "Class": current_class,
                    "Paper Code": _format_paper_code(current_paper_code),
                    "Paper Name": current_paper_name,
                    "Room Number": current_room,
                    "Roll Number 1": roll_number,
                    "Seat Number 1": seat_number,
                    "Paper": None, # This might need to be extracted from PDF if available
                    "Mode": None,
                    "Type": None,
                })
    
    doc.close()
    return sitting_plan_data

def _extract_timetable_data(pdf_path):
    """Extracts timetable data from a single PDF."""
    timetable_data = []
    
    # Regex patterns for timetable extraction
    date_pattern = re.compile(r'(\d{2}-\d{2}-\d{4})')
    shift_pattern = re.compile(r'([A-Z][a-z]+)\s*Shift', re.IGNORECASE)
    time_pattern = re.compile(r'Timing:\s*(\d{2}:\d{2}\s*-\s*\d{2}:\d{2})')
    
    # The main pattern for a timetable row: Class | Paper Code | Paper Name
    # This is a highly simplified pattern and may need to be adjusted
    # based on the actual PDF structure.
    row_pattern = re.compile(r'([A-Z\s]+?)\s+\|\s+([\w-]+)\s+\|\s+([A-Z\s]+)')

    doc = fitz.open(pdf_path)
    current_date = None
    current_shift = None
    current_time = None

    for page in doc:
        text = page.get_text()

        # Extract date, shift, time from headers
        date_match = date_pattern.search(text)
        if date_match:
            current_date = date_match.group(1).strip()

        shift_match = shift_pattern.search(text)
        if shift_match:
            current_shift = shift_match.group(1).strip()

        time_match = time_pattern.search(text)
        if time_match:
            current_time = time_match.group(1).strip()

        # Find timetable rows
        for line in text.split('\n'):
            row_match = row_pattern.search(line)
            if row_match and current_date and current_shift and current_time:
                class_name = row_match.group(1).strip()
                paper_code = row_match.group(2).strip()
                paper_name = row_match.group(3).strip()
                
                timetable_data.append({
                    "Date": current_date,
                    "Shift": current_shift,
                    "Time": current_time,
                    "Class": class_name,
                    "Paper Code": _format_paper_code(paper_code),
                    "Paper Name": paper_name
                })
    
    doc.close()
    return timetable_data

def process_zip_and_upload_to_supabase(uploaded_zip, table_name, file_type):
    """
    Extracts PDFs from a ZIP file, parses the data, and uploads it to Supabase.
    """
    if not uploaded_zip:
        return False, "No file uploaded."
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_file = zipfile.ZipFile(uploaded_zip)
            zip_file.extractall(temp_dir)
            
            all_extracted_data = []
            for root, _, files in os.walk(temp_dir):
                for file_name in files:
                    if file_name.endswith('.pdf'):
                        pdf_path = os.path.join(root, file_name)
                        if file_type == "sitting_plan":
                            all_extracted_data.extend(_extract_sitting_plan_data(pdf_path))
                        elif file_type == "timetable":
                            all_extracted_data.extend(_extract_timetable_data(pdf_path))
            
            if not all_extracted_data:
                return False, f"No PDF files found or no data could be extracted from the PDFs in the ZIP for {table_name}."

            success, message = save_data_to_supabase(table_name, all_extracted_data)
            return success, message
            
    except zipfile.BadZipFile:
        return False, "The uploaded file is not a valid ZIP file."
    except Exception as e:
        return False, f"An error occurred during processing: {e}"


# Save uploaded files (for admin panel)
def upload_file_to_supabase(uploaded_file_content, table_name):
    """Uploads a DataFrame to a Supabase table. (Kept for other uploads if needed)"""
    try:
        df = pd.read_csv(io.BytesIO(uploaded_file_content))
        if df.empty:
            st.warning(f"⚠️ Uploaded file is empty.")
            return False, "File is empty"

        st.write(f"📄 Preview of `{table_name}` data:", df.head())
        st.info(f"Uploading {len(df)} rows to `{table_name}` table...")

        # Clean out all non-JSON-safe values (NaN, inf, -inf)
        df = df.applymap(lambda x: None if pd.isna(x) or x in [float("inf"), float("-inf")] else x)

        # Convert to list of dicts
        data = df.to_dict(orient="records")
        
        success, message = save_data_to_supabase(table_name, data)
        return success, message
    except Exception as e:
        return False, f"❌ Error uploading to Supabase table '{table_name}': {e}"


# --- CSV Helper Functions for CS Reports (now Supabase) ---
def load_cs_reports_supabase():
    df = fetch_data_from_supabase("cs_reports")
    if not df.empty:
        # Convert string representations of lists back to actual lists
        for col in ['absent_roll_numbers', 'ufm_roll_numbers']:
            if col in df.columns:
                df[col] = df[col].astype(str).apply(
                    lambda x: ast.literal_eval(x) if x.strip() and x.strip().lower() != 'nan' else []
                )
    return df

def save_cs_report_supabase(report_key, data):
    data_for_db = data.copy()
    data_for_db['absent_roll_numbers'] = str(data_for_db.get('absent_roll_numbers', []))
    data_for_db['ufm_roll_numbers'] = str(data_for_db.get('ufm_roll_numbers', []))
    
    # Check if report_key exists to decide on PATCH or POST
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/cs_reports?report_key=eq.{report_key}",
            headers=headers
        )
        response.raise_for_status()
        existing_records = response.json()

        if existing_records:
            # Update existing record (PATCH)
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/cs_reports?report_key=eq.{report_key}",
                headers=headers,
                json=data_for_db
            )
            response.raise_for_status()
            return True, "Report updated in Supabase successfully!"
        else:
            # Insert new record (POST)
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/cs_reports",
                headers=headers,
                json=data_for_db
            )
            response.raise_for_status()
            return True, "Report saved to Supabase successfully!"
    except requests.exceptions.HTTPError as e:
        return False, f"Error saving report to Supabase: {e}"

def load_single_cs_report_supabase(report_key):
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/cs_reports?report_key=eq.{report_key}",
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        if data:
            record = data[0]
            # Convert string representations of lists back to actual lists
            for col in ['absent_roll_numbers', 'ufm_roll_numbers']:
                if col in record:
                    record[col] = ast.literal_eval(record[col])
            return True, record
        else:
            return False, {}
    except requests.exceptions.HTTPError as e:
        st.error(f"Error fetching report: {e}")
        return False, {}

# --- Exam Team Members Functions (now Supabase) ---
def load_exam_team_members_supabase():
    df = fetch_data_from_supabase("exam_team_members")
    if not df.empty:
        return df['name'].tolist()
    return []

def save_exam_team_members_supabase(members):
    # For simplicity, we'll clear the table and insert the new list
    try:
        requests.delete(f"{SUPABASE_URL}/rest/v1/exam_team_members?id=not.is.null", headers=headers)
        
        data = [{"name": member} for member in sorted(list(set(members)))]
        
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/exam_team_members",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        return True, "Exam team members saved to Supabase successfully!"
    except requests.exceptions.HTTPError as e:
        return False, f"Error saving exam team members: {e}"


# Admin login (simple hardcoded credentials)
def admin_login():
    user = st.text_input("Username", type="default")
    pwd = st.text_input("Password", type="password")
    return user == "admin" and pwd == "admin123"

# Centre Superintendent login (simple hardcoded credentials)
def cs_login():
    user = st.text_input("CS Username", type="default")
    pwd = st.text_input("CS Password", type="password")
    return user == "cs_admin" and pwd == "cs_pass123"

# Refactored helper function to get raw student data for a session
def _get_session_students_raw_data(date_str, shift, assigned_seats_df, timetable_df):
    """
    Collects raw student data for a given date and shift from assigned_seats_df
    and merges with timetable info.
    Returns a list of dictionaries, each representing an assigned student.
    """
    all_students_data = []

    # Filter timetable for the given date and shift
    current_day_exams_tt = timetable_df[
        (timetable_df["Date"].astype(str).str.strip() == date_str) &
        (timetable_df["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ].copy()

    if current_day_exams_tt.empty:
        return all_students_data # Return empty list if no exams found

    # Iterate through each exam scheduled for the date/shift in the timetable
    for _, tt_row in current_day_exams_tt.iterrows():
        tt_class = str(tt_row["Class"]).strip()
        tt_paper_code = str(tt_row["Paper Code"]).strip()
        tt_paper_name = str(tt_row["Paper Name"]).strip()

        # Filter assigned_seats_df for students assigned to this specific exam session
        current_exam_assigned_students = assigned_seats_df[
            (assigned_seats_df["Date"].astype(str).str.strip() == date_str) &
            (assigned_seats_df["Shift"].astype(str).str.strip().str.lower() == shift.lower()) &
            (assigned_seats_df["Paper Code"].astype(str).str.strip() == tt_paper_code) & # Use formatted paper code
            (assigned_seats_df["Paper Name"].astype(str).str.strip() == tt_paper_name)
        ]

        for _, assigned_row in current_exam_assigned_students.iterrows():
            roll_num = str(assigned_row["Roll Number"]).strip()
            room_num = str(assigned_row["Room Number"]).strip()
            seat_num_raw = str(assigned_row["Seat Number"]).strip()

            seat_num_display = ""
            seat_num_sort_key = None
            try:
                # Handle alphanumeric seats for sorting (e.g., 1A, 2A, 1B, 2B)
                if re.match(r'^\d+[A-Z]$', seat_num_raw):
                    num_part = int(re.match(r'^(\d+)', seat_num_raw).group(1))
                    char_part = re.search(r'([A-Z])$', seat_num_raw).group(1)
                    # Assign a tuple for sorting: (char_order, number)
                    seat_num_sort_key = (ord(char_part), num_part)
                    seat_num_display = seat_num_raw
                elif seat_num_raw.isdigit():
                    seat_num_sort_key = (float('inf'), int(seat_num_raw)) # Numeric seats after alphanumeric
                    seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                else:
                    seat_num_sort_key = (float('inf'), float('inf')) # Fallback for other formats
                    seat_num_display = seat_num_raw if seat_num_raw else "N/A"
            except ValueError:
                seat_num_sort_key = (float('inf'), float('inf')) # Fallback for other formats
                seat_num_display = seat_num_raw if seat_num_raw else "N/A"

            all_students_data.append({
                "roll_num": roll_num,
                "room_num": room_num,
                "seat_num_display": seat_num_display, # This is what will be displayed/exported
                "seat_num_sort_key": seat_num_sort_key, # This is for sorting
                "paper_name": tt_paper_name,
                "paper_code": tt_paper_code,
                "class_name": tt_class,
                "date": date_str,
                "shift": shift
            })
    return all_students_data

def get_all_students_for_date_shift_formatted(date_str, shift, assigned_seats_df, timetable):
    all_students_data = _get_session_students_raw_data(date_str, shift, assigned_seats_df, timetable)

    if not all_students_data:
        return None, "No students found for the selected date and shift.", None

    # Sort the collected data by Room Number, then Seat Number
    all_students_data.sort(key=lambda x: (x['room_num'], x['seat_num_sort_key']))

    # Extract exam_time and class_summary_header from timetable (similar to original logic)
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]
    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"
    unique_classes = current_day_exams_tt['Class'].dropna().astype(str).str.strip().unique()
    class_summary_header = ""
    if len(unique_classes) == 1:
        class_summary_header = f"{unique_classes[0]} Examination {datetime.datetime.now().year}"
    elif len(unique_classes) > 1:
        class_summary_header = f"Various Classes Examination {datetime.datetime.now().year}"
    else:
        class_summary_header = f"Examination {datetime.datetime.now().year}"

    # --- Prepare text output ---
    output_string_parts = []
    output_string_parts.append("जीवाजी विश्वविद्यालय ग्वालियर")
    output_string_parts.append("परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107")
    output_string_parts.append(class_summary_header)
    output_string_parts.append(f"दिनांक :-{date_str}")
    output_string_parts.append(f"पाली :-{shift}")
    output_string_parts.append(f"समय :-{exam_time}")

    students_by_room = {}
    for student in all_students_data:
        room = student['room_num']
        if room not in students_by_room:
            students_by_room[room] = []
        students_by_room[room].append(student)

    for room_num in sorted(students_by_room.keys()):
        output_string_parts.append(f" कक्ष :-{room_num}")
        current_room_students = students_by_room[room_num]

        num_cols = 10

        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]

            # Create a single line for 10 students
            single_line_students = []
            for student in block_students:
                line_part = f"{student['seat_num_display']} {student['roll_num']} ({student['paper_code']})"
                single_line_students.append(line_part)

            output_string_parts.append("  ".join(single_line_students))

    output_string_parts.append("  \n")
    output_string_parts.append("---------------------------------------------------------------------------------------------------------------------------")
    output_string_parts.append("Controller of Examinations                                                                                      Centre Superintendent")
    output_string_parts.append("---------------------------------------------------------------------------------------------------------------------------")

    text_output = "\n".join(output_string_parts)
    return text_output, None, None

def get_all_exams(roll_number, sitting_plan_df, timetable_df):
    """
    Finds all exams for a given roll number and returns a DataFrame.
    """
    roll_number = str(roll_number).strip()
    
    exam_schedule = pd.DataFrame(columns=[
        "Date", "Shift", "Time", "Paper", "Paper Name", "Paper Code", "Class", "Mode", "Type"
    ])
    
    # Find rows in the sitting plan that contain the roll number
    matching_sitting_plan_rows = sitting_plan_df[
        sitting_plan_df.apply(
            lambda row: roll_number in [str(row[f"Roll Number {i}"]) for i in range(1, 11) if pd.notna(row[f"Roll Number {i}"])],
            axis=1
        )
    ]
    
    if matching_sitting_plan_rows.empty:
        return []
    
    for _, sp_row in matching_sitting_plan_rows.iterrows():
        paper_code = _format_paper_code(sp_row.get("Paper Code"))
        
        matching_timetable_rows = timetable_df[
            timetable_df['Paper Code'].apply(_format_paper_code) == paper_code
        ]
        
        for _, tt_row in matching_timetable_rows.iterrows():
            new_row = {
                "Date": tt_row.get("Date"),
                "Shift": tt_row.get("Shift"),
                "Time": tt_row.get("Time"),
                "Paper": sp_row.get("Paper"),
                "Paper Name": sp_row.get("Paper Name"),
                "Paper Code": paper_code,
                "Class": sp_row.get("Class"),
                "Mode": sp_row.get("Mode"),
                "Type": sp_row.get("Type")
            }
            exam_schedule = pd.concat([exam_schedule, pd.DataFrame([new_row])], ignore_index=True)
            
    return exam_schedule.drop_duplicates()

def get_sitting_details(roll_number, date_str, sitting_plan_df, timetable_df):
    """
    Finds sitting details for a given roll number on a specific date.
    """
    roll_number = str(roll_number).strip()
    date_str = str(date_str).strip()
    
    all_exams_df = get_all_exams(roll_number, sitting_plan_df, timetable_df)
    
    if all_exams_df.empty:
        return []

    filtered_exams = all_exams_df[all_exams_df["Date"] == date_str]

    if filtered_exams.empty:
        return []

    results = []
    for _, exam_row in filtered_exams.iterrows():
        paper_code = _format_paper_code(exam_row["Paper Code"])
        
        matching_sp_row = sitting_plan_df[
            (sitting_plan_df['Paper Code'].apply(_format_paper_code) == paper_code) &
            (sitting_plan_df.apply(
                lambda row: roll_number in [str(row[f"Roll Number {i}"]) for i in range(1, 11) if pd.notna(row[f"Roll Number {i}"])],
                axis=1
            ))
        ]
        
        if not matching_sp_row.empty:
            result = exam_row.to_dict()
            result['Room Number'] = str(matching_sp_row.iloc[0]['Room Number'])
            
            for i in range(1, 11):
                if str(matching_sp_row.iloc[0].get(f'Roll Number {i}')).strip() == roll_number:
                    seat_num_col = f'Seat Number {i}'
                    result['Seat Number'] = str(matching_sp_row.iloc[0].get(seat_num_col, 'N/A'))
                    break
            else:
                result['Seat Number'] = 'N/A'
                
            results.append(result)
            
    return results

def get_students_in_room(room_number, date_str, shift, assigned_seats_df):
    """
    Retrieves a list of students assigned to a specific room for a given date and shift.
    """
    filtered_df = assigned_seats_df[
        (assigned_seats_df['Room Number'].astype(str).str.strip() == str(room_number).strip()) &
        (assigned_seats_df['Date'].astype(str).str.strip() == date_str) &
        (assigned_seats_df['Shift'].astype(str).str.strip().lower() == shift.lower())
    ]
    
    return filtered_df

def get_sitting_plan_data(date_str, shift, sitting_plan, timetable):
    """
    Generates sitting plan data in a printable format.
    """
    output_string_parts = []
    
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ].copy()

    if current_day_exams_tt.empty:
        return None, "No exams found for the selected date and shift.", None
    
    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"

    output_string_parts.append("जीवाजी विश्वविद्यालय ग्वालियर")
    output_string_parts.append("परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107")
    output_string_parts.append("अस्थाई सीटिंग चार्ट")
    output_string_parts.append(f"दिनांक :-{date_str}")
    output_string_parts.append(f"पाली :-{shift}")
    output_string_parts.append(f"समय :-{exam_time}")

    for _, tt_row in current_day_exams_tt.iterrows():
        tt_class = str(tt_row["Class"]).strip()
        tt_paper_code = _format_paper_code(tt_row["Paper Code"])
        tt_paper_name = str(tt_row["Paper Name"]).strip()

        relevant_sitting_plan_entries = sitting_plan[
            (sitting_plan['Class'].astype(str).str.strip() == tt_class) &
            (sitting_plan['Paper Code'].apply(_format_paper_code) == tt_paper_code) &
            (sitting_plan['Paper Name'].astype(str).str.strip() == tt_paper_name)
        ]
        
        if relevant_sitting_plan_entries.empty:
            continue

        output_string_parts.append(f"  \n")
        output_string_parts.append(f"Class: {tt_class}, Paper Code: {tt_paper_code}, Paper Name: {tt_paper_name}")
        output_string_parts.append("---------------------------------------------------------------------------------------------------------------------------")

        for _, sp_row in relevant_sitting_plan_entries.iterrows():
            room_num = str(sp_row.get('Room Number', ''))
            if not room_num:
                continue
            
            output_string_parts.append(f"  \nRoom No: {room_num}")
            
            header_parts = ["Roll Number", "Seat Number"]
            output_string_parts.append(f"{' | '.join(header_parts)}")
            output_string_parts.append("------------------------------------------")

            for i in range(1, 11):
                roll_col = f"Roll Number {i}"
                seat_col = f"Seat Number {i}"
                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num = str(sp_row.get(seat_col, '')).strip()
                
                if roll_num:
                    output_string_parts.append(f"{roll_num:<12s}| {seat_num}")

    output_string = "\n".join(output_string_parts)
    return output_string, None, None

def _generate_sitting_plan_report_pdf(sitting_plan_text):
    """Generates a PDF from the sitting plan text using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # A4 size
    rect = page.rect.shrink(50)  # Add a margin
    page.insert_text(rect.tl, sitting_plan_text, fontname="helv", fontsize=10)
    
    output = io.BytesIO(doc.tobytes())
    doc.close()
    output.seek(0)
    return output

def get_all_invigilators_for_session(date_str, shift, shift_assignments_df):
    """
    Finds all invigilators assigned to a specific date and shift.
    """
    filtered_df = shift_assignments_df[
        (shift_assignments_df['date'] == date_str) &
        (shift_assignments_df['shift'] == shift)
    ]
    
    if not filtered_df.empty:
        invigilators = filtered_df.iloc[0].get('permanent_invigilator', []) + \
                       filtered_df.iloc[0].get('assistant_permanent_invigilator', [])
        return invigilators
    return []

# --- Main App ---
st.title("Government Law College, Morena (M.P.) Examination Management System")

# Ensure initial data loading is done for all modules
sitting_plan, timetable, assigned_seats_df = load_data_supabase()
exam_team_members = load_exam_team_members_supabase()
shift_assignments_df = load_shift_assignments_supabase()
cs_reports_df = load_cs_reports_supabase()

menu = st.radio("Select Module", ["Student View", "Admin Panel", "Centre Superintendent Panel"])

if menu == "Student View":
    
    if sitting_plan.empty or timetable.empty:
        st.warning("Sitting plan or timetable data not found. Please upload them via the Admin Panel for full functionality.")
    
    option = st.radio("Choose Search Option:", [
        "Search by Roll Number and Date",
        "Get Full Exam Schedule by Roll Number",
        "View Full Timetable"
    ])

    if option == "Search by Roll Number and Date":
        roll = st.text_input("Enter Roll Number", max_chars=9)
        date_input = st.date_input("Enter Exam Date", value=datetime.date.today())
        
        if st.button("Search"):
            if sitting_plan.empty or timetable.empty:
                st.warning("Sitting plan or timetable data is missing. Please upload them via the Admin Panel to search.")
            else:
                results = get_sitting_details(roll, date_input.strftime('%d-%m-%Y'), sitting_plan, timetable)
                if results:
                    st.success(f"Found {len(results)} exam(s) for Roll Number {roll} on {date_input.strftime('%d-%m-%Y')}:")
                    for i, result in enumerate(results):
                        st.markdown(f"---")
                        st.subheader(f"Exam {i+1}")
                        st.write(f"**Room Number:** {result['Room Number']}")
                        st.write(f"**🪑 Seat Number:** {result['Seat Number']}")
                        st.write(f"**📚 Paper:** {result['Paper']} - {result['Paper Name']} - ({result['Paper Code']})")
                        st.write(f"**🏫 Class:** {result['Class']}")
                        st.write(f"**🎓 Student type:** {result['Mode']} - {result['Type']}")
                        st.write(f"**🕐 Shift:** {result['Shift']}, **📅 Date:** {result['Date']}")
                else:
                    st.warning("No data found for the given inputs.")

    elif option == "Get Full Exam Schedule by Roll Number":
        roll = st.text_input("Enter Roll Number")
        if st.button("Get Schedule"):
            if sitting_plan.empty or timetable.empty:
                st.warning("Sitting plan or timetable data is missing. Please upload them via the Admin Panel to get schedule.")
            else:
                schedule = pd.DataFrame(get_all_exams(roll, sitting_plan, timetable))
                if not schedule.empty:
                    schedule['Date_dt'] = pd.to_datetime(schedule['Date'], format='%d-%m-%Y', errors='coerce')
                    schedule = schedule.sort_values(by="Date_dt").drop(columns=['Date_dt'])
                    st.write(schedule)
                else:
                    st.warning("No exam records found for this roll number.")

    elif option == "View Full Timetable":
        st.subheader("Full Examination Timetable")
        if timetable.empty:
            st.warning("Timetable data is missing. Please upload it via the Admin Panel.")
        else:
            st.dataframe(timetable)

elif menu == "Admin Panel":
    st.subheader("🔐 Admin Login")
    if admin_login():
        st.success("Login successful!")
        
        sitting_plan, timetable, assigned_seats_df = load_data_supabase()
        exam_team_members = load_exam_team_members_supabase()
        shift_assignments_df = load_shift_assignments_supabase()

        st.markdown("---")
        st.subheader("Current Data Previews")
        col_sp, col_tt, col_assigned = st.columns(3)
        with col_sp:
            st.write("**Sitting Plan**")
            if not sitting_plan.empty:
                st.dataframe(sitting_plan)
            else:
                st.info("No sitting plan data loaded.")
        with col_tt:
            st.write("**Timetable**")
            if not timetable.empty:
                st.dataframe(timetable)
            else:
                st.info("No timetable data loaded.")
        with col_assigned:
            st.write("**Assigned Seats**")
            if not assigned_seats_df.empty:
                st.dataframe(assigned_seats_df)
            else:
                st.info("No assigned seats data loaded.")
        
        st.markdown("---")
        
        admin_option = st.radio("Select Admin Task:", [
            "Upload Data from ZIP Files",
            "Update Exam Team Members",
            "Assign Rooms & Seats to Students",
            "Generate & Assign Shifts",
            "Delete All Data" 
        ])

        if admin_option == "Upload Data from ZIP Files":
            st.subheader("Upload Data from PDF ZIP Files")
            uploaded_zip_sitting_plan = st.file_uploader("Upload Sitting Plan ZIP (.zip)", type="zip", key="sitting_plan_zip")
            if uploaded_zip_sitting_plan:
                success, message = process_zip_and_upload_to_supabase(uploaded_zip_sitting_plan, "sitting_plan", "sitting_plan")
                if success:
                    st.success(message)
                else:
                    st.error(message)

            uploaded_zip_timetable = st.file_uploader("Upload Timetable ZIP (.zip)", type="zip", key="timetable_zip")
            if uploaded_zip_timetable:
                success, message = process_zip_and_upload_to_supabase(uploaded_zip_timetable, "timetable", "timetable")
                if success:
                    st.success(message)
                else:
                    st.error(message)
        
        elif admin_option == "Update Exam Team Members":
            st.subheader("Update Exam Team Members")
            st.info("Enter one name per line.")
            members_text = st.text_area("Exam Team Members", value="\n".join(exam_team_members), height=200)
            if st.button("Save Team Members"):
                new_members = [m.strip() for m in members_text.split('\n') if m.strip()]
                success, message = save_exam_team_members_supabase(new_members)
                if success:
                    st.success(message)
                    exam_team_members = new_members # Update local variable
                else:
                    st.error(message)

        elif admin_option == "Assign Rooms & Seats to Students":
            st.subheader("Assign Rooms & Seats to Students")
            st.warning("This feature is under development and will save data to Supabase.")
            st.info("For now, it displays a mock output. The logic for saving to Supabase needs to be implemented here.")
            
            if st.button("Mock Assign Seats & Save to Supabase"):
                mock_assigned_seats = [
                    {"Roll Number": "1001", "Paper Code": "01", "Paper Name": "Paper A", "Room Number": "101", "Seat Number": "1", "Date": "2025-08-01", "Shift": "Morning"},
                    {"Roll Number": "1002", "Paper Code": "01", "Paper Name": "Paper A", "Room Number": "101", "Seat Number": "2", "Date": "2025-08-01", "Shift": "Morning"},
                ]
                
                success, message = save_data_to_supabase("assigned_seats", mock_assigned_seats)
                if success:
                    st.success("Mock assigned seats saved to Supabase successfully!")
                else:
                    st.error(f"Error saving mock data: {message}")

        elif admin_option == "Generate & Assign Shifts":
            st.subheader("Generate & Assign Invigilator Shifts")
            st.info("This feature is under development and will save data to Supabase.")
            st.warning("For now, it shows mock assignments. The full assignment logic needs to be implemented here.")

            if st.button("Generate & Save Mock Shift Assignments"):
                mock_assignments = {
                    'date': '2025-08-01',
                    'shift': 'Morning',
                    'senior_center_superintendent': ['John Doe'],
                    'center_superintendent': ['Jane Smith'],
                    'assistant_center_superintendent': ['Mike Johnson'],
                    'permanent_invigilator': ['Emily White', 'Chris Brown'],
                    'assistant_permanent_invigilator': ['Sarah Davis'],
                    'class_3_worker': ['Worker A'],
                    'class_4_worker': ['Worker B']
                }
                success, message = save_shift_assignment_supabase(mock_assignments['date'], mock_assignments['shift'], mock_assignments)
                if success:
                    st.success(message)
                else:
                    st.error(message)

        elif admin_option == "Delete All Data":
            st.subheader("Delete All Supabase Data")
            st.error("This will permanently delete all data from your Supabase tables. This action cannot be undone.")
            if st.button("Confirm and Delete All Data"):
                try:
                    tables_to_delete = ["sitting_plan", "timetable", "assigned_seats", "exam_team_members", "shift_assignments", "cs_reports", "attestation_data"]
                    for table in tables_to_delete:
                        response = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?id=not.is.null", headers=headers)
                        response.raise_for_status()
                        st.success(f"Successfully deleted all data from table '{table}'.")
                    st.success("All data successfully deleted.")
                except Exception as e:
                    st.error(f"Error during data deletion: {e}")

elif menu == "Centre Superintendent Panel":
    st.subheader("🔐 Centre Superintendent Login")
    if cs_login():
        st.success("Login successful!")
        
        sitting_plan, timetable, assigned_seats_df = load_data_supabase()
        cs_reports_df = load_cs_reports_supabase()
        shift_assignments_df = load_shift_assignments_supabase()

        cs_option = st.radio("Select CS Task:", [
            "Daily Attendance Report",
            "Generate Room-wise Report (PDF)",
            "Generate Room Chart (CSV)"
        ])

        if cs_option == "Daily Attendance Report":
            st.subheader("Daily Attendance Report")
            if not assigned_seats_df.empty and not timetable.empty and not cs_reports_df.empty:
                unique_dates = sorted(assigned_seats_df['Date'].astype(str).str.strip().unique())
                unique_shifts = sorted(assigned_seats_df['Shift'].astype(str).str.strip().unique())
                
                if unique_dates and unique_shifts:
                    selected_date = st.selectbox("Select Date", options=unique_dates)
                    selected_shift = st.selectbox("Select Shift", options=unique_shifts)
                    
                    if st.button("View Daily Report"):
                        st.write(f"### Report for {selected_date} ({selected_shift})")
                        report_data = cs_reports_df[
                            (cs_reports_df['date'] == selected_date) &
                            (cs_reports_df['shift'] == selected_shift)
                        ]
                        if not report_data.empty:
                            st.dataframe(report_data)
                        else:
                            st.warning("No reports submitted for this date and shift.")
            else:
                st.warning("Required data (assigned seats, timetable, or CS reports) is missing. Please ensure data is uploaded and reports are submitted.")

        elif cs_option == "Generate Room-wise Report (PDF)":
            st.subheader("Generate Room-wise Report (PDF)")
            if not assigned_seats_df.empty and not timetable.empty:
                unique_dates = sorted(assigned_seats_df['Date'].astype(str).str.strip().unique())
                unique_shifts = sorted(assigned_seats_df['Shift'].astype(str).str.strip().unique())

                if unique_dates and unique_shifts:
                    selected_date = st.selectbox("Select Date", options=unique_dates, key="pdf_date")
                    selected_shift = st.selectbox("Select Shift", options=unique_shifts, key="pdf_shift")
                    unique_rooms = sorted(assigned_seats_df[
                        (assigned_seats_df['Date'] == selected_date) &
                        (assigned_seats_df['Shift'] == selected_shift)
                    ]['Room Number'].astype(str).str.strip().unique())
                    
                    selected_room = st.selectbox("Select Room Number", options=unique_rooms)

                    if st.button("Generate Room Report PDF"):
                        students_in_room_df = get_students_in_room(selected_room, selected_date, selected_shift, assigned_seats_df)
                        if not students_in_room_df.empty:
                            report_text = f"""
                            जीवाजी विश्वविद्यालय ग्वालियर
                            परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107
                            Room Report
                            Date: {selected_date}, Shift: {selected_shift}
                            Room Number: {selected_room}
                            
                            Roll Number | Paper Code | Seat Number | Paper Name
                            -----------------------------------------------------------------------------------------------------------------
                            """
                            for _, row in students_in_room_df.iterrows():
                                report_text += f"\n{row['Roll Number']} | {row['Paper Code']} | {row['Seat Number']} | {row['Paper Name']}"

                            pdf_output = _generate_sitting_plan_report_pdf(report_text)
                            st.download_button(
                                label="Download Room Report as PDF",
                                data=pdf_output,
                                file_name=f"room_report_{selected_date}_{selected_shift}_room_{selected_room}.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.warning("No students found for this room, date, and shift.")
                else:
                    st.info("No assigned seat data available. Please run 'Assign Rooms & Seats to Students' first.")
            else:
                st.warning("Assigned seats or timetable data is missing. Please upload them first.")

        elif cs_option == "Generate Room Chart (CSV)":
            st.subheader("Generate Room Chart (CSV)")
            if not assigned_seats_df.empty and not timetable.empty and not cs_reports_df.empty:
                unique_dates = sorted(assigned_seats_df['Date'].astype(str).str.strip().unique())
                unique_shifts = sorted(assigned_seats_df['Shift'].astype(str).str.strip().unique())
                
                if unique_dates and unique_shifts:
                    selected_date = st.selectbox("Select Date", options=unique_dates, key="chart_date")
                    selected_shift = st.selectbox("Select Shift", options=unique_shifts, key="chart_shift")

                    if st.button("Generate Room Chart CSV"):
                        room_chart_df = pd.DataFrame()
                        
                        st.warning("This feature is not yet implemented fully. It shows a mock output.")
                        st.dataframe(room_chart_df)

                        if not room_chart_df.empty:
                            room_chart_output = room_chart_df.to_csv(index=False)
                            file_name = f"room_chart_{selected_date}_{selected_shift}.csv"
                            st.download_button(
                                label="Download Room Chart as CSV",
                                data=room_chart_output.encode('utf-8'),
                                file_name=file_name,
                                mime="text/csv",
                            )
                        else:
                            st.warning("Could not generate room chart. Please ensure data is complete and assignments are made.")
                else:
                    st.warning("No assigned seats, timetable or CS report data available.")
            else:
                st.warning("Required data (assigned seats, timetable, or CS reports) is missing. Please ensure data is uploaded.")

