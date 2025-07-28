import streamlit as st
import pandas as pd
import datetime
import os
import io
import zipfile # For handling zip files
import tempfile # For creating temporary directories
import fitz  # PyMuPDF for PDF processing
import re # For regex in PDF processing
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font
import json
import ast # Added for literal_eval to convert string representations of lists back to lists

# --- Configuration ---
CS_REPORTS_FILE = "cs_reports.csv"
EXAM_TEAM_MEMBERS_FILE = "exam_team_members.csv"
SHIFT_ASSIGNMENTS_FILE = "shift_assignments.csv"
ROOM_INVIGILATORS_FILE = "room_invigilator_assignments.csv" # New file for room-wise invigilators
SITTING_PLAN_FILE = "sitting_plan.csv" # Standardized sitting plan filename
TIMETABLE_FILE = "timetable.csv" # Standardized timetable filename
ASSIGNED_SEATS_FILE = "assigned_seats.csv" # New file for assigned seats
ATTESTATION_DATA_FILE = "attestation_data_combined.csv" # For rasa_pdf output
COLLEGE_STATISTICS_FILE = "college_statistics_fancy.csv" # For college_statistic output

def load_shift_assignments():
    if os.path.exists(SHIFT_ASSIGNMENTS_FILE):
        try:
            df = pd.read_csv(SHIFT_ASSIGNMENTS_FILE)
            # Convert string representations of lists back to actual lists for roles
            for role in ["senior_center_superintendent", "center_superintendent", "assistant_center_superintendent", 
                         "permanent_invigilator", "assistant_permanent_invigilator", 
                         "class_3_worker", "class_4_worker"]: # Added new roles
                if role in df.columns:
                    # Ensure that empty strings or NaN values are handled gracefully
                    df[role] = df[role].apply(lambda x: ast.literal_eval(x) if pd.notna(x) and x.strip() else [])
            return df
        except Exception as e:
            st.error(f"Error loading shift assignments: {e}. Reinitializing shift assignments file.")
            # If an error occurs during loading, reinitialize the DataFrame with correct columns
            return pd.DataFrame(columns=['date', 'shift', 'senior_center_superintendent', 'center_superintendent', 
                                         'assistant_center_superintendent', 'permanent_invigilator', 
                                         'assistant_permanent_invigilator', 'class_3_worker', 'class_4_worker']) # Added new columns here
    # If file does not exist, create a new DataFrame with all columns
    return pd.DataFrame(columns=['date', 'shift', 'senior_center_superintendent', 'center_superintendent', 
                                 'assistant_center_superintendent', 'permanent_invigilator', 
                                 'assistant_permanent_invigilator', 'class_3_worker', 'class_4_worker']) # Added new columns here

def save_shift_assignment(date, shift, assignments):
    assignments_df = load_shift_assignments()
    
    # Create a unique key for the assignment
    assignment_key = f"{date}_{shift}"

    # Prepare data for DataFrame, converting lists to string representations
    data_for_df = {
        'date': date,
        'shift': shift,
        'senior_center_superintendent': str(assignments.get('senior_center_superintendent', [])),
        'center_superintendent': str(assignments.get('center_superintendent', [])), 
        'assistant_center_superintendent': str(assignments.get('assistant_center_superintendent', [])),
        'permanent_invigilator': str(assignments.get('permanent_invigilator', [])),
        'assistant_permanent_invigilator': str(assignments.get('assistant_permanent_invigilator', [])),
        'class_3_worker': str(assignments.get('class_3_worker', [])), # Added new role
        'class_4_worker': str(assignments.get('class_4_worker', []))  # Added new role
    }
    new_row_df = pd.DataFrame([data_for_df])

    # Check if assignment_key already exists
    if assignment_key in (assignments_df['date'] + '_' + assignments_df['shift']).values:
        # Update existing record
        idx_to_update = assignments_df[(assignments_df['date'] == date) & (assignments_df['shift'] == shift)].index[0]
        for col, val in data_for_df.items():
            assignments_df.loc[idx_to_update, col] = val
    else:
        # Add new record
        assignments_df = pd.concat([assignments_df, new_row_df], ignore_index=True)
    
    try:
        assignments_df.to_csv(SHIFT_ASSIGNMENTS_FILE, index=False)
        return True, "Shift assignments saved successfully!"
    except Exception as e:
        return False, f"Error saving shift assignments: {e}"



# --- Rest of your exam_app_bot.py code follows below ---
# For example, your Streamlit app layout, other functions, and calls to load_shift_assignments()
# should come after the definitions of load_shift_assignments and save_shift_assignment.

# --- Firebase related code removed as per user request ---
# Initialize session state for Centre Superintendent reports if not already present
if 'cs_reports' not in st.session_state:
    st.session_state.cs_reports = {}

# Load data from CSV files (sitting_plan.csv, timetable.csv, assigned_seats.csv)
def load_data():
    # Check if files exist before attempting to read them
    sitting_plan_df = pd.DataFrame()
    timetable_df = pd.DataFrame()
    assigned_seats_df = pd.DataFrame() # Initialize assigned_seats_df

    if os.path.exists(SITTING_PLAN_FILE):
        try:
            sitting_plan_df = pd.read_csv(SITTING_PLAN_FILE, dtype={
                f"Roll Number {i}": str for i in range(1, 11)
            })
            sitting_plan_df.columns = sitting_plan_df.columns.str.strip()
        except Exception as e:
            st.error(f"Error loading {SITTING_PLAN_FILE}: {e}")
            sitting_plan_df = pd.DataFrame()

    if os.path.exists(TIMETABLE_FILE):
        try:
            timetable_df = pd.read_csv(TIMETABLE_FILE)
            timetable_df.columns = timetable_df.columns.str.strip()
        except Exception as e:
            st.error(f"Error loading {TIMETABLE_FILE}: {e}")
            timetable_df = pd.DataFrame()
    
    if os.path.exists(ASSIGNED_SEATS_FILE):
        try:
            # Ensure Room Number and Roll Number are read as string to prevent type mismatch issues
            assigned_seats_df = pd.read_csv(ASSIGNED_SEATS_FILE, dtype={"Roll Number": str, "Room Number": str})
        except Exception as e:
            st.error(f"Error loading {ASSIGNED_SEATS_FILE}: {e}")
            assigned_seats_df = pd.DataFrame(columns=["Roll Number", "Paper Code", "Paper Name", "Room Number", "Seat Number", "Date", "Shift"])
    else:
        assigned_seats_df = pd.DataFrame(columns=["Roll Number", "Paper Code", "Paper Name", "Room Number", "Seat Number", "Date", "Shift"])
        # st.info(f"Note: `{ASSIGNED_SEATS_FILE}` not found. A new empty file will be created upon first assignment.") # Removed for cleaner UI

            
    return sitting_plan_df, timetable_df, assigned_seats_df

# Save uploaded files (for admin panel)
def save_uploaded_file(uploaded_file_content, filename):
    try:
        if isinstance(uploaded_file_content, pd.DataFrame):
            # If it's a DataFrame, convert to CSV bytes
            csv_bytes = uploaded_file_content.to_csv(index=False).encode('utf-8')
        else:
            # Assume it's bytes from st.file_uploader
            # Ensure uploaded_file_content is a BytesIO object or similar with .getbuffer()
            if hasattr(uploaded_file_content, 'getbuffer'):
                csv_bytes = uploaded_file_content.getbuffer()
            else:
                # Fallback for other file-like objects, or if it's already bytes
                csv_bytes = uploaded_file_content.read()


        with open(filename, "wb") as f:
            f.write(csv_bytes)
        return True, f"File {filename} saved successfully!" # Modified: Return a tuple here
    except Exception as e:
        return False, f"Error saving file {filename}: {e}"

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

# --- CSV Helper Functions for CS Reports ---
def load_cs_reports_csv():
    if os.path.exists(CS_REPORTS_FILE):
        try:
            df = pd.read_csv(CS_REPORTS_FILE)
            # Ensure 'class' column exists, add if missing with empty string as default
            if 'class' not in df.columns:
                df['class'] = ""
            
            # Convert string representations of lists back to actual lists
            for col in ['absent_roll_numbers', 'ufm_roll_numbers']:
                if col in df.columns:
                    # Convert to string, then handle 'nan' and empty strings before literal_eval
                    df[col] = df[col].astype(str).apply(
                        lambda x: ast.literal_eval(x) if x.strip() and x.strip().lower() != 'nan' else []
                    )
            return df
        except Exception as e:
            st.error(f"Error loading CS reports from CSV: {e}")
            return pd.DataFrame(columns=['report_key', 'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'class', 'absent_roll_numbers', 'ufm_roll_numbers'])
    else:
        return pd.DataFrame(columns=['report_key', 'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'class', 'absent_roll_numbers', 'ufm_roll_numbers'])

def save_cs_report_csv(report_key, data):
    reports_df = load_cs_reports_csv()
    
    # Convert lists to string representation for CSV storage
    data_for_df = data.copy()
    data_for_df['absent_roll_numbers'] = str(data_for_df.get('absent_roll_numbers', []))
    data_for_df['ufm_roll_numbers'] = str(data_for_df.get('ufm_roll_numbers', []))

    # Convert the single data dictionary to a DataFrame row
    new_row_df = pd.DataFrame([data_for_df])

    # Check if report_key already exists in the DataFrame
    if report_key in reports_df['report_key'].values:
        # Update existing record
        idx_to_update = reports_df[reports_df['report_key'] == report_key].index[0]
        # Update values in that row using .loc
        for col, val in data_for_df.items():
            reports_df.loc[idx_to_update, col] = val
    else:
        # Add new record
        reports_df = pd.concat([reports_df, new_row_df], ignore_index=True)

    try:
        reports_df.to_csv(CS_REPORTS_FILE, index=False)
        return True, "Report saved to CSV successfully!"
    except Exception as e:
        return False, f"Error saving report to CSV: {e}"

def load_single_cs_report_csv(report_key):
    reports_df = load_cs_reports_csv()
    filtered_df = reports_df[reports_df['report_key'] == report_key]
    if not filtered_df.empty:
        return True, filtered_df.iloc[0].to_dict()
    else:
        return False, {}

# --- Exam Team Members Functions ---
def load_exam_team_members():
    if os.path.exists(EXAM_TEAM_MEMBERS_FILE):
        try:
            df = pd.read_csv(EXAM_TEAM_MEMBERS_FILE)
            return df['name'].tolist()
        except Exception as e:
            st.error(f"Error loading exam team members: {e}")
            return []
    return []

def save_exam_team_members(members):
    df = pd.DataFrame({'name': sorted(list(set(members)))}) # Remove duplicates and sort
    try:
        df.to_csv(EXAM_TEAM_MEMBERS_FILE, index=False)
        return True, "Exam team members saved successfully!"
    except Exception as e:
        return False, f"Error saving exam team members: {e}"

def get_all_students_for_date_shift_formatted(date_str, shift, sitting_plan, timetable):
    all_students_data = []

    # Filter timetable for the given date and shift
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if current_day_exams_tt.empty:
        return None, "No exams found for the selected date and shift.", None

    # Extract time from the timetable. Assuming all exams in a given shift have the same time.
    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"

    # Determine the class summary for the header
    unique_classes = current_day_exams_tt['Class'].dropna().astype(str).str.strip().unique()
    class_summary_header = ""
    if len(unique_classes) == 1:
        class_summary_header = f"{unique_classes[0]} Examination {datetime.datetime.now().year}"
    elif len(unique_classes) > 1:
        class_summary_header = f"Various Classes Examination {datetime.datetime.now().year}"
    else:
        class_summary_header = f"Examination {datetime.datetime.now().year}"

    # Iterate through each exam scheduled for the date/shift
    for _, tt_row in current_day_exams_tt.iterrows():
        tt_class = str(tt_row["Class"]).strip()
        tt_paper = str(tt_row["Paper"]).strip()
        tt_paper_code = str(tt_row["Paper Code"]).strip()
        tt_paper_name = str(tt_row["Paper Name"]).strip()

        # Find students in sitting plan for this specific exam
        matching_students_sp = sitting_plan[
            (sitting_plan["Class"].astype(str).str.strip().str.lower() == tt_class.lower()) &
            (sitting_plan["Paper"].astype(str).str.strip() == tt_paper) &
            (sitting_plan["Paper Code"].astype(str).str.strip() == tt_paper_code) &
            (sitting_plan["Paper Name"].astype(str).str.strip() == tt_paper_name)
        ]

        for _, sp_row in matching_students_sp.iterrows():
            room_num = str(sp_row["Room Number"]).strip()

            for i in range(1, 11): # Iterate through Roll Number 1 to 10
                roll_col = f"Roll Number {i}"
                s_col = f"Seat Number {i}" # Define s_col here

                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num_display = ""
                seat_num_sort_key = None # For sorting

                if roll_num and roll_num != 'nan':
                    if s_col in sp_row.index: # Check if column exists
                        seat_num_raw = str(sp_row[s_col]).strip()
                        try:
                            seat_num_sort_key = int(float(seat_num_raw)) # Convert to float first to handle .0, then int
                            seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                        except ValueError:
                            seat_num_sort_key = float('inf') # Assign a large number to sort at the end
                            seat_num_display = seat_num_raw if seat_num_raw else "N/A" # Display raw or N/A
                    else:
                        seat_num_sort_key = float('inf')
                        seat_num_display = "N/A" # Column itself is missing

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

    if not all_students_data:
        return None, "No students found for the selected date and shift.", None

    # Sort the collected data by Room Number, then Seat Number
    all_students_data.sort(key=lambda x: (x['room_num'], x['seat_num_sort_key']))

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
        output_string_parts.append(f" कक्ष :-{room_num}") # Added space for consistency
        current_room_students = students_by_room[room_num]

        num_cols = 10

        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]

            # Create a single line for 10 students
            single_line_students = []
            for student in block_students:
                # Modified formatting here: removed space after '(' and added '-' before paper_name
                single_line_students.append(
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']})-{student['paper_name']}"
                )

            output_string_parts.append("".join(single_line_students)) # Join directly without spaces

    final_text_output = "\n".join(output_string_parts)

    # --- Prepare Excel output data ---
    excel_output_data = []

    # Excel Header
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107"])
    excel_output_data.append([class_summary_header])
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["दिनांक :-", date_str])
    excel_output_data.append(["पाली :-", shift])
    excel_output_data.append(["समय :-", exam_time])
    excel_output_data.append([]) # Blank line

    # Excel Student Data Section (now each block of 10 students is one row, each student is one cell)
    for room_num in sorted(students_by_room.keys()):
        excel_output_data.append([f" कक्ष :-{room_num}"]) # Added space for consistency
        current_room_students = students_by_room[room_num]

        num_cols = 10

        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]

            excel_row_for_students = [""] * num_cols # Prepare 10 cells for this row

            for k, student in enumerate(block_students):
                # Each cell contains the full student string, modified formatting
                excel_row_for_students[k] = (
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']})-{student['paper_name']}"
                )

            excel_output_data.append(excel_row_for_students)
            excel_output_data.append([""] * num_cols) # Blank row for spacing

    return final_text_output, None, excel_output_data	
# --- Room Invigilator Assignment Functions (NEW) ---
def load_room_invigilator_assignments():
    if os.path.exists(ROOM_INVIGILATORS_FILE):
        try:
            df = pd.read_csv(ROOM_INVIGILATORS_FILE)
            if 'invigilators' in df.columns:
                df['invigilators'] = df['invigilators'].astype(str).apply(
                    lambda x: ast.literal_eval(x) if x.strip() and x.strip().lower() != 'nan' else []
                )
            return df
        except Exception as e:
            st.error(f"Error loading room invigilator assignments: {e}")
            return pd.DataFrame(columns=['date', 'shift', 'room_num', 'invigilators'])
    return pd.DataFrame(columns=['date', 'shift', 'room_num', 'invigilators'])

def save_room_invigilator_assignment(date, shift, room_num, invigilators):
    inv_df = load_room_invigilator_assignments()
    
    # Create a unique key for the assignment
    assignment_key = f"{date}_{shift}_{room_num}"

    # Prepare data for DataFrame, converting list to string representation
    data_for_df = {
        'date': date,
        'shift': shift,
        'room_num': room_num,
        'invigilators': str(invigilators)
    }
    new_row_df = pd.DataFrame([data_for_df])

    # Check if assignment_key already exists
    if assignment_key in (inv_df['date'] + '_' + inv_df['shift'] + '_' + inv_df['room_num']).values:
        # Update existing record
        idx_to_update = inv_df[
            (inv_df['date'] == date) & 
            (inv_df['shift'] == shift) & 
            (inv_df['room_num'] == room_num)
        ].index[0]
        for col, val in data_for_df.items():
            inv_df.loc[idx_to_update, col] = val
    else:
        # Add new record
        inv_df = pd.concat([inv_df, new_row_df], ignore_index=True)
    
    try:
        inv_df.to_csv(ROOM_INVIGILATORS_FILE, index=False)
        return True, "Room invigilator assignments saved successfully!"
    except Exception as e:
        return False, f"Error saving room invigilator assignments: {e}"


# Get all exams for a roll number (Student View)
def get_all_exams(roll_number, sitting_plan, timetable):
    student_exams = []
    roll_number_str = str(roll_number).strip() # Ensure consistent string comparison

    # Iterate through each row of the sitting plan
    for _, sp_row in sitting_plan.iterrows():
        # Check all possible roll number columns in the current sitting plan row
        for i in range(1, 11):
            r_col = f"Roll Number {i}"
            if r_col in sp_row and str(sp_row[r_col]).strip() == roll_number_str:
                # If roll number matches, extract paper and class details from this sitting plan row
                paper = str(sp_row["Paper"]).strip()
                paper_code = str(sp_row["Paper Code"]).strip()
                paper_name = str(sp_row["Paper Name"]).strip()
                _class = str(sp_row["Class"]).strip()

                # Find all matching entries in the timetable for this paper and class
                matches_in_timetable = timetable[
                    (timetable["Paper"].astype(str).str.strip() == paper) &
                    (timetable["Paper Code"].astype(str).str.strip() == paper_code) &
                    (timetable["Paper Name"].astype(str).str.strip() == paper_name) &
                    (timetable["Class"].astype(str).str.strip().str.lower() == _class.lower())
                ]

                # Add all found timetable matches for this student's paper to the list
                for _, tt_row in matches_in_timetable.iterrows():
                    student_exams.append({
                        "Date": tt_row["Date"],
                        "Shift": tt_row["Shift"],
                        "Class": _class,
                        "Paper": paper,
                        "Paper Code": paper_code,
                        "Paper Name": paper_name
                    })
                # Break from inner loop once the roll number is found in a row to avoid duplicate processing for the same row
                # if the roll number appears in multiple 'Roll Number X' columns within the *same* row (unlikely but safe)
                break
    return student_exams

# Get sitting details for a specific roll number and date (Student View)
def get_sitting_details(roll_number, date, sitting_plan, timetable):
    found_sittings = []
    roll_number_str = str(roll_number).strip()
    date_str = str(date).strip() # Ensure date is in 'DD-MM-YYYY' string format

    for _, sp_row in sitting_plan.iterrows():
        for i in range(1, 11):
            r_col = f"Roll Number {i}"
            s_col = f"Seat Number {i}" # Corresponding seat number column

            # Check if the roll number exists in any of the roll number columns in this sitting plan row
            if r_col in sp_row and str(sp_row[r_col]).strip() == roll_number_str:
                # If roll number matches, extract paper and class details from this sitting plan row
                paper = str(sp_row["Paper"]).strip()
                paper_code = str(sp_row["Paper Code"]).strip()
                paper_name = str(sp_row["Paper Name"]).strip()
                _class = str(sp_row["Class"]).strip()

                # Find if this paper's date matches the search in the timetable
                matches_in_timetable = timetable[
                    (timetable["Class"].astype(str).str.strip().str.lower() == _class.lower()) &
                    (timetable["Paper"].astype(str).str.strip() == paper) &
                    (timetable["Paper Code"].astype(str).str.strip() == paper_code) &
                    (timetable["Paper Name"].astype(str).str.strip() == paper_name) &
                    (timetable["Date"].astype(str).str.strip() == date_str) # Match against the provided date
                ]

                if not matches_in_timetable.empty:
                    # If there are multiple timetable entries for the same paper/class/date (e.g., different shifts),
                    # add all of them as separate sitting details.
                    for _, tt_row in matches_in_timetable.iterrows():
                        # Safely get seat number for display and sorting
                        seat_num_display = ""
                        seat_num_sort_key = float('inf') # Default sort key for non-numeric

                        if s_col in sp_row.index: # Check if column exists
                            seat_num_raw = str(sp_row[s_col]).strip()
                            try:
                                seat_num_sort_key = int(float(seat_num_raw)) # Convert to float first to handle .0, then int
                                seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                            except ValueError:
                                seat_num_display = seat_num_raw if seat_num_raw else "N/A"
                        else:
                            seat_num_display = "N/A" # Column itself is missing

                        found_sittings.append({
                            "Room Number": sp_row["Room Number"],
                            "Seat Number": seat_num_display, # Use display value
                            "Class": _class,
                            "Paper": paper,
                            "Paper Code": paper_code,
                            "Paper Name": paper_name,
                            "Date": tt_row["Date"],
                            "Shift": tt_row["Shift"],
                            "Mode": sp_row.get("Mode", ""), # Use .get() for safe access
                            "Type": sp_row.get("Type", "") # Use .get() for safe access
                        })
    return found_sittings

# Function to get all students for a given date and shift in the requested text format (Admin Panel)
# This function will now also return data suitable for Excel download
def get_all_students_for_date_shift_formatted(date_str, shift, sitting_plan, timetable):
    all_students_data = []

    # Filter timetable for the given date and shift
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if current_day_exams_tt.empty:
        return None, "No exams found for the selected date and shift.", None

    # Extract time from the timetable. Assuming all exams in a given shift have the same time.
    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"

    # Determine the class summary for the header
    unique_classes = current_day_exams_tt['Class'].dropna().astype(str).str.strip().unique()
    class_summary_header = ""
    if len(unique_classes) == 1:
        class_summary_header = f"{unique_classes[0]} Examination {datetime.datetime.now().year}"
    elif len(unique_classes) > 1:
        class_summary_header = f"Various Classes Examination {datetime.datetime.now().year}"
    else:
        class_summary_header = f"Examination {datetime.datetime.now().year}"

    # Iterate through each exam scheduled for the date/shift
    for _, tt_row in current_day_exams_tt.iterrows():
        tt_class = str(tt_row["Class"]).strip()
        tt_paper = str(tt_row["Paper"]).strip()
        tt_paper_code = str(tt_row["Paper Code"]).strip()
        tt_paper_name = str(tt_row["Paper Name"]).strip()

        # Find students in sitting plan for this specific exam
        matching_students_sp = sitting_plan[
            (sitting_plan["Class"].astype(str).str.strip().str.lower() == tt_class.lower()) &
            (sitting_plan["Paper"].astype(str).str.strip() == tt_paper) &
            (sitting_plan["Paper Code"].astype(str).str.strip() == tt_paper_code) &
            (sitting_plan["Paper Name"].astype(str).str.strip() == tt_paper_name)
        ]

        for _, sp_row in matching_students_sp.iterrows():
            room_num = str(sp_row["Room Number"]).strip()

            for i in range(1, 11): # Iterate through Roll Number 1 to 10
                roll_col = f"Roll Number {i}"
                s_col = f"Seat Number {i}" # Define s_col here

                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num_display = ""
                seat_num_sort_key = None # For sorting

                if roll_num and roll_num != 'nan':
                    if s_col in sp_row.index: # Check if column exists
                        seat_num_raw = str(sp_row[s_col]).strip()
                        try:
                            seat_num_sort_key = int(float(seat_num_raw)) # Convert to float first to handle .0, then int
                            seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                        except ValueError:
                            seat_num_sort_key = float('inf') # Assign a large number to sort at the end
                            seat_num_display = seat_num_raw if seat_num_raw else "N/A" # Display raw or N/A
                    else:
                        seat_num_sort_key = float('inf')
                        seat_num_display = "N/A" # Column itself is missing

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

    if not all_students_data:
        return None, "No students found for the selected date and shift.", None

    # Sort the collected data by Room Number, then Seat Number
    all_students_data.sort(key=lambda x: (x['room_num'], x['seat_num_sort_key']))

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
        output_string_parts.append(f" कक्ष :-{room_num}") # Added space for consistency
        current_room_students = students_by_room[room_num]

        num_cols = 10

        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]

            # Create a single line for 10 students
            single_line_students = []
            for student in block_students:
                # Modified formatting here: removed space after '(' and added '-' before paper_name
                single_line_students.append(
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']})-{student['paper_name']}"
                )

            output_string_parts.append("".join(single_line_students)) # Join directly without spaces

    final_text_output = "\n".join(output_string_parts)

    # --- Prepare Excel output data ---
    excel_output_data = []

    # Excel Header
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107"])
    excel_output_data.append([class_summary_header])
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["दिनांक :-", date_str])
    excel_output_data.append(["पाली :-", shift])
    excel_output_data.append(["समय :-", exam_time])
    excel_output_data.append([]) # Blank line

    # Excel Student Data Section (now each block of 10 students is one row, each student is one cell)
    for room_num in sorted(students_by_room.keys()):
        excel_output_data.append([f" कक्ष :-{room_num}"]) # Added space for consistency
        current_room_students = students_by_room[room_num]

        num_cols = 10

        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]

            excel_row_for_students = [""] * num_cols # Prepare 10 cells for this row

            for k, student in enumerate(block_students):
                # Each cell contains the full student string, modified formatting
                excel_row_for_students[k] = (
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']})-{student['paper_name']}"
                )

            excel_output_data.append(excel_row_for_students)
            excel_output_data.append([""] * num_cols) # Blank row for spacing

    return final_text_output, None, excel_output_data

# New function to get all students for a given date and shift, sorted by roll number (Admin Panel)
def get_all_students_roll_number_wise_formatted(date_str, shift, sitting_plan, timetable):
    all_students_data = []

    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if current_day_exams_tt.empty:
        return None, "No exams found for the selected date and shift.", None

    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"
    unique_classes = current_day_exams_tt['Class'].dropna().astype(str).str.strip().unique()
    class_summary_header = ""
    if len(unique_classes) == 1:
        class_summary_header = f"{unique_classes[0]} Examination {datetime.datetime.now().year}"
    elif len(unique_classes) > 1:
        class_summary_header = f"Various Classes Examination {datetime.datetime.now().year}"
    else:
        class_summary_header = f"Examination {datetime.datetime.now().year}"

    for _, tt_row in current_day_exams_tt.iterrows():
        tt_class = str(tt_row["Class"]).strip()
        tt_paper = str(tt_row["Paper"]).strip()
        tt_paper_code = str(tt_row["Paper Code"]).strip()
        tt_paper_name = str(tt_row["Paper Name"]).strip()

        matching_students_sp = sitting_plan[
            (sitting_plan["Class"].astype(str).str.strip().str.lower() == tt_class.lower()) &
            (sitting_plan["Paper"].astype(str).str.strip() == tt_paper) &
            (sitting_plan["Paper Code"].astype(str).str.strip() == tt_paper_code) &
            (sitting_plan["Paper Name"].astype(str).str.strip() == tt_paper_name)
        ]

        for _, sp_row in matching_students_sp.iterrows():
            room_num = str(sp_row["Room Number"]).strip()
            
            for i in range(1, 11):
                roll_col = f"Roll Number {i}"
                s_col = f"Seat Number {i}"

                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num_display = ""
                seat_num_sort_key = None

                if roll_num and roll_num != 'nan':
                    if s_col in sp_row.index:
                        seat_num_raw = str(sp_row[s_col]).strip()
                        try:
                            seat_num_sort_key = int(float(seat_num_raw)) # Convert to float first to handle .0, then int
                            seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                        except ValueError:
                            seat_num_sort_key = float('inf')
                            seat_num_display = seat_num_raw if seat_num_raw else "N/A"
                    else:
                        seat_num_sort_key = float('inf')
                        seat_num_display = "N/A"

                    all_students_data.append({
                        "roll_num": roll_num,
                        "room_num": room_num,
                        "seat_num_display": seat_num_display,
                        "seat_num_sort_key": seat_num_sort_key,
                        "paper_name": tt_paper_name,
                        "paper_code": tt_paper_code,
                        "class_name": tt_class,
                        "date": date_str,
                        "shift": shift
                    })
    
    if not all_students_data:
        return None, "No students found for the selected date and shift.", None

    # Sort the collected data by Roll Number (lexicographically as strings)
    all_students_data.sort(key=lambda x: x['roll_num'])

    # --- Prepare text output ---
    output_string_parts = []
    output_string_parts.append("जीवाजी विश्वविद्यालय ग्वालियर")
    output_string_parts.append("परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107")
    output_string_parts.append(class_summary_header)
    output_string_parts.append(f"दिनांक :-{date_str}")
    output_string_parts.append(f"पाली :-{shift}")
    output_string_parts.append(f"समय :-{exam_time}")
    output_string_parts.append("") # Blank line for separation

    num_cols = 10 
    for i in range(0, len(all_students_data), num_cols):
        block_students = all_students_data[i : i + num_cols]
        
        single_line_students = []
        for student in block_students:
            single_line_students.append(
                f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']}){student['paper_name']}"
            )
        output_string_parts.append("".join(single_line_students))

    final_text_output = "\n".join(output_string_parts)

    # --- Prepare Excel output data ---
    excel_output_data = []

    # Excel Header
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107"])
    excel_output_data.append([class_summary_header])
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["दिनांक :-", date_str])
    excel_output_data.append(["पाली :-", shift])
    excel_output_data.append(["समय :-", exam_time])
    excel_output_data.append([]) # Blank line

    # Excel Student Data Section
    for i in range(0, len(all_students_data), num_cols):
        block_students = all_students_data[i : i + num_cols]
        
        excel_row_for_students = [""] * num_cols

        for k, student in enumerate(block_students):
            excel_row_for_students[k] = (
                f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']}){student['paper_name']}"
            )
        
        excel_output_data.append(excel_row_for_students)
        excel_output_data.append([""] * num_cols) # Blank row for spacing

    return final_text_output, None, excel_output_data

# New helper function based on pdftocsv.py's extract_metadata, but using "UNSPECIFIED" defaults
def extract_metadata_from_pdf_text(text):
    # Extract Class Group and Year like "BSC", "2YEAR"
    class_match = re.search(r'([A-Z]+)\s*/?\s*(\d+YEAR)', text)
    class_val = f"{class_match.group(1)} {class_match.group(2)}" if class_match else "UNSPECIFIED_CLASS"

    # Detect mode/type: REGULAR, PRIVATE, SUPP, EXR
    mode_type = "UNSPECIFIED_MODE"
    for keyword in ["REGULAR", "SUPP", "EXR", "PRIVATE"]:
        if keyword in text.upper():
            mode_type = keyword
            break
    
    paper_code = re.search(r'Paper Code[:\s]*([\d]+)', text)
    paper_code_val = paper_code.group(1) if paper_code else "UNSPECIFIED_PAPER_CODE"

    paper_name = re.search(r'Paper Name[:\s]*(.+?)(?:\n|$)', text)
    paper_name_val = paper_name.group(1).strip() if paper_name else "UNSPECIFIED_PAPER_NAME"

    return {
        "class": class_val,
        "mode": mode_type,
        "type": mode_type, # Assuming type is same as mode
        "room_number": "", # Always blank initially as per request
        "seat_numbers": [""] * 10, # Always blank initially as per request
        "paper_code": paper_code_val,
        "paper_name": paper_name_val
    }

# --- Integration of pdftocsv.py logic ---
def process_sitting_plan_pdfs(zip_file_buffer, output_sitting_plan_path, output_timetable_path):
    all_rows = []
    sitting_plan_columns = [f"Roll Number {i+1}" for i in range(10)]
    sitting_plan_columns += ["Class", "Mode", "Type", "Room Number"]
    sitting_plan_columns += [f"Seat Number {i+1}" for i in range(10)]
    sitting_plan_columns += ["Paper", "Paper Code", "Paper Name"]

    def extract_roll_numbers(text):
        return re.findall(r'\b\d{9}\b', text)

    def format_sitting_plan_rows(rolls, paper_folder_name, meta):
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
            row.append(paper_folder_name)  # Use folder name as Paper
            row.append(meta["paper_code"])
            row.append(meta["paper_name"])
            rows.append(row)
        return rows

    unique_exams_for_timetable = [] # To collect data for incomplete timetable

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_file_buffer, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)
        
        base_dir = tmpdir
        # Check if there's a 'pdf_folder' sub-directory inside the extracted content
        # This handles cases where the zip contains 'pdf_folder' directly or files/folders at root
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

                            rolls = extract_roll_numbers(full_text)
                            rows = format_sitting_plan_rows(rolls, paper_folder_name=folder_name, meta=current_meta)
                            all_rows.extend(rows)
                            processed_files_count += 1
                            st.info(f"✔ Processed: {file} ({len(rolls)} roll numbers)")

                            # Collect unique exam details for timetable generation
                            unique_exams_for_timetable.append({
                                'Class': current_meta['class'],
                                'Paper': folder_name, # Use folder name as Paper
                                'Paper Code': current_meta['paper_code'],
                                'Paper Name': current_meta['paper_name']
                            })

                        except Exception as e:
                            st.error(f"❌ Failed to process {file}: {e}")
    
    if all_rows:
        df_sitting_plan = pd.DataFrame(all_rows, columns=sitting_plan_columns)
        df_sitting_plan.to_csv(output_sitting_plan_path, index=False)
        st.success(f"Successfully processed {processed_files_count} PDFs and saved sitting plan to {output_sitting_plan_path}")

        # Generate incomplete timetable based on unique exams found
        if unique_exams_for_timetable:
            df_unique_exams = pd.DataFrame(unique_exams_for_timetable).drop_duplicates().reset_index(drop=True)
            
            timetable_data = []
            for idx, row in df_unique_exams.iterrows():
                timetable_data.append({
                    "SN": idx + 1,
                    "Date": "", # Blank
                    "Shift": "",    # Blank
                    "Time": "", # Blank
                    "Class": row['Class'], # Now guaranteed to be non-blank
                    "Paper": row['Paper'],
                    "Paper Code": row['Paper Code'], # Now guaranteed to be non-blank
                    "Paper Name": row['Paper Name'] # Now guaranteed to be non-blank
                })
            df_timetable = pd.DataFrame(timetable_data)
            df_timetable.to_csv(output_timetable_path, index=False)
            st.success(f"Generated initial timetable based on sitting plan papers and saved to {output_timetable_path}. Please update dates, shifts, and times as needed.")
        else:
            st.warning("No unique exam details found to generate an initial timetable.")

        return True, "PDF processing complete."
    else:
        return False, "No roll numbers extracted from PDFs."

# --- Integration of rasa_pdf.py logic ---
def process_attestation_pdfs(zip_file_buffer, output_csv_path):
    all_data = []

    def parse_pdf_content(text):
        students = re.split(r"\n?RollNo\.\:\s*", text)
        students = [s.strip() for s in students if s.strip()]

        student_records = []

        for s in students:
            lines = s.splitlines()
            lines = [line.strip() for line in lines if line.strip()]

            def extract_after(label):
                for i, line in enumerate(lines):
                    if line.startswith(label):
                        value = line.replace(label, "").strip()
                        if value:
                            return value
                        elif i+1 < len(lines):
                            return lines[i+1].strip()
                    # Special handling for "Regular/Backlog" as it might be on the next line
                    if label == "Regular/ Backlog:" and line.startswith("Regular/Backlog"):
                        value = line.replace("Regular/Backlog", "").strip()
                        if value:
                            return value
                        elif i+1 < len(lines):
                            return lines[i+1].strip()
                    return "" # Return empty string if label not found or value is empty
                return "" # Return empty string if lines is empty

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

            papers = re.findall(r"([^\n]+?\[\\d{5}\][^\n]*)", s)

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
    if not os.path.exists(input_csv_path):
        return False, f"Input file not found: {input_csv_path}. Please process attestation PDFs first."

    try:
        df = pd.read_csv(input_csv_path)

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
        pd.DataFrame(output_rows).to_csv(output_csv_path, index=False, header=False)
        return True, f"Statistics saved in layout format to: {output_csv_path}"

    except Exception as e:
        return False, f"Error generating college statistics: {e}"

# New helper function to generate sequential seat numbers based on a range string (from assign_seats_app.py)
def generate_sequential_seats(seat_range_str, num_students):
    generated_seats = []
    seat_range_str = seat_range_str.strip().upper() # Normalize input

    if '-' in seat_range_str:
        start_seat_str, end_seat_str = seat_range_str.split('-')
        
        # Handle alphanumeric like "1A-60A"
        if re.match(r'^\d+[A-Z]$', start_seat_str) and re.match(r'^\d+[A-Z]$', end_seat_str):
            start_num = int(re.match(r'^(\d+)', start_seat_str).group(1))
            start_char = re.search(r'([A-Z])$', start_seat_str).group(1)
            end_num = int(re.match(r'^(\d+)', end_seat_str).group(1))
            end_char = re.search(r'([A-Z])$', end_seat_str).group(1)

            if start_char != end_char:
                raise ValueError("For alphanumeric seat ranges (e.g., 1A-60A), the alphabet part must be the same.")
            
            for i in range(start_num, end_num + 1):
                generated_seats.append(f"{i}{start_char}")
        # Handle numeric like "1-60"
        elif start_seat_str.isdigit() and end_seat_str.isdigit():
            start_num = int(start_seat_str)
            end_num = int(end_seat_str)
            for i in range(start_num, end_num + 1):
                generated_seats.append(str(i))
        else:
            raise ValueError("Invalid seat number range format. Use '1-60' or '1A-60A'.")
    elif seat_range_str.isdigit() or re.match(r'^\d+[A-Z]$', seat_range_str):
        generated_seats.append(seat_range_str)
    else:
        raise ValueError("Invalid seat number format. Use a single number, '1-60', or '1A-60A'.")

    # Return only as many seats as there are students, or all generated seats if fewer students
    return generated_seats[:num_students]


# NEW FUNCTION: Get unassigned students for a given date and shift
def get_unassigned_students_for_session(date_str, shift, sitting_plan_df, timetable_df):
    unassigned_roll_numbers_details = {} # {roll_num: {class, paper, paper_code, paper_name}}

    # 1. Filter timetable for the given date and shift
    relevant_tt_exams = timetable_df[
        (timetable_df["Date"].astype(str).str.strip() == date_str) &
        (timetable_df["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ].copy()

    if relevant_tt_exams.empty:
        return []

    # Create a unique identifier for exams in timetable for easier matching
    relevant_tt_exams['exam_key'] = relevant_tt_exams['Class'].astype(str).str.strip().str.lower() + "_" + \
                                     relevant_tt_exams['Paper'].astype(str).str.strip() + "_" + \
                                     relevant_tt_exams['Paper Code'].astype(str).str.strip() + "_" + \
                                     relevant_tt_exams['Paper Name'].astype(str).str.strip()

    # Iterate through sitting plan to find students for these exams
    for _, sp_row in sitting_plan_df.iterrows():
        # Create exam_key for this sitting plan row
        sp_exam_key = str(sp_row['Class']).strip().lower() + "_" + \
                      str(sp_row['Paper']).strip() + "_" + \
                      str(sp_row['Paper Code']).strip() + "_" + \
                      str(sp_row['Paper Name']).strip()

        # Check if this sitting plan entry corresponds to a relevant exam session
        if sp_exam_key in relevant_tt_exams['exam_key'].values:
            room_assigned = str(sp_row['Room Number']).strip()
            
            # Check all roll numbers in this sitting plan row
            for i in range(1, 11):
                roll_col = f"Roll Number {i}"
                if roll_col in sp_row and pd.notna(sp_row[roll_col]) and str(sp_row[roll_col]).strip() != '':
                    roll_num = str(sp_row[roll_col]).strip()
                    # If room is blank, this student is unassigned for this paper
                    if not room_assigned: # If room_assigned is an empty string
                        # Store details for display
                        unassigned_roll_numbers_details[roll_num] = {
                            'Class': str(sp_row['Class']).strip(),
                            'Paper': str(sp_row['Paper']).strip(),
                            'Paper Code': str(sp_row['Paper Code']).strip(),
                            'Paper Name': str(sp_row['Paper Name']).strip()
                        }
    
    # Convert to a list of dictionaries for display, sorted by roll number
    sorted_unassigned_list = []
    for roll, details in sorted(unassigned_roll_numbers_details.items()):
        sorted_unassigned_list.append({
            "Roll Number": roll,
            "Class": details['Class'],
            "Paper": details['Paper'],
            "Paper Code": details['Paper Code'],
            "Paper Name": details['Paper Name']
        })
    
    return sorted_unassigned_list

# NEW FUNCTION: Get summary of students by paper for a given session (assigned + unassigned)
def get_session_paper_summary(date_str, shift, sitting_plan_df, assigned_seats_df, timetable_df):
    summary_data = []

    # Filter timetable for the given date and shift
    relevant_tt_exams = timetable_df[
        (timetable_df["Date"].astype(str).str.strip() == date_str) &
        (timetable_df["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ].copy()

    if relevant_tt_exams.empty:
        return pd.DataFrame(columns=['Paper Name', 'Paper Code', 'Total Expected', 'Assigned', 'Unassigned'])

    # Iterate through each unique paper in the relevant timetable exams
    for _, tt_row in relevant_tt_exams.drop_duplicates(subset=['Paper Code', 'Paper Name']).iterrows():
        paper_code = str(tt_row['Paper Code']).strip()
        paper_name = str(tt_row['Paper Name']).strip()
        
        # Get all expected roll numbers for this specific paper (from sitting plan)
        expected_rolls = set()
        paper_sitting_rows = sitting_plan_df[sitting_plan_df['Paper Code'].astype(str).str.strip() == paper_code]
        for _, sp_row in paper_sitting_rows.iterrows():
            for i in range(1, 11):
                roll_col = f"Roll Number {i}"
                if roll_col in sp_row and pd.notna(sp_row[roll_col]) and str(sp_row[roll_col]).strip() != '':
                    expected_rolls.add(str(sp_row[roll_col]).strip())
        
        total_expected_students = len(expected_rolls)

        # Get assigned roll numbers for this specific paper, date, and shift
        assigned_rolls_for_paper = set(
            assigned_seats_df[
                (assigned_seats_df["Paper Code"].astype(str) == paper_code) &
                (assigned_seats_df["Date"] == date_str) &
                (assigned_seats_df["Shift"] == shift)
            ]["Roll Number"].astype(str).tolist()
        )
        num_assigned_students = len(assigned_rolls_for_paper)

        # Calculate unassigned students
        num_unassigned_students = total_expected_students - num_assigned_students

        summary_data.append({
            'Paper Name': paper_name,
            'Paper Code': paper_code,
            'Total Expected': total_expected_students,
            'Assigned': num_assigned_students,
            'Unassigned': num_unassigned_students
        })
    
    return pd.DataFrame(summary_data)

# NEW FUNCTION: Display Room Occupancy Report
def display_room_occupancy_report(sitting_plan_df, assigned_seats_df, timetable_df):
    st.subheader("📊 Room Occupancy Report")
    st.info("View detailed occupancy for each room for a selected date and shift.")

    if sitting_plan_df.empty or timetable_df.empty:
        st.warning("Please upload 'sitting_plan.csv' and 'timetable.csv' via the Admin Panel to generate this report.")
        return

    # Date and Shift filters for the report
    report_date_options = sorted(timetable_df["Date"].dropna().unique())
    report_shift_options = sorted(timetable_df["Shift"].dropna().unique())

    if not report_date_options or not report_shift_options:
        st.info("No exam dates or shifts found in the timetable to generate a report.")
        return

    selected_report_date = st.selectbox("Select Date", report_date_options, key="room_report_date")
    selected_report_shift = st.selectbox("Select Shift", report_shift_options, key="room_report_shift")

    if st.button("Generate Room Occupancy Report"):
        # Filter sitting plan for relevant exams on this date/shift
        relevant_tt_exams = timetable_df[
            (timetable_df["Date"].astype(str).str.strip() == selected_report_date) &
            (timetable_df["Shift"].astype(str).str.strip().str.lower() == selected_report_shift.lower())
        ]

        if relevant_tt_exams.empty:
            st.info("No exams scheduled for the selected date and shift to generate room occupancy.")
            return

        # Get unique combinations of (Class, Paper, Paper Code, Paper Name) for the relevant exams
        unique_exams_in_session = relevant_tt_exams[['Class', 'Paper', 'Paper Code', 'Paper Name']].drop_duplicates()

        room_occupancy_data = []

        # Iterate through each unique room in the sitting plan that has a room number assigned
        all_rooms_in_sitting_plan = sitting_plan_df['Room Number'].dropna().astype(str).str.strip().unique()
        
        for room_num in sorted(all_rooms_in_sitting_plan):
            # Find all sitting plan entries for this room
            room_sitting_plan_entries = sitting_plan_df[sitting_plan_df['Room Number'].astype(str).str.strip() == room_num]
            
            expected_students_in_room = 0
            assigned_students_in_room = 0
            assigned_roll_numbers_list = []

            # Calculate expected students for this room for the selected session
            for _, sp_row in room_sitting_plan_entries.iterrows():
                # Create a temporary key to link sitting plan entries to unique exams in session
                sp_exam_key = str(sp_row['Class']).strip() + "_" + \
                              str(sp_row['Paper']).strip() + "_" + \
                              str(sp_row['Paper Code']).strip() + "_" + \
                              str(sp_row['Paper Name']).strip()
                
                # Check if this sitting plan entry's exam is part of the current session
                is_relevant_exam = False
                for _, ue_row in unique_exams_in_session.iterrows():
                    ue_exam_key = str(ue_row['Class']).strip() + "_" + \
                                  str(ue_row['Paper']).strip() + "_" + \
                                  str(ue_row['Paper Code']).strip() + "_" + \
                                  str(ue_row['Paper Name']).strip()
                    if sp_exam_key == ue_exam_key:
                        is_relevant_exam = True
                        break
                
                if is_relevant_exam:
                    for i in range(1, 11):
                        roll_col = f"Roll Number {i}"
                        if roll_col in sp_row and pd.notna(sp_row[roll_col]) and str(sp_row[roll_col]).strip() != '':
                            expected_students_in_room += 1
            
            # Get assigned students for this room for the selected session
            room_assigned_students_df = assigned_seats_df[
                (assigned_seats_df["Room Number"] == room_num) &
                (assigned_seats_df["Date"] == selected_report_date) &
                (assigned_seats_df["Shift"] == selected_report_shift)
            ]
            assigned_students_in_room = len(room_assigned_students_df)
            
            # Collect assigned roll numbers and their seats for display
            if not room_assigned_students_df.empty:
                # Sort by seat number for better readability
                def sort_seat_number_for_display(seat):
                    if isinstance(seat, str):
                        if seat.endswith('A'):
                            return (0, int(seat[:-1]))
                        elif seat.endswith('B'):
                            return (1, int(seat[:-1]))
                        elif seat.isdigit():
                            return (2, int(seat))
                    return (3, seat)
                
                room_assigned_students_df['sort_key'] = room_assigned_students_df['Seat Number'].apply(sort_seat_number_for_display)
                sorted_room_assigned = room_assigned_students_df.sort_values(by='sort_key').drop(columns=['sort_key'])

                for _, assigned_row in sorted_room_assigned.iterrows():
                    assigned_roll_numbers_list.append(
                        f"{assigned_row['Roll Number']} (Seat: {assigned_row['Seat Number']}, Paper: {assigned_row['Paper Code']})"
                    )
            
            remaining_capacity = expected_students_in_room - assigned_students_in_room
            occupancy_percentage = (assigned_students_in_room / expected_students_in_room * 100) if expected_students_in_room > 0 else 0

            room_occupancy_data.append({
                'Room Number': room_num,
                'Total Expected Students': expected_students_in_room,
                'Assigned Students': assigned_students_in_room,
                'Remaining Capacity': remaining_capacity,
                'Occupancy (%)': f"{occupancy_percentage:.2f}%",
                'Assigned Roll Numbers (Details)': ", ".join(assigned_roll_numbers_list) if assigned_roll_numbers_list else "N/A"
            })
        
        if room_occupancy_data:
            df_occupancy = pd.DataFrame(room_occupancy_data)
            st.dataframe(df_occupancy)
            
            # Optional: Download button for this report
            csv_occupancy = df_occupancy.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Room Occupancy Report as CSV",
                data=csv_occupancy,
                file_name=f"room_occupancy_report_{selected_report_date}_{selected_report_shift}.csv",
                mime="text/csv",
            )
        else:
            st.info("No room occupancy data found for the selected date and shift.")

# NEW FUNCTION: Generate Room Chart in specified format
def generate_room_chart_report(date_str, shift, sitting_plan_df, assigned_seats_df, timetable_df):
    output_string_parts = []

    # --- Robust Checks for essential columns ---
    required_timetable_cols = ["Date", "Shift", "Time", "Class", "Paper Code", "Paper Name"]
    for col in required_timetable_cols:
        if col not in timetable_df.columns:
            return f"Error: Missing essential column '{col}' in timetable.csv. Please ensure the file is correctly formatted."

    required_assigned_seats_cols = ["Roll Number", "Paper Code", "Paper Name", "Room Number", "Seat Number", "Date", "Shift"]
    for col in required_assigned_seats_cols:
        if col not in assigned_seats_df.columns:
            return f"Error: Missing essential column '{col}' in assigned_seats.csv. Please ensure seats are assigned and the file is correctly formatted."

    # 1. Get header information from timetable
    relevant_tt_exams = timetable_df[
        (timetable_df["Date"].astype(str).str.strip() == date_str) &
        (timetable_df["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if relevant_tt_exams.empty:
        return "No exams found for the selected date and shift to generate room chart."

    # Extract common info for header (assuming they are consistent for a given date/shift)
    exam_time = relevant_tt_exams.iloc[0]["Time"].strip() if "Time" in relevant_tt_exams.columns else ""
    
    # Determine the class summary for the header
    unique_classes = relevant_tt_exams['Class'].dropna().astype(str).str.strip().unique()
    class_summary_header = ""
    if len(unique_classes) == 1:
        class_summary_header = f"{unique_classes[0]} Examination {datetime.datetime.now().year}"
    elif len(unique_classes) > 1:
        class_summary_header = f"Various Classes Examination {datetime.datetime.now().year}"
    else:
        class_summary_header = f"Examination {datetime.datetime.now().year}"

    # Static header lines
    output_string_parts.append(",,,,,,,,,\nजीवाजी विश्वविद्यालय ग्वालियर ,,,,,,,,,\n\"परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरेना (म. प्र.) कोड :- G107 \",,,,,,,,,\n")
    output_string_parts.append(f"{class_summary_header},,,,,,,,,\n")
    output_string_parts.append(f"Date :- ,,{date_str},,Shift :-,{shift},,Time :- ,,\n")

    # 2. Get all assigned students for the given date and shift
    assigned_students_for_session = assigned_seats_df[
        (assigned_seats_df["Date"] == date_str) &
        (assigned_seats_df["Shift"] == shift)
    ].copy()

    if assigned_students_for_session.empty:
        output_string_parts.append("\nNo students assigned seats for this date and shift.")
        return "".join(output_string_parts)

    # Merge with timetable to get full paper names and Class
    # Ensure paper codes are comparable (e.g., int vs str)
    assigned_students_for_session['Paper Code'] = assigned_students_for_session['Paper Code'].astype(str)
    timetable_df['Paper Code'] = timetable_df['Paper Code'].astype(str)

    assigned_students_for_session = pd.merge(
        assigned_students_for_session,
        timetable_df[['Paper Code', 'Paper Name', 'Class']], # Need Class for the summary line
        on='Paper Code',
        how='left',
        suffixes=('', '_tt') # Suffixes are applied only if column names are duplicated in both DFs
    )
    # Use Paper Name from timetable if available, otherwise from assigned_seats_df
    assigned_students_for_session['Paper Name'] = assigned_students_for_session['Paper Name_tt'].fillna(assigned_students_for_session['Paper Name'])
    
    # Corrected line: Access 'Class' directly, as it would not have been suffixed if not present in assigned_seats_df
    # The 'Class' column from timetable_df is merged directly if assigned_seats_df doesn't have one,
    # otherwise it would be 'Class_tt'. We need to check which one exists.
    if 'Class_tt' in assigned_students_for_session.columns:
        assigned_students_for_session['Class'] = assigned_students_for_session['Class_tt'].fillna('')
    elif 'Class' in assigned_students_for_session.columns: # Fallback if 'Class' was already in assigned_seats_df
        assigned_students_for_session['Class'] = assigned_students_for_session['Class'].fillna('')
    else:
        assigned_students_for_session['Class'] = '' # Default if neither exists, though this should be caught by earlier checks

    # Sort by Room Number, then by Seat Number
    def sort_seat_number_key(seat):
        if isinstance(seat, str):
            match_a = re.match(r'(\d+)A', seat)
            match_b = re.match(r'(\d+)B', seat)
            if match_a:
                return (0, int(match_a.group(1))) # A-seats first
            elif match_b:
                return (1, int(match_b.group(1))) # B-seats second
            elif seat.isdigit():
                return (2, int(seat)) # Numeric seats last
        return (3, seat) # Fallback for unexpected formats

    assigned_students_for_session['sort_key'] = assigned_students_for_session['Seat Number'].apply(sort_seat_number_key)
    assigned_students_for_session = assigned_students_for_session.sort_values(by=['Room Number', 'sort_key']).drop(columns=['sort_key'])

    # Group by room for output
    students_by_room = assigned_students_for_session.groupby('Room Number')

    for room_num, room_data in students_by_room:
        output_string_parts.append(f"\n,,,कक्ष  :-,{room_num}  ,,,,\n") # Room header
        
        # Get unique papers for this room and session for the "परीक्षा का नाम" line
        unique_papers_in_room = room_data[['Class', 'Paper Code', 'Paper Name']].drop_duplicates()
        
        for _, paper_row in unique_papers_in_room.iterrows():
            paper_class = str(paper_row['Class']).strip()
            paper_code = str(paper_row['Paper Code']).strip()
            paper_name = str(paper_row['Paper Name']).strip()
            
            # Count students for this specific paper in this room
            students_for_this_paper_in_room = room_data[
                (room_data['Paper Code'].astype(str).str.strip() == paper_code) &
                (room_data['Paper Name'].astype(str).str.strip() == paper_name)
            ]
            num_students_for_paper = len(students_for_this_paper_in_room)

            output_string_parts.append(
                f"परीक्षा का नाम (Class - mode - Type),,,प्रश्न पत्र (paper- paper code - paper name),,,,उत्तर पुस्तिकाएं (number of students),,\n"
                f",,,,,,,प्राप्त ,प्रयुक्त ,शेष \n"
                f"{paper_class} - Regular - Regular,,,{paper_code} - {paper_name}        ,,,,{num_students_for_paper},,\n" # Assuming Regular for now
            )
            output_string_parts.append(",,,,,,,,,\n") # Blank line

        output_string_parts.append(",,,,,,,,,\n") # Blank line
        output_string_parts.append(f",,,Total,,,,{len(room_data)},,\n") # Total for the room
        output_string_parts.append(",,,,,,,,,\n") # Blank line
        output_string_parts.append("roll number - (room number-seat number) - 20 letters of paper name,,,,,,,,,\n")

        # Now add the roll number lines
        current_line_students = []
        for _, student_row in room_data.iterrows():
            roll_num = str(student_row['Roll Number']).strip()
            room_num_display = str(student_row['Room Number']).strip()
            seat_num_display = str(student_row['Seat Number']).strip()
            paper_name_display = str(student_row['Paper Name']).strip()
            
            # Truncate paper name to first 20 characters
            truncated_paper_name = paper_name_display[:20]

            student_entry = f"{roll_num}(कक्ष-{room_num_display}-सीट-{seat_num_display})-{truncated_paper_name}"
            current_line_students.append(student_entry)

            if len(current_line_students) == 10:
                output_string_parts.append(",".join(current_line_students) + "\n")
                current_line_students = []
        
        # Add any remaining students in the last line for the room
        if current_line_students:
            output_string_parts.append(",".join(current_line_students) + "\n")
        
        output_string_parts.append("\n") # Add an extra newline between rooms

    return "".join(output_string_parts)


# Function to display the Report Panel
def display_report_panel():
    st.subheader("📊 Exam Session Reports")

    sitting_plan, timetable, assigned_seats_df = load_data() # Load assigned_seats_df here
    all_reports_df = load_cs_reports_csv()
    room_invigilators_df = load_room_invigilator_assignments() # Load room invigilators

    if all_reports_df.empty and room_invigilators_df.empty:
        st.info("No Centre Superintendent reports or invigilator assignments available yet for statistics.")
        return
    
    if sitting_plan.empty:
        st.info("Sitting plan data is required for full report statistics.")
        # We can still show basic reports if sitting_plan is empty, but attendance % will be off.

    # Initialize expected_students_df with all necessary columns from the start
    # and populate it with expected student counts from the sitting plan
    expected_students_data = []
    if not sitting_plan.empty:
        for idx, row in sitting_plan.iterrows():
            expected_count = 0
            for i in range(1, 11):
                if pd.notna(row.get(f"Roll Number {i}")) and str(row.get(f"Roll Number {i}")).strip() != '':
                    expected_count += 1
            
            expected_students_data.append({
                'Room Number': str(row['Room Number']).strip(),
                'Class': str(row['Class']).strip(), # Keep as string, lower() later
                'Paper': str(row['Paper']).strip(),   # Keep as string, lower() later
                'Paper Code': str(row['Paper Code']).strip(), # Keep as string, lower() later
                'Paper Name': str(row['Paper Name']).strip(), # Keep as string, lower() later
                'Mode': str(row.get('Mode', '')).strip(),
                'Type': str(row.get('Type', '')).strip(),
                'expected_students_count': expected_count
            })
    expected_students_df = pd.DataFrame(expected_students_data)

    # Standardize merge keys in all_reports_df
    all_reports_df['room_num'] = all_reports_df['room_num'].astype(str).str.strip()
    all_reports_df['paper_code'] = all_reports_df['paper_code'].astype(str).str.strip().str.lower()
    all_reports_df['paper_name'] = all_reports_df['paper_name'].astype(str).str.strip().str.lower()
    all_reports_df['class'] = all_reports_df['class'].astype(str).str.strip().str.lower()

    # Standardize merge keys in expected_students_df (apply .str.lower() here)
    expected_students_df['Room Number'] = expected_students_df['Room Number'].astype(str).str.strip()
    expected_students_df['Paper Code'] = expected_students_df['Paper Code'].astype(str).str.strip().str.lower()
    expected_students_df['Paper Name'] = expected_students_df['Paper Name'].astype(str).str.strip().str.lower()
    expected_students_df['Class'] = expected_students_df['Class'].astype(str).str.strip().str.lower()


    # Merge all_reports_df with expected_students_df
    # We want to keep all report entries and add expected counts where available
    merged_reports_df = pd.merge(
        all_reports_df,
        expected_students_df,
        left_on=['room_num', 'paper_code', 'paper_name', 'class'],
        right_on=['Room Number', 'Paper Code', 'Paper Name', 'Class'],
        how='left', # Use left merge to keep all reports
        suffixes=('_report', '_sp')
    )

    # Fill NaN expected_students_count with 0 for reports where no matching sitting plan entry was found
    merged_reports_df['expected_students_count'] = merged_reports_df['expected_students_count'].fillna(0).astype(int)

    # Merge with room_invigilators_df to add invigilator info
    if not room_invigilators_df.empty:
        room_invigilators_df['date'] = room_invigilators_df['date'].astype(str).str.strip()
        room_invigilators_df['shift'] = room_invigilators_df['shift'].astype(str).str.strip().str.lower()
        room_invigilators_df['room_num'] = room_invigilators_df['room_num'].astype(str).str.strip()

        merged_reports_df = pd.merge(
            merged_reports_df,
            room_invigilators_df[['date', 'shift', 'room_num', 'invigilators']],
            on=['date', 'shift', 'room_num'],
            how='left',
            suffixes=('', '_room_inv') # Suffix to avoid column name collision if 'invigilators' existed in merged_reports_df
        )
        # Fill NaN invigilators with empty list for reports where no invigilator assignment was found
        merged_reports_df['invigilators'] = merged_reports_df['invigilators'].apply(lambda x: x if isinstance(x, list) else [])

    else:
        merged_reports_df['invigilators'] = [[]] * len(merged_reports_df) # Add empty list if no invigilator data

    st.markdown("---")
    st.subheader("Overall Statistics")

    total_reports = len(merged_reports_df)
    unique_sessions = merged_reports_df['report_key'].nunique()
    total_absent = merged_reports_df['absent_roll_numbers'].apply(len).sum()
    total_ufm = merged_reports_df['ufm_roll_numbers'].apply(len).sum()
    
    # Calculate total expected students directly from the expected_students_df
    total_expected_students = expected_students_df['expected_students_count'].sum()
    
    # Calculate total present students
    total_present_students = total_expected_students - total_absent
    # Calculate total answer sheets collected
    total_answer_sheets_collected = total_present_students - total_ufm


    overall_attendance_percentage = 0
    if total_expected_students > 0:
        overall_attendance_percentage = (total_present_students / total_expected_students) * 100

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Reports Submitted", total_reports)
    with col2:
        st.metric("Unique Exam Sessions Reported", unique_sessions)
    with col3:
        st.metric("Total Expected Students", total_expected_students)
    with col4:
        st.metric("Total Absent Students", total_absent)
    with col5:
        st.metric("Overall Attendance (%)", f"{overall_attendance_percentage:.2f}%")
    
    col_metrics_2_1, col_metrics_2_2, col_metrics_2_3 = st.columns(3)
    with col_metrics_2_1:
        st.metric("Total Present Students", total_present_students)
    with col_metrics_2_2:
        st.metric("Total UFM Cases", total_ufm)
    with col_metrics_2_3:
        st.metric("Total Answer Sheets Collected", total_answer_sheets_collected)


    # --- Paper-wise Statistics ---
    st.markdown("---")
    st.subheader("Paper-wise Statistics")

    # Group expected students by paper
    expected_by_paper = expected_students_df.groupby(['Paper Name', 'Paper Code']).agg(
        expected_students=('expected_students_count', 'sum')
    ).reset_index()
    expected_by_paper.rename(columns={'Paper Name': 'paper_name', 'Paper Code': 'paper_code'}, inplace=True)
    expected_by_paper['paper_name'] = expected_by_paper['paper_name'].astype(str).str.strip().str.lower()
    expected_by_paper['paper_code'] = expected_by_paper['paper_code'].astype(str).str.strip().str.lower()

    # Group reported data by paper
    reported_by_paper = merged_reports_df.groupby(['paper_name', 'paper_code']).agg(
        total_absent=('absent_roll_numbers', lambda x: x.apply(len).sum()),
        total_ufm=('ufm_roll_numbers', lambda x: x.apply(len).sum())
    ).reset_index()

    # Merge expected and reported data
    paper_stats = pd.merge(
        expected_by_paper,
        reported_by_paper,
        on=['paper_name', 'paper_code'],
        how='left' # Keep all papers from expected_students_df
    )

    # Fill NaN values for absent/ufm with 0 where no reports exist
    paper_stats['total_absent'] = paper_stats['total_absent'].fillna(0).astype(int)
    paper_stats['total_ufm'] = paper_stats['total_ufm'].fillna(0).astype(int)

    paper_stats['total_present'] = paper_stats['expected_students'] - paper_stats['total_absent']
    paper_stats['total_answer_sheets_collected'] = paper_stats['total_present'] - paper_stats['total_ufm']
    paper_stats['attendance_percentage'] = paper_stats.apply(
        lambda row: (row['total_present'] / row['expected_students'] * 100) if row['expected_students'] > 0 else 0,
        axis=1
    )
    paper_stats['attendance_percentage'] = paper_stats['attendance_percentage'].map('{:.2f}%'.format)

    # Rename columns for display
    paper_stats.rename(columns={
        'paper_name': 'Paper Name',
        'paper_code': 'Paper Code',
        'expected_students': 'Expected Students',
        'total_absent': 'Absent Students',
        'total_present': 'Present Students',
        'total_ufm': 'UFM Cases',
        'total_answer_sheets_collected': 'Answer Sheets Collected',
        'attendance_percentage': 'Attendance (%)'
    }, inplace=True)

    st.dataframe(paper_stats[['Paper Name', 'Paper Code', 'Expected Students', 'Present Students', 'Absent Students', 'UFM Cases', 'Answer Sheets Collected', 'Attendance (%)']])


    # --- Student Type-wise Statistics ---
    st.markdown("---")
    st.subheader("Student Type-wise Statistics")

    # Group expected students by Class, Mode, Type
    expected_by_type = expected_students_df.groupby(['Class', 'Mode', 'Type']).agg(
        expected_students=('expected_students_count', 'sum')
    ).reset_index()
    expected_by_type.rename(columns={'Class': 'Class_sp', 'Mode': 'Mode_sp', 'Type': 'Type_sp'}, inplace=True)


    # Group reported data by Class, Mode, Type (from the merged_reports_df which has _sp suffixes)
    # Ensure these columns exist before grouping, as they come from the sitting plan side of the merge
    required_type_cols_for_grouping = ['Class_sp', 'Mode_sp', 'Type_sp']
    
    # Filter merged_reports_df to ensure we only consider rows where type info is available
    if all(col in merged_reports_df.columns for col in required_type_cols_for_grouping):
        reported_by_type_df = merged_reports_df.dropna(subset=required_type_cols_for_grouping).copy()

        if not reported_by_type_df.empty:
            reported_by_type = reported_by_type_df.groupby(required_type_cols_for_grouping).agg(
                total_absent=('absent_roll_numbers', lambda x: x.apply(len).sum()),
                total_ufm=('ufm_roll_numbers', lambda x: x.apply(len).sum())
            ).reset_index()

            # Merge expected and reported data
            type_stats = pd.merge(
                expected_by_type,
                reported_by_type,
                on=required_type_cols_for_grouping,
                how='left' # Keep all types from expected_students_df
            )

            # Fill NaN values for absent/ufm with 0 where no reports exist
            type_stats['total_absent'] = type_stats['total_absent'].fillna(0).astype(int)
            type_stats['total_ufm'] = type_stats['total_ufm'].fillna(0).astype(int)

            type_stats['total_present'] = type_stats['expected_students'] - type_stats['total_absent']
            type_stats['total_answer_sheets_collected'] = type_stats['total_present'] - type_stats['total_ufm']
            type_stats['attendance_percentage'] = type_stats.apply(
                lambda row: (row['total_present'] / row['expected_students'] * 100) if row['expected_students'] > 0 else 0,
                axis=1
            )
            type_stats['attendance_percentage'] = type_stats['attendance_percentage'].map('{:.2f}%'.format)

            # Rename columns for display
            type_stats.rename(columns={
                'Class_sp': 'Class',
                'Mode_sp': 'Mode',
                'Type_sp': 'Type',
                'expected_students': 'Expected Students',
                'total_absent': 'Absent Students',
                'total_present': 'Present Students',
                'total_ufm': 'UFM Cases',
                'total_answer_sheets_collected': 'Answer Sheets Collected',
                'attendance_percentage': 'Attendance (%)'
            }, inplace=True)

            st.dataframe(type_stats[['Class', 'Mode', 'Type', 'Expected Students', 'Present Students', 'Absent Students', 'UFM Cases', 'Answer Sheets Collected', 'Attendance (%)']])
        else:
            st.info("No student type data available in reports for statistics after filtering.")
    else:
        st.info("Required student type columns (Class, Mode, Type) are not available in the merged reports for statistics.")


    st.markdown("---")
    st.subheader("Filter and View Reports")

    # Filters
    unique_dates = sorted(merged_reports_df['date'].unique())
    unique_shifts = sorted(merged_reports_df['shift'].unique())
    unique_rooms = sorted(merged_reports_df['room_num'].unique())
    unique_papers = sorted(merged_reports_df['paper_name'].unique())

    filter_date = st.selectbox("Filter by Date", ["All"] + unique_dates, key="report_filter_date")
    filter_shift = st.selectbox("Filter by Shift", ["All"] + unique_shifts, key="report_filter_shift")
    filter_room = st.selectbox("Filter by Room Number", ["All"] + unique_rooms, key="report_filter_room")
    filter_paper = st.selectbox("Filter by Paper Name", ["All"] + unique_papers, key="report_filter_paper")

    filtered_reports_df = merged_reports_df.copy()

    if filter_date != "All":
        filtered_reports_df = filtered_reports_df[filtered_reports_df['date'] == filter_date]
    if filter_shift != "All":
        filtered_reports_df = filtered_reports_df[filtered_reports_df['shift'] == filter_shift]
    if filter_room != "All":
        filtered_reports_df = filtered_reports_df[filtered_reports_df['room_num'] == filter_room]
    if filter_paper != "All":
        filtered_reports_df = filtered_reports_df[filtered_reports_df['paper_name'] == filter_paper]

    if filtered_reports_df.empty:
        st.info("No reports match the selected filters.")
    else:
        st.markdown("---")
        st.subheader("Filtered Reports Summary")
        st.dataframe(filtered_reports_df[[
            'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'invigilators', # 'invigilators' is now from merge
            'absent_roll_numbers', 'ufm_roll_numbers'
        ]].rename(columns={
            'date': 'Date', 'shift': 'Shift', 'room_num': 'Room',
            'paper_code': 'Paper Code', 'paper_name': 'Paper Name',
            'invigilators': 'Invigilators',
            'absent_roll_numbers': 'Absent Roll Numbers',
            'ufm_roll_numbers': 'UFM Roll Numbers'
        }))

        st.markdown("---")
        st.subheader("Detailed Absentee List (Filtered)")
        absent_list_data = []
        for _, row in filtered_reports_df.iterrows():
            for roll in row['absent_roll_numbers']:
                absent_list_data.append({
                    'Date': row['date'],
                    'Shift': row['shift'],
                    'Room': row['room_num'],
                    'Paper Code': row['paper_code'],
                    'Paper Name': row['paper_name'],
                    'Absent Roll Number': roll
                })
        
        if absent_list_data:
            df_absent = pd.DataFrame(absent_list_data)
            st.dataframe(df_absent)
            
            # Download Absentee List
            csv_absent = df_absent.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Absentee List as CSV",
                data=csv_absent,
                file_name=f"absent_list_{filter_date}_{filter_shift}.csv",
                mime="text/csv",
            )
        else:
            st.info("No absent students in the filtered reports.")

        st.markdown("---")
        st.subheader("Detailed UFM List (Filtered)")
        ufm_list_data = []
        for _, row in filtered_reports_df.iterrows():
            for roll in row['ufm_roll_numbers']:
                ufm_list_data.append({
                    'Date': row['date'],
                    'Shift': row['shift'],
                    'Room': row['room_num'],
                    'Paper Code': row['paper_code'],
                    'Paper Name': row['paper_name'],
                    'UFM Roll Number': roll
                })
        
        if ufm_list_data:
            df_ufm = pd.DataFrame(ufm_list_data)
            st.dataframe(df_ufm)

            # Download UFM List
            csv_ufm = df_ufm.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download UFM List as CSV",
                data=csv_ufm,
                file_name=f"ufm_list_{filter_date}_{filter_shift}.csv",
                mime="text/csv",
            )
        else:
            st.info("No UFM cases in the filtered reports.")


# Main app
st.title("Government Law College, Morena (M.P.) Examination Management System")

menu = st.radio("Select Module", ["Student View", "Admin Panel", "Centre Superintendent Panel"])

if menu == "Student View":
    sitting_plan, timetable, assigned_seats_df = load_data() # Load assigned_seats_df here

    # Check if dataframes are empty, indicating files were not loaded
    if sitting_plan.empty or timetable.empty:
        st.warning("Sitting plan or timetable data not found. Please upload them via the Admin Panel for full functionality.")
    
    option = st.radio("Choose Search Option:", [
        "Search by Roll Number and Date",
        "Get Full Exam Schedule by Roll Number",
        "View Full Timetable"
    ])

    if option == "Search by Roll Number and Date":
        roll = st.text_input("Enter Roll Number")
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
                        st.write(f"**Room Number:** {result['Room Number']}") # Display as string
                        st.write(f"**🪑 Seat Number:** {result['Seat Number']}") # Display as string
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
        
        # Load data here, inside the successful login block
        sitting_plan, timetable, assigned_seats_df = load_data()

        # File Upload Section
        st.subheader("📤 Upload Data Files")
        st.info(f"Upload your '{SITTING_PLAN_FILE}' and '{TIMETABLE_FILE}' CSV files here. These files are essential for most features.")
        
        uploaded_sitting = st.file_uploader(f"Upload {SITTING_PLAN_FILE}", type=["csv"], key="upload_sitting_csv")
        if uploaded_sitting:
            success, msg = save_uploaded_file(uploaded_sitting, SITTING_PLAN_FILE)
            if success:
                st.success(f"{SITTING_PLAN_FILE} uploaded successfully.")
                sitting_plan, timetable, assigned_seats_df = load_data() # Reload data after successful upload
            else:
                st.error(msg)

        uploaded_timetable = st.file_uploader(f"Upload {TIMETABLE_FILE}", type=["csv"], key="upload_timetable_csv")
        if uploaded_timetable:
            success, msg = save_uploaded_file(uploaded_timetable, TIMETABLE_FILE)
            if success:
                st.success(f"{TIMETABLE_FILE} uploaded successfully.")
                sitting_plan, timetable, assigned_seats_df = load_data() # Reload data after successful upload
            else:
                st.error(msg)
        
        st.markdown("---")
        st.subheader("Current Data Previews")
        col_sp, col_tt, col_assigned = st.columns(3) # Added a column for assigned_seats
        with col_sp:
            st.write(f"**{SITTING_PLAN_FILE}**")
            if not sitting_plan.empty:
                st.dataframe(sitting_plan)
            else:
                st.info("No sitting plan data loaded.")
        with col_tt:
            st.write(f"**{TIMETABLE_FILE}**")
            if not timetable.empty:
                st.dataframe(timetable)
            else:
                st.info("No timetable data loaded.")
        with col_assigned: # Display assigned_seats.csv
            st.write(f"**{ASSIGNED_SEATS_FILE}**")
            if not assigned_seats_df.empty:
                st.dataframe(assigned_seats_df)
            else:
                st.info("No assigned seats data loaded.")

        st.markdown("---") # Separator

        # Admin Panel Options
        admin_option = st.radio("Select Admin Task:", [
            "Get All Students for Date & Shift (Room Wise)",
            "Get All Students for Date & Shift (Roll Number Wise)",
            "Update Timetable Details",
            "Assign Rooms & Seats to Students", # Renamed option
            "Room Occupancy Report", # New option
            "Room Chart Report", # New option for room chart
            "Data Processing & Reports",
            "Report Panel"
        ])

        # Conditional rendering based on data availability for core functions
        # Individual functions will now check for data and display warnings.
            
        
        if admin_option == "Get All Students for Date & Shift (Room Wise)":
            st.subheader("List All Students for a Date and Shift (Room Wise)")
            if sitting_plan.empty or timetable.empty:
                st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' to use this feature.")
            else:
                list_date_input = st.date_input("Select Date", value=datetime.date.today())
                list_shift_options = ["Morning", "Evening"]
                list_shift = st.selectbox("Select Shift", list_shift_options)
                
                if st.button("Get Student List (Room Wise)"):
                    formatted_student_list_text, error_message, excel_data_for_students_list = get_all_students_for_date_shift_formatted(
                        list_date_input.strftime('%d-%m-%Y'),
                        list_shift,
                        sitting_plan,
                        timetable
                    )
                    if formatted_student_list_text:
                        st.success(f"Generated list for {list_date_input.strftime('%d-%m-%Y')} ({list_shift} Shift):")
                        st.text_area("Student List (Text Format)", formatted_student_list_text, height=500)
                        
                        # Download button for TXT
                        file_name_txt = (
                            f"all_students_list_room_wise_{list_date_input.strftime('%Y%m%d')}_"
                            f"{list_shift.lower()}.txt"
                        )
                        st.download_button(
                            label="Download Student List (Room Wise) as TXT",
                            data=formatted_student_list_text,
                            file_name=file_name_txt,
                            mime="text/plain"
                        )

                        # Download button for Excel
                        if excel_data_for_students_list:
                            output = io.BytesIO()
                            workbook = Workbook()
                            sheet = workbook.active
                            sheet.title = "Student List (Room Wise)"

                            for row_data in excel_data_for_students_list:
                                sheet.append(row_data)

                            for col_idx, col_cells in enumerate(sheet.columns):
                                max_length = 0
                                for cell in col_cells:
                                    try:
                                        if cell.value is not None:
                                            cell_value_str = str(cell.value)
                                            current_length = max(len(line) for line in cell_value_str.split('\n'))
                                            if current_length > max_length:
                                                max_length = current_length
                                    except Exception as e:
                                        st.error(f"Error processing cell: {e}")
                                        pass
                            adjusted_width = (max_length + 2)
                            sheet.column_dimensions[get_column_letter(col_idx + 1)].width = adjusted_width

                            workbook.save(output)
                            processed_data = output.getvalue()

                            file_name_excel = (
                                f"all_students_list_room_wise_{list_date_input.strftime('%Y%m%d')}_"
                                f"{list_shift.lower()}.xlsx"
                            )
                            st.download_button(
                                label="Download Student List (Room Wise) as Excel",
                                data=processed_data,
                                file_name=file_name_excel,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.warning(f"No students found: {error_message}")

        elif admin_option == "Get All Students for Date & Shift (Roll Number Wise)":
            st.subheader("List All Students for a Date and Shift (Roll Number Wise)")
            if sitting_plan.empty or timetable.empty:
                st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' to use this feature.")
            else:
                list_date_input = st.date_input("Select Date", value=datetime.date.today(), key="roll_num_wise_date")
                list_shift_options = ["Morning", "Evening"]
                list_shift = st.selectbox("Select Shift", list_shift_options, key="roll_num_wise_shift")
                
                if st.button("Get Student List (Roll Number Wise)"):
                    formatted_student_list_text, error_message, excel_data_for_students_list = get_all_students_roll_number_wise_formatted(
                        list_date_input.strftime('%d-%m-%Y'),
                        list_shift,
                        sitting_plan,
                        timetable
                    )
                    if formatted_student_list_text:
                        st.success(f"Generated list for {list_date_input.strftime('%d-%m-%Y')} ({list_shift} Shift):")
                        st.text_area("Student List (Text Format)", formatted_student_list_text, height=500)
                        
                        # Download button for TXT
                        file_name_txt = (
                            f"all_students_list_roll_wise_{list_date_input.strftime('%Y%m%d')}_"
                            f"{list_shift.lower()}.txt"
                        )
                        st.download_button(
                            label="Download Student List (Roll Number Wise) as TXT",
                            data=formatted_student_list_text,
                            file_name=file_name_txt,
                            mime="text/plain"
                        )

                        # Download button for Excel
                        if excel_data_for_students_list:
                            output = io.BytesIO()
                            workbook = Workbook()
                            sheet = workbook.active
                            sheet.title = "Student List (Roll Wise)"

                            for row_data in excel_data_for_students_list:
                                sheet.append(row_data)

                            for col_idx, col_cells in enumerate(sheet.columns):
                                max_length = 0
                                for cell in col_cells:
                                    try:
                                        if cell.value is not None:
                                            cell_value_str = str(cell.value)
                                            current_length = max(len(line) for line in cell_value_str.split('\n'))
                                            if current_length > max_length:
                                                    max_length = current_length
                                    except Exception as e:
                                        st.error(f"Error processing cell: {e}")
                                        pass
                            adjusted_width = (max_length + 2)
                            sheet.column_dimensions[get_column_letter(col_idx + 1)].width = adjusted_width

                            workbook.save(output)
                            processed_data = output.getvalue()

                            file_name_excel = (
                                f"all_students_list_roll_wise_{list_date_input.strftime('%Y%m%d')}_"
                                f"{list_shift.lower()}.xlsx"
                            )
                            st.download_button(
                                label="Download Student List (Roll Number Wise) as Excel",
                                data=processed_data,
                                file_name=file_name_excel,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.warning(f"No students found: {error_message}")

        elif admin_option == "Update Timetable Details":
            st.subheader("✏️ Update Timetable Details")
            if timetable.empty:
                st.info("No timetable data loaded. Please upload 'timetable.csv' first using the 'Upload Data Files' section.")
            else:
                st.write("Current Timetable Preview:")
                st.dataframe(timetable)

                st.markdown("---")
                st.write("Select filters to specify which entries to update:")
                
                # Filters for selecting entries to update
                unique_dates_tt = sorted(timetable['Date'].astype(str).unique().tolist())
                unique_shifts_tt = sorted(timetable['Shift'].astype(str).unique().tolist())
                unique_classes_tt = sorted(timetable['Class'].astype(str).unique().tolist())
                unique_paper_codes_tt = sorted(timetable['Paper Code'].astype(str).unique().tolist())
                unique_paper_tt = sorted(timetable['Paper'].astype(str).unique().tolist())
                unique_paper_names_tt = sorted(timetable['Paper Name'].astype(str).unique().tolist())

                filter_date_tt_update = st.selectbox("Filter by Date", ["All"] + unique_dates_tt, key="filter_date_tt_update")
                filter_shift_tt_update = st.selectbox("Filter by Shift", ["All"] + unique_shifts_tt, key="filter_shift_tt_update")
                filter_class_tt_update = st.selectbox("Filter by Class", ["All"] + unique_classes_tt, key="filter_class_tt_update")
                filter_paper_code_tt_update = st.selectbox("Filter by Paper Code", ["All"] + unique_paper_codes_tt, key="filter_paper_code_tt_update")
                filter_paper_tt_update = st.selectbox("Filter by Paper", ["All"] + unique_paper_tt, key="filter_paper_tt_update")
                filter_paper_name_tt_update = st.selectbox("Filter by Paper Name", ["All"] + unique_paper_names_tt, key="filter_paper_name_tt_update")

                st.markdown("---")
                st.write("Entries that will be updated based on your filters:")
                
                temp_filtered_tt = timetable.copy()
                if filter_date_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Date'].astype(str) == filter_date_tt_update]
                if filter_shift_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Shift'].astype(str) == filter_shift_tt_update]
                if filter_class_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Class'].astype(str) == filter_class_tt_update]
                if filter_paper_code_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Paper Code'].astype(str) == filter_paper_code_tt_update]
                if filter_paper_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Paper'].astype(str) == filter_paper_tt_update]
                if filter_paper_name_tt_update != "All":
                    temp_filtered_tt = temp_filtered_tt[temp_filtered_tt['Paper Name'].astype(str) == filter_paper_name_tt_update]
                
                if temp_filtered_tt.empty:
                    st.info("No entries match the selected filters. No updates will be applied.")
                else:
                    st.dataframe(temp_filtered_tt)

                st.markdown("---")
                st.write("Enter new values for 'Date', 'Shift', and 'Time' for the filtered entries:")
                
                # Provide default values from the first row of the *filtered* timetable if available, otherwise from the full timetable or current date/time
                default_date_update_input = datetime.date.today()
                if not temp_filtered_tt.empty and 'Date' in temp_filtered_tt.columns and pd.notna(temp_filtered_tt['Date'].iloc[0]):
                    try:
                        default_date_update_input = datetime.datetime.strptime(str(temp_filtered_tt['Date'].iloc[0]).strip(), '%d-%m-%Y').date()
                    except ValueError:
                        pass
                elif 'Date' in timetable.columns and not timetable['Date'].empty and pd.notna(timetable['Date'].iloc[0]):
                    try:
                        default_date_update_input = datetime.datetime.strptime(str(timetable['Date'].iloc[0]).strip(), '%d-%m-%Y').date()
                    except ValueError:
                        pass


                default_shift_update_input = "Morning"
                if not temp_filtered_tt.empty and 'Shift' in temp_filtered_tt.columns and pd.notna(temp_filtered_tt['Shift'].iloc[0]):
                    default_shift_update_input = str(temp_filtered_tt['Shift'].iloc[0]).strip()
                elif 'Shift' in timetable.columns and not timetable['Shift'].empty and pd.notna(timetable['Shift'].iloc[0]):
                    default_shift_update_input = str(timetable['Shift'].iloc[0]).strip()


                default_time_update_input = "09:00 AM - 12:00 PM"
                if not temp_filtered_tt.empty and 'Time' in temp_filtered_tt.columns and pd.notna(temp_filtered_tt['Time'].iloc[0]):
                    default_time_update_input = str(temp_filtered_tt['Time'].iloc[0]).strip()
                elif 'Time' in timetable.columns and not timetable['Time'].empty and pd.notna(timetable['Time'].iloc[0]):
                    default_time_update_input = str(timetable['Time'].iloc[0]).strip()


                update_date = st.date_input("New Date", value=default_date_update_input, key="update_tt_date")
                update_shift = st.selectbox("New Shift", ["Morning", "Evening"], index=["Morning", "Evening"].index(default_shift_update_input) if default_shift_update_input in ["Morning", "Evening"] else 0, key="update_tt_shift")
                update_time = st.text_input("New Time (e.g., 09:00 AM - 12:00 PM)", value=default_time_update_input, key="update_tt_time")

                if st.button("Apply Updates and Save Timetable"):
                    if temp_filtered_tt.empty:
                        st.warning("No entries matched your filters, so no updates were applied.")
                    else:
                        timetable_modified = timetable.copy()
                        
                        # Identify indices to update in the original DataFrame
                        indices_to_update = timetable_modified[
                            (timetable_modified['Date'].astype(str) == filter_date_tt_update if filter_date_tt_update != "All" else True) &
                            (timetable_modified['Shift'].astype(str) == filter_shift_tt_update if filter_shift_tt_update != "All" else True) &
                            (timetable_modified['Class'].astype(str) == filter_class_tt_update if filter_class_tt_update != "All" else True) &
                            (timetable_modified['Paper Code'].astype(str) == filter_paper_code_tt_update if filter_paper_code_tt_update != "All" else True) &                           (timetable_modified['Paper'].astype(str) == filter_paper_tt_update if filter_paper_tt_update != "All" else True) &
                            (timetable_modified['Paper Name'].astype(str) == filter_paper_name_tt_update if filter_paper_name_tt_update != "All" else True)
                        ].index

                        # Apply updates only to the identified rows
                        if not indices_to_update.empty:
                            timetable_modified.loc[indices_to_update, 'Date'] = update_date.strftime('%d-%m-%Y')
                            timetable_modified.loc[indices_to_update, 'Shift'] = update_shift
                            timetable_modified.loc[indices_to_update, 'Time'] = update_time

                            success, msg = save_uploaded_file(timetable_modified, TIMETABLE_FILE)
                            if success:
                                st.success(f"Timetable details updated for {len(indices_to_update)} entries and saved successfully.")
                                # Reload data to reflect changes in the app
                                sitting_plan, timetable, assigned_seats_df = load_data() 
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            st.warning("No entries matched your filters to apply updates.")

        elif admin_option == "Assign Rooms & Seats to Students": # Replaced with assign_seats_app.py logic
            st.subheader("📘 Room & Seat Assignment Tool")
            st.markdown("""
            This tool helps manage seat assignments for exams, offering real-time status updates,
            capacity warnings, and clear error messages based on your selected seat format.
            """)

            if sitting_plan.empty or timetable.empty:
                st.error(f"Error: `{SITTING_PLAN_FILE}` or `{TIMETABLE_FILE}` not found. Please upload these files to run the assignment tool.")
                st.stop() # Stop execution if critical files are missing

            # --- Session State for consistent UI updates ---
            if 'current_room_status_a_rem' not in st.session_state:
                st.session_state.current_room_status_a_rem = None
            if 'current_room_status_b_rem' not in st.session_state:
                st.session_state.current_room_status_b_rem = None
            if 'current_room_status_total_rem' not in st.session_state:
                st.session_state.current_room_status_total_rem = None

            # --- Input Widgets ---
            st.subheader("Exam Details")
            # Ensure date and shift options are available from timetable
            date_options = sorted(timetable["Date"].dropna().unique())
            shift_options = sorted(timetable["Shift"].dropna().unique())

            if not date_options or not shift_options:
                st.warning("Timetable is empty or missing Date/Shift information. Please upload a complete timetable.")
            else:
                date = st.selectbox("Select Exam Date", date_options, key="assign_date_select")
                shift = st.selectbox("Select Shift", shift_options, key="assign_shift_select")

                # --- NEW: Paper-wise summary chart for the selected session ---
                st.markdown("---")
                st.subheader("Session Student Summary (Assigned vs. Unassigned)")
                session_paper_summary_df = get_session_paper_summary(date, shift, sitting_plan, assigned_seats_df, timetable)
                if not session_paper_summary_df.empty:
                    st.dataframe(session_paper_summary_df)
                else:
                    st.info("No student data found for the selected date and shift.")
                st.markdown("---")
                # --- END NEW ---

                # Filter relevant papers based on selected date and shift
                filtered_papers = timetable[(timetable["Date"] == date) & (timetable["Shift"] == shift)]
                paper_options = filtered_papers[["Paper Code", "Paper Name"]].drop_duplicates().values.tolist()
                paper_display = [f"{code} - {name}" for code, name in paper_options]

                selected_paper = st.selectbox("Select Paper Code and Name", paper_display, key="assign_paper_select")

                # Only proceed if a paper is selected
                if selected_paper:
                    paper_code = selected_paper.split(" - ")[0].strip()
                    paper_name = selected_paper.split(" - ", 1)[1].strip()

                    st.subheader("Room & Seat Configuration")
                    # Added .strip() to handle potential leading/trailing spaces in room input
                    room = st.text_input("Enter Room Number (e.g., 1, G230)", key="room_input").strip()

                    # Enhanced capacity input
                    col1, col2 = st.columns(2)
                    with col1:
                        total_capacity = st.number_input("Enter Total Room Capacity (for '1 to N' format)", min_value=1, max_value=200, value=60, key="total_capacity_input")
                    with col2:
                        capacity_per_format = st.number_input("Capacity per Format (for 'A/B' formats)", min_value=1, max_value=100, value=30, key="capacity_per_format_input")

                    seat_format = st.radio("Select Seat Assignment Format:", ["1 to N", "1A to NA", "1B to NB"], key="seat_format_radio")

                    # --- Show current room status BEFORE assignment ---
                    if room:
                        # Get all assigned seats for the current room, date, and shift
                        room_assigned_seats_current = assigned_seats_df[
                            (assigned_seats_df["Room Number"] == room) &
                            (assigned_seats_df["Date"] == date) &
                            (assigned_seats_df["Shift"] == shift)
                        ]["Seat Number"].tolist()

                        # Calculate used seats for A, B, and no-suffix formats
                        a_seats_used_current = len([s for s in room_assigned_seats_current if s.endswith("A")])
                        b_seats_used_current = len([s for s in room_assigned_seats_current if s.endswith("B")])
                        no_suffix_seats_used_current = len([s for s in room_assigned_seats_current if not s.endswith("A") and not s.endswith("B")])

                        st.subheader("📊 Current Room Status")
                        if seat_format in ["1A to NA", "1B to NB"]:
                            a_remaining_current = capacity_per_format - a_seats_used_current
                            b_remaining_current = capacity_per_format - b_seats_used_current
                            st.info(f"A-format: **{a_remaining_current}** remaining ({a_seats_used_current}/{capacity_per_format} used)")
                            st.info(f"B-format: **{b_remaining_current}** remaining ({b_seats_used_current}/{capacity_per_format} used)")
                            st.session_state.current_room_status_a_rem = a_remaining_current
                            st.session_state.current_room_status_b_rem = b_remaining_current
                            st.session_state.current_room_status_total_rem = None # Clear total if A/B is selected
                        else: # 1 to N format
                            remaining_current = total_capacity - no_suffix_seats_used_current
                            st.info(f"Total: **{remaining_current}** seats remaining ({no_suffix_seats_used_current}/{total_capacity} used)")
                            st.session_state.current_room_status_total_rem = remaining_current
                            st.session_state.current_room_status_a_rem = None # Clear A/B if total is selected
                            st.session_state.current_room_status_b_rem = None


                    st.markdown("---")

                    # --- Assign Seats Button ---
                    if st.button("✅ Assign Seats", key="assign_button"):
                        if not room:
                            st.error("Please enter a Room Number before assigning seats.")
                            st.stop()

                        # Extract roll numbers for the selected paper from sitting_plan
                        roll_cols = [col for col in sitting_plan.columns if col.lower().startswith("roll number")]
                        # Ensure Paper Code is treated as string for comparison
                        paper_rows = sitting_plan[sitting_plan["Paper Code"].astype(str) == paper_code]
                        all_rolls = paper_rows[roll_cols].values.flatten()
                        all_rolls = [str(r).strip() for r in all_rolls if str(r).strip() and str(r).lower() != 'nan']

                        # Remove previously assigned roll numbers for this paper/date/shift
                        already_assigned_rolls = assigned_seats_df[
                            (assigned_seats_df["Paper Code"].astype(str) == paper_code) &
                            (assigned_seats_df["Date"] == date) &
                            (assigned_seats_df["Shift"] == shift)
                        ]["Roll Number"].astype(str).tolist()

                        unassigned_rolls = [r for r in all_rolls if r not in already_assigned_rolls]

                        if not unassigned_rolls:
                            st.warning("⚠️ All students for this paper are already assigned for this date/shift!")
                            st.stop()

                        # Determine seat format and capacity for the assignment logic
                        suffix = ""
                        format_capacity_for_assignment = 0 # Initialize

                        if seat_format == "1 to N":
                            suffix = ""
                            format_capacity_for_assignment = total_capacity
                        elif seat_format == "1A to NA":
                            suffix = "A"
                            format_capacity_for_assignment = capacity_per_format
                        elif seat_format == "1B to NB":
                            suffix = "B"
                            format_capacity_for_assignment = capacity_per_format

                        # Get a set of all *physically occupied seat keys* for the current room, date, and shift
                        occupied_physical_seat_keys = set(
                            (str(x[0]), str(x[1]), str(x[2]), str(x[3]))
                            for x in assigned_seats_df[
                                (assigned_seats_df["Room Number"] == room) &
                                (assigned_seats_df["Date"] == date) &
                                (assigned_seats_df["Shift"] == shift)
                            ][['Room Number', 'Seat Number', 'Date', 'Shift']].values
                        )

                        # Find truly available seat numbers for the selected format.
                        available_seat_numbers = []
                        for i in range(1, format_capacity_for_assignment + 1):
                            prospective_seat_string = f"{i}{suffix}"
                            prospective_seat_key = (str(room), prospective_seat_string, str(date), str(shift)) # Ensure consistency

                            # A seat is available if its specific key (Room, Seat String, Date, Shift) is NOT already taken
                            if prospective_seat_key not in occupied_physical_seat_keys:
                                available_seat_numbers.append(i)

                        # --- Clear Error Messages & No Automatic Format Switching ---
                        if not available_seat_numbers:
                            st.error(f"❌ ERROR: No seats available in **{seat_format}** format for Room {room}! Please manually change to a different format (e.g., '1A to NA' or '1B to NB') or room.")
                            st.stop() # Stop execution after displaying error

                        # --- Capacity Warnings ---
                        if len(available_seat_numbers) < len(unassigned_rolls):
                            st.warning(f"⚠️ Capacity Warning: Only **{len(available_seat_numbers)}** seats available in **{seat_format}** format, but **{len(unassigned_rolls)}** students need assignment.")
                            st.warning(f"💡 This will assign the first **{len(available_seat_numbers)}** students. Remaining students will need assignment in a different format or room.")

                        # Generate actual seat strings with the selected suffix
                        seats_to_assign_count = min(len(available_seat_numbers), len(unassigned_rolls))
                        assigned_seat_strings = [f"{available_seat_numbers[i]}{suffix}" for i in range(seats_to_assign_count)]

                        # Assign seats to students
                        students_to_assign = unassigned_rolls[:seats_to_assign_count]
                        assigned_rows = []

                        for i, roll in enumerate(students_to_assign):
                            seat_num_str = assigned_seat_strings[i]
                            current_assignment_key = (str(room), seat_num_str, str(date), str(shift)) # Ensure consistency

                            # Check if this specific physical seat key is already taken
                            if current_assignment_key in occupied_physical_seat_keys:
                                st.warning(f"⚠️ Conflict: Seat **{seat_num_str}** in Room **{room}** is already assigned for this date/shift. Skipping assignment for Roll Number **{roll}**.")
                            else:
                                assigned_rows.append({
                                    "Roll Number": roll,
                                    "Paper Code": int(paper_code),
                                    "Paper Name": paper_name,
                                    "Room Number": room,
                                    "Seat Number": seat_num_str,
                                    "Date": date,
                                    "Shift": shift
                                })
                                # Add this new assignment's physical seat key to our occupied set for this batch
                                occupied_physical_seat_keys.add(current_assignment_key) # Update the set for subsequent assignments in this batch

                        new_assignments_df = pd.DataFrame(assigned_rows)

                        if new_assignments_df.empty:
                            st.warning("No new unique seats could be assigned in this attempt, possibly due to conflicts with existing assignments.")
                            # st.stop() # Removed st.stop() to allow further interaction
                        else:
                            # Merge new assignments with existing ones and save
                            assigned_seats_df = pd.concat([assigned_seats_df, new_assignments_df], ignore_index=True)
                            # Re-add drop_duplicates on Roll Number/Paper Code/Date/Shift to prevent a student
                            # from being assigned the *same paper* multiple times if the button is clicked repeatedly.
                            assigned_seats_df.drop_duplicates(subset=["Roll Number", "Paper Code", "Date", "Shift"], inplace=True)
                            
                            success, msg = save_uploaded_file(assigned_seats_df, ASSIGNED_SEATS_FILE)
                            if success:
                                st.success(f"✅ Successfully assigned **{len(new_assignments_df)}** students to Room **{room}** using **{seat_format}** format.")
                                st.dataframe(new_assignments_df) # Display only the newly assigned students
                            else:
                                st.error(f"Error saving assigned seats: {msg}")

                            # --- Display Updated Room Status AFTER assignment ---
                            st.subheader("📊 Updated Room Status")
                            updated_room_assigned_seats = assigned_seats_df[
                                (assigned_seats_df["Room Number"] == room) &
                                (assigned_seats_df["Date"] == date) &
                                (assigned_seats_df["Shift"] == shift)
                            ]["Seat Number"].tolist()

                            updated_a_seats_used = len([s for s in updated_room_assigned_seats if s.endswith("A")])
                            updated_b_seats_used = len([s for s in updated_room_assigned_seats if s.endswith("B")])
                            updated_no_suffix_seats_used = len([s for s in updated_room_assigned_seats if not s.endswith("A") and not s.endswith("B")])

                            if seat_format in ["1A to NA", "1B to NB"]:
                                updated_a_remaining = capacity_per_format - updated_a_seats_used
                                updated_b_remaining = capacity_per_format - updated_b_seats_used
                                st.info(f"A-format: **{updated_a_remaining}** remaining ({updated_a_seats_used}/{capacity_per_format} used)")
                                st.info(f"B-format: **{updated_b_remaining}** remaining ({updated_b_seats_used}/{capacity_per_format} used)")
                            else: # 1 to N format
                                updated_remaining = total_capacity - updated_no_suffix_seats_used
                                st.info(f"Total: **{updated_remaining}** seats remaining ({updated_no_suffix_seats_used}/{total_capacity} used)")

                            if len(new_assignments_df) < len(unassigned_rolls):
                                remaining_students_after_assignment = len(unassigned_rolls) - len(new_assignments_df)
                                st.warning(f"⚠️ **{remaining_students_after_assignment}** students from this paper still need assignment. Please run assignment again, potentially with a different format or room.")
                            
                            st.rerun() # Rerun to refresh the dataframes and status

                    st.markdown("---")

                    # --- Display all assignments for the selected room/date/shift ---
                    if room:
                        with st.expander(f"📄 View all current assignments for Room {room} on {date} ({shift})"):
                            room_assignments_display = assigned_seats_df[
                                (assigned_seats_df["Room Number"] == room) &
                                (assigned_seats_df["Date"] == date) &
                                (assigned_seats_df["Shift"] == shift)
                            ].copy() # Use .copy() to avoid SettingWithCopyWarning

                            if room_assignments_display.empty:
                                st.info("No assignments yet for this room, date, and shift.")
                            else:
                                # Proper sorting for seat numbers (e.g., 1A, 2A, ..., 10A, 1B, 2B)
                                def sort_seat_number(seat):
                                    if isinstance(seat, str):
                                        if seat.endswith('A'):
                                            return (0, int(seat[:-1])) # Group A seats first
                                        elif seat.endswith('B'):
                                            return (1, int(seat[:-1])) # Group B seats second
                                        elif seat.isdigit():
                                            return (2, int(seat)) # Group 1 to N seats last
                                    return (3, seat) # For any unexpected format, put at the end

                                room_assignments_display['sort_key'] = room_assignments_display['Seat Number'].apply(sort_seat_number)
                                room_assignments_sorted = room_assignments_display.sort_values(by='sort_key').drop('sort_key', axis=1)
                                st.dataframe(room_assignments_sorted, use_container_width=True)

            # --- Reset Button (outside the paper selection block for broader access) ---
            st.markdown("---")
            st.subheader("Maintenance")
            if st.button("🔄 Reset All Assigned Seats (Clear assigned_seats.csv)", key="reset_button"):
                if os.path.exists(ASSIGNED_SEATS_FILE):
                    os.remove(ASSIGNED_SEATS_FILE)
                    st.success("`assigned_seats.csv` has been deleted. All assignments reset.")
                else:
                    st.info("No `assigned_seats.csv` found to reset.")
                st.rerun() # Rerun the app to reflect the changes

        elif admin_option == "Room Occupancy Report": # New Room Occupancy Report section
            display_room_occupancy_report(sitting_plan, assigned_seats_df, timetable)

        elif admin_option == "Room Chart Report": # New Room Chart Report section
            st.subheader("📄 Room Chart Report")
            st.info("Generate a detailed room chart showing student seating arrangements for a specific exam session.")

            if sitting_plan.empty or timetable.empty or assigned_seats_df.empty:
                st.warning("Please upload 'sitting_plan.csv', 'timetable.csv', and ensure seats are assigned via 'Assign Rooms & Seats to Students' to generate this report.")
                st.stop() # Use st.stop() to halt execution if critical data is missing
            
            # Date and Shift filters for the room chart
            chart_date_options = sorted(timetable["Date"].dropna().unique())
            chart_shift_options = sorted(timetable["Shift"].dropna().unique())

            if not chart_date_options or not chart_shift_options:
                st.info("No exam dates or shifts found in the timetable to generate a room chart.")
                st.stop() # Use st.stop() to halt execution if no options

            selected_chart_date = st.selectbox("Select Date", chart_date_options, key="room_chart_date")
            selected_chart_shift = st.selectbox("Select Shift", chart_shift_options, key="room_chart_shift")

            if st.button("Generate Room Chart"):
                with st.spinner("Generating room chart..."):
                    # The generate_room_chart_report function now returns a string message if there's an error
                    room_chart_output = generate_room_chart_report(selected_chart_date, selected_chart_shift, sitting_plan, assigned_seats_df, timetable)
                    
                    # Check if the output is an error message (string) or the actual chart data
                    if room_chart_output and "Error:" in room_chart_output:
                        st.error(room_chart_output) # Display the error message
                    elif room_chart_output:
                        st.text_area("Generated Room Chart", room_chart_output, height=600)
                        
                        # Download button
                        file_name = f"room_chart_{selected_chart_date}_{selected_chart_shift}.csv"
                        st.download_button(
                            label="Download Room Chart as CSV",
                            data=room_chart_output.encode('utf-8'),
                            file_name=file_name,
                            mime="text/csv",
                        )
                    else:
                        st.warning("Could not generate room chart. Please ensure data is complete and assignments are made.")


        elif admin_option == "Data Processing & Reports":
            st.subheader("⚙️ Data Processing & Report Generation")

            st.markdown("---")
            st.subheader("Upload PDFs for Sitting Plan (pdf_folder.zip)")
            st.info(f"Upload a ZIP file containing folders of PDFs (e.g., 'pdf_folder/Zoology'). Each folder name will be used as the 'Paper' name. This will generate/update '{SITTING_PLAN_FILE}' and an initial '{TIMETABLE_FILE}'.")
            uploaded_sitting_plan_zip = st.file_uploader("Upload Sitting Plan PDFs (ZIP)", type=["zip"], key="upload_sitting_plan_zip")
            if uploaded_sitting_plan_zip:
                with st.spinner("Processing sitting plan PDFs and generating initial timetable... This may take a while."):
                    success, message = process_sitting_plan_pdfs(uploaded_sitting_plan_zip, SITTING_PLAN_FILE, TIMETABLE_FILE)
                    if success:
                        st.success(message)
                        # Reload data after processing
                        sitting_plan, timetable, assigned_seats_df = load_data()
                    else:
                        st.error(message)

            st.markdown("---")
            st.subheader("Upload Attestation PDFs (rasa_pdf.zip)")
            st.info(f"Upload a ZIP file containing attestation PDFs. These will be parsed to create a combined attestation data CSV ('{ATTESTATION_DATA_FILE}') and then automatically generate college statistics ('{COLLEGE_STATISTICS_FILE}').")
            uploaded_attestation_zip = st.file_uploader("Upload Attestation PDFs (ZIP)", type=["zip"], key="upload_attestation_zip")
            if uploaded_attestation_zip:
                with st.spinner("Processing attestation PDFs and generating college statistics... This may take a while."):
                    success, message = process_attestation_pdfs(uploaded_attestation_zip, ATTESTATION_DATA_FILE)
                    if success:
                        st.success(message)
                        # Automatically generate college statistics after attestation PDFs are processed
                        st.info("Generating college statistics...")
                        stats_success, stats_message = generate_college_statistics(ATTESTATION_DATA_FILE, COLLEGE_STATISTICS_FILE)
                        if stats_success:
                            st.success(stats_message)
                            if os.path.exists(COLLEGE_STATISTICS_FILE):
                                with open(COLLEGE_STATISTICS_FILE, "rb") as f:
                                    st.download_button(
                                        label="Download College Statistics CSV",
                                        data=f,
                                        file_name=COLLEGE_STATISTICS_FILE,
                                        mime="text/csv",
                                        key="download_college_stats_auto" # Unique key added
                                    )
                        else:
                            st.error(stats_message)
                    else:
                        st.error(message)

            st.markdown("---")
            st.subheader("Generate College Statistics (Manual Trigger)")
            st.info(f"This will generate college-wise statistics from '{ATTESTATION_DATA_FILE}' and save it to '{COLLEGE_STATISTICS_FILE}'. Only use if attestation data is already processed.")
            if st.button("Generate College Statistics (Manual)"):
                success, message = generate_college_statistics(ATTESTATION_DATA_FILE, COLLEGE_STATISTICS_FILE)
                if success:
                    st.success(message)
                    if os.path.exists(COLLEGE_STATISTICS_FILE):
                        with open(COLLEGE_STATISTICS_FILE, "rb") as f:
                            st.download_button(
                                label="Download College Statistics CSV",
                                data=f,
                                file_name=COLLEGE_STATISTICS_FILE,
                                mime="text/csv",
                                key="download_college_stats_manual" # Unique key added
                            )
                else:
                    st.error(message)

        elif admin_option == "Report Panel":
            display_report_panel()

    else:
        st.warning("Enter valid admin credentials.")

elif menu == "Centre Superintendent Panel":
    st.subheader("🔐 Centre Superintendent Login")
    if cs_login():
        st.success("Login successful!")

        # Load data for CS panel
        sitting_plan, timetable, assigned_seats_df = load_data() # Load assigned_seats_df here
        
        cs_panel_option = st.radio("Select CS Task:", ["Report Exam Session", "Manage Exam Team & Shift Assignments", "View Full Timetable", "Room Chart Report"]) # Added Room Chart Report

        if cs_panel_option == "Manage Exam Team & Shift Assignments":
            st.subheader("👥 Manage Exam Team Members")
            
            current_members = load_exam_team_members()
            new_member_name = st.text_input("Add New Team Member Name")
            if st.button("Add Member"):
                if new_member_name and new_member_name not in current_members:
                    current_members.append(new_member_name)
                    success, msg = save_exam_team_members(current_members)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                elif new_member_name:
                    st.warning("Member already exists.")
                else:
                    st.warning("Please enter a name.")

            if current_members:
                st.write("Current Team Members:")
                st.write(current_members)
                
                member_to_remove = st.selectbox("Select Member to Remove", [""] + current_members)
                if st.button("Remove Selected Member"):
                    if member_to_remove:
                        current_members.remove(member_to_remove)
                        success, msg = save_exam_team_members(current_members)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Please select a member to remove.")
            else:
                st.info("No team members added yet.")

            st.markdown("---")
            st.subheader("🗓️ Assign Roles for Exam Shift")

            assignment_date = st.date_input("Select Date for Assignment", value=datetime.date.today(), key="assignment_date")
            assignment_shift = st.selectbox("Select Shift for Assignment", ["Morning", "Evening"], key="assignment_shift")

            all_team_members = load_exam_team_members()
            if not all_team_members:
                st.warning("Please add exam team members first in the 'Manage Exam Team Members' section.")
            else:
                current_assignments_df = load_shift_assignments()
                current_assignment_for_shift = current_assignments_df[
                    (current_assignments_df['date'] == assignment_date.strftime('%d-%m-%Y')) &
                    (current_assignments_df['shift'] == assignment_shift)
                ]
                
                loaded_senior_cs = []
                loaded_cs = []
                loaded_assist_cs = []
                loaded_perm_inv = []
                loaded_assist_perm_inv = []
                loaded_class_3 = []
                loaded_class_4 = []



                if not current_assignment_for_shift.empty:
                    loaded_senior_cs = current_assignment_for_shift.iloc[0].get('senior_center_superintendent', [])
                    loaded_cs = current_assignment_for_shift.iloc[0].get('center_superintendent', [])
                    loaded_assist_cs = current_assignment_for_shift.iloc[0].get('assistant_center_superintendent', [])
                    loaded_perm_inv = current_assignment_for_shift.iloc[0].get('permanent_invigilator', [])
                    loaded_assist_perm_inv = current_assignment_for_shift.iloc[0].get('assistant_permanent_invigilator', [])
                    loaded_class_3 = current_assignment_for_shift.iloc[0].get('class_3_worker', [])
                    loaded_class_4 = current_assignment_for_shift.iloc[0].get('class_4_worker', [])



                selected_senior_cs = st.multiselect("Senior Center Superintendent (Max 1)", all_team_members, default=loaded_senior_cs, max_selections=1)
                selected_cs = st.multiselect("Center Superintendent (Max 1)", all_team_members, default=loaded_cs, max_selections=1)
                selected_assist_cs = st.multiselect("Assistant Center Superintendent (Max 3)", all_team_members, default=loaded_assist_cs, max_selections=3)
                selected_perm_inv = st.multiselect("Permanent Invigilator (Max 1)", all_team_members, default=loaded_perm_inv, max_selections=1)
                selected_assist_perm_inv = st.multiselect("Assistant Permanent Invigilator (Max 5)", all_team_members, default=loaded_assist_perm_inv, max_selections=5)
                selected_class_3 = st.multiselect("class_3_worker (Max 10)", all_team_members, default=loaded_class_3, max_selections=10)
                selected_class_4 = st.multiselect("class_4_worker (Max 10)", all_team_members, default=loaded_class_4, max_selections=10)


                if st.button("Save Shift Assignments"):
                    all_selected_members = (
                        selected_senior_cs + selected_cs + selected_assist_cs +
                        selected_perm_inv + selected_assist_perm_inv + selected_class_3 + selected_class_4
                    )
                    if len(all_selected_members) != len(set(all_selected_members)):
                        st.error("Error: A team member cannot be assigned to multiple roles for the same shift.")
                    else:
                        assignments_to_save = {
                            'senior_center_superintendent': selected_senior_cs,
                            'center_superintendent': selected_cs,
                            'assistant_center_superintendent': selected_assist_cs,
                            'permanent_invigilator': selected_perm_inv,
                            'assistant_permanent_invigilator': selected_assist_perm_inv,
                            'class_3_worker': selected_class_3,
                            'class_4_worker': selected_class_4
                        }
                        success, msg = save_shift_assignment(assignment_date.strftime('%d-%m-%Y'), assignment_shift, assignments_to_save)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                
                st.markdown("---")
                st.subheader("Current Shift Assignments")
                display_assignments_df = load_shift_assignments()
                if not display_assignments_df.empty:
                    st.dataframe(display_assignments_df)
                else:
                    st.info("No shift assignments saved yet.")

            st.markdown("---")

            st.subheader("Assign Invigilators to Rooms")
            if assigned_seats_df.empty: # Check assigned_seats_df instead of sitting_plan/timetable for rooms
                st.info("Please assign seats to students via the Admin Panel's 'Assign Rooms & Seats to Students' section first to see available rooms for invigilator assignment.")
            else:
                room_inv_date = st.date_input("Select Date for Room Invigilators", value=datetime.date.today(), key="room_inv_date")
                room_inv_shift = st.selectbox("Select Shift for Room Invigilators", ["Morning", "Evening"], key="room_inv_shift")
                
                # MODIFIED: Get unique rooms for the selected date and shift from assigned_seats_df
                relevant_rooms_assigned = assigned_seats_df[
                    (assigned_seats_df["Date"].astype(str).str.strip() == room_inv_date.strftime('%d-%m-%Y')) &
                    (assigned_seats_df["Shift"].astype(str).str.strip().str.lower() == room_inv_shift.lower())
                ]
                
                unique_relevant_rooms = sorted(list(relevant_rooms_assigned['Room Number'].dropna().astype(str).str.strip().unique()))

                selected_room_for_inv = st.selectbox("Select Room to Assign Invigilators", [""] + unique_relevant_rooms, key="selected_room_for_inv")

                if selected_room_for_inv:
                    current_room_inv_df = load_room_invigilator_assignments()
                    loaded_invigilators = []
                    
                    filtered_inv_for_room = current_room_inv_df[
                        (current_room_inv_df['date'] == room_inv_date.strftime('%d-%m-%Y')) &
                        (current_room_inv_df['shift'] == room_inv_shift) &
                        (current_room_inv_df['room_num'] == selected_room_for_inv)
                    ]
                    
                    if not filtered_inv_for_room.empty:
                        loaded_invigilators = filtered_inv_for_room.iloc[0].get('invigilators', [])
                    
                    invigilators_for_room = st.multiselect(
                        "Invigilators for this Room",
                        options=all_team_members, # Use the same team members list
                        default=loaded_invigilators,
                        key="invigilators_for_room_multiselect"
                    )

                    if st.button("Save Room Invigilators"):
                        success, msg = save_room_invigilator_assignment(
                            room_inv_date.strftime('%d-%m-%Y'),
                            room_inv_shift,
                            selected_room_for_inv,
                            invigilators_for_room
                        )
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.info("Select a date, shift, and room to assign invigilators.")
                
                st.markdown("---")
                st.subheader("Current Room Invigilator Assignments")
                display_room_inv_df = load_room_invigilator_assignments()
                if not display_room_inv_df.empty:
                    st.dataframe(display_room_inv_df)
                else:
                    st.info("No room invigilator assignments saved yet.")


        elif cs_panel_option == "Report Exam Session":
            st.subheader("📝 Report Exam Session")
            if sitting_plan.empty or timetable.empty:
                st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' via the Admin Panel to report exam sessions.")
            else:
                # Date and Shift selection
                report_date = st.date_input("Select Date", value=datetime.date.today(), key="cs_report_date")
                report_shift = st.selectbox("Select Shift", ["Morning", "Evening"], key="cs_report_shift")

                # Filter timetable for selected date and shift to get available exams
                available_exams_tt = timetable[
                    (timetable["Date"].astype(str).str.strip() == report_date.strftime('%d-%m-%Y')) &
                    (timetable["Shift"].astype(str).str.strip().str.lower() == report_shift.lower())
                ]

                if available_exams_tt.empty:
                    st.warning("No exams scheduled for the selected date and shift.")
                else:
                    # Get unique exam sessions (Room + Paper Code) from sitting_plan that match timetable
                    
                    # Prepare sitting_plan for merging by creating a common key
                    sitting_plan_temp = sitting_plan.copy()
                    sitting_plan_temp['merge_key'] = sitting_plan_temp['Class'].astype(str).str.strip().str.lower() + "_" + \
                                                      sitting_plan_temp['Paper'].astype(str).str.strip() + "_" + \
                                                      sitting_plan_temp['Paper Code'].astype(str).str.strip() + "_" + \
                                                      sitting_plan_temp['Paper Name'].astype(str).str.strip()

                    # Prepare available_exams_tt for merging
                    available_exams_tt_temp = available_exams_tt.copy()
                    available_exams_tt_temp['merge_key'] = available_exams_tt_temp['merge_key'] = available_exams_tt_temp['Class'].astype(str).str.strip().str.lower() + "_" + \
                                                            available_exams_tt_temp['Paper'].astype(str).str.strip() + "_" + \
                                                            available_exams_tt_temp['Paper Code'].astype(str).str.strip() + "_" + \
                                                            available_exams_tt_temp['Paper Name'].astype(str).str.strip()

                    merged_data = pd.merge(
                        available_exams_tt_temp,
                        sitting_plan_temp,
                        on='merge_key',
                        how='inner',
                        suffixes=('_tt', '_sp')
                    )
                    
                    if merged_data.empty:
                        st.warning("No sitting plan data found for the selected exams. Ensure data consistency.")
                    else:
                        # Create a unique identifier for each exam session (Room - Paper Code (Paper Name))
                        merged_data['exam_session_id'] = merged_data['Room Number'].astype(str).str.strip() + " - " + \
                                                          merged_data['Paper Code_tt'].astype(str).str.strip() + " (" + \
                                                          merged_data['Paper Name_tt'].astype(str).str.strip() + ")"
                        
                        unique_exam_sessions = merged_data[['Room Number', 'Paper Code_tt', 'Paper Name_tt', 'exam_session_id']].drop_duplicates().sort_values(by='exam_session_id')
                        
                        if unique_exam_sessions.empty:
                            st.warning("No unique exam sessions found for the selected date and shift.")
                        else:
                            selected_exam_session_option = st.selectbox(
                                "Select Exam Session (Room - Paper Code (Paper Name))",
                                [""] + unique_exam_sessions['exam_session_id'].tolist(),
                                key="cs_exam_session_select"
                            )

                            if selected_exam_session_option:
                                # Extract room_number, paper_code, paper_name from the selected option
                                selected_room_num = selected_exam_session_option.split(" - ")[0].strip()
                                selected_paper_code_with_name = selected_exam_session_option.split(" - ")[1].strip()
                                selected_paper_code = selected_paper_code_with_name.split(" (")[0].strip()
                                selected_paper_name = selected_paper_code_with_name.split(" (")[1].replace(")", "").strip()

                                # Find the corresponding class for the selected session
                                # Assuming for a given room, paper_code, paper_name, there's a consistent class.
                                matching_session_info = merged_data[
                                    (merged_data['Room Number'].astype(str).str.strip() == selected_room_num) &
                                    (merged_data['Paper Code_tt'].astype(str).str.strip() == selected_paper_code) &
                                    (merged_data['Paper Name_tt'].astype(str).str.strip() == selected_paper_name)
                                ]
                                selected_class = ""
                                if not matching_session_info.empty:
                                    selected_class = str(matching_session_info.iloc[0]['Class_sp']).strip() # Use Class_sp from sitting plan

                                # Create a unique key for CSV row ID
                                report_key = f"{report_date.strftime('%Y%m%d')}_{report_shift.lower()}_{selected_room_num}_{selected_paper_code}"

                                # Load existing report from CSV
                                loaded_success, loaded_report = load_single_cs_report_csv(report_key)
                                if loaded_success:
                                    st.info("Existing report loaded.")
                                else:
                                    st.info("No existing report found for this session. Starting new.")
                                    loaded_report = {} # Ensure it's an empty dict if not found

                                # Get all expected roll numbers for this specific session
                                expected_students_for_session = []
                                # Filter merged_data for the selected session
                                session_students = merged_data[
                                    (merged_data['Room Number'].astype(str).str.strip() == selected_room_num) &
                                    (merged_data['Paper Code_tt'].astype(str).str.strip() == selected_paper_code) &
                                    (merged_data['Paper Name_tt'].astype(str).str.strip() == selected_paper_name)
                                ]

                                for _, row in session_students.iterrows():
                                    for i in range(1, 11):
                                        roll_col = f"Roll Number {i}"
                                        if roll_col in row.index and pd.notna(row[roll_col]) and str(row[roll_col]).strip() != '':
                                            expected_students_for_session.append(str(row[roll_col]).strip())
                                
                                expected_students_for_session = sorted(list(set(expected_students_for_session))) # Remove duplicates and sort

                                st.write(f"**Reporting for:** Room {selected_room_num}, Paper: {selected_paper_name} ({selected_paper_code})")

                                # Multiselect for Absent Roll Numbers
                                absent_roll_numbers_selected = st.multiselect(
                                    "Absent Roll Numbers", 
                                    options=expected_students_for_session, 
                                    default=loaded_report.get('absent_roll_numbers', []),
                                    key="absent_roll_numbers_multiselect"
                                )

                                # Multiselect for UFM Roll Numbers
                                ufm_roll_numbers_selected = st.multiselect(
                                    "UFM (Unfair Means) Roll Numbers", 
                                    options=expected_students_for_session, 
                                    default=loaded_report.get('ufm_roll_numbers', []),
                                    key="ufm_roll_numbers_multiselect"
                                )

                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("Save Report", key="save_cs_report"):
                                        # --- Validation Logic ---
                                        expected_set = set(expected_students_for_session)
                                        absent_set = set(absent_roll_numbers_selected)
                                        ufm_set = set(ufm_roll_numbers_selected)

                                        validation_errors = []

                                        # 1. All reported absent students must be in the expected list
                                        if not absent_set.issubset(expected_set):
                                            invalid_absent = list(absent_set.difference(expected_set))
                                            validation_errors.append(f"Error: Absent roll numbers {invalid_absent} are not in the expected student list for this session.")

                                        # 2. All reported UFM students must be in the expected list
                                        if not ufm_set.issubset(expected_set):
                                            invalid_ufm = list(ufm_set.difference(expected_set))
                                            validation_errors.append(f"Error: UFM roll numbers {invalid_ufm} are not in the expected student list for this session.")

                                        # 3. No student can be both absent and UFM
                                        if not absent_set.isdisjoint(ufm_set):
                                            overlap = list(absent_set.intersection(ufm_set))
                                            validation_errors.append(f"Error: Roll numbers {overlap} are marked as both Absent and UFM. A student cannot be both.")
                                        
                                        if validation_errors:
                                            for err in validation_errors:
                                                st.error(err)
                                        else:
                                            report_data = {
                                                'report_key': report_key, # Add report_key to data
                                                'date': report_date.strftime('%d-%m-%Y'),
                                                'shift': report_shift,
                                                'room_num': selected_room_num,
                                                'paper_code': selected_paper_code,
                                                'paper_name': selected_paper_name,
                                                'class': selected_class, # Added 'class' here
                                                'absent_roll_numbers': absent_roll_numbers_selected, # Store as list
                                                'ufm_roll_numbers': ufm_roll_numbers_selected # Store as list
                                            }
                                            success, message = save_cs_report_csv(report_key, report_data)
                                            if success:
                                                st.success(message)
                                            else:
                                                st.error(message)
                                            st.rerun() # Rerun to refresh the UI with saved data

                                st.markdown("---")
                                st.subheader("All Saved Reports (for debugging/review)")
                                
                                # Fetch all reports for the current CS user from CSV
                                all_reports_df_display = load_cs_reports_csv()
                                room_invigilators_df_display = load_room_invigilator_assignments()

                                if not all_reports_df_display.empty:
                                    # Merge with room invigilators for display
                                    if not room_invigilators_df_display.empty:
                                        all_reports_df_display = pd.merge(
                                            all_reports_df_display,
                                            room_invigilators_df_display[['date', 'shift', 'room_num', 'invigilators']],
                                            on=['date', 'shift', 'room_num'],
                                            how='left',
                                            suffixes=('', '_room_inv_display')
                                        )
                                        all_reports_df_display['invigilators'] = all_reports_df_display['invigilators'].apply(lambda x: x if isinstance(x, list) else [])
                                    else:
                                        all_reports_df_display['invigilators'] = [[]] * len(all_reports_df_display)

                                    # Reorder columns for better readability
                                    display_cols = [
                                        "date", "shift", "room_num", "paper_code", "paper_name", "class", 
                                        "invigilators", "absent_roll_numbers", "ufm_roll_numbers", "report_key"
                                    ]
                                    # Map internal keys to display keys
                                    df_all_reports_display = all_reports_df_display.rename(columns={
                                        'date': 'Date', 'shift': 'Shift', 'room_num': 'Room',
                                        'paper_code': 'Paper Code', 'paper_name': 'Paper Name', 'class': 'Class', 
                                        'invigilators': 'Invigilators',
                                        'absent_roll_numbers': 'Absent Roll Numbers',
                                        'ufm_roll_numbers': 'UFM Roll Numbers',
                                        'report_key': 'Report Key'
                                    })
                                    
                                    # Ensure all display_cols exist, fill missing with empty string
                                    for col in display_cols:
                                        if col not in df_all_reports_display.columns:
                                            df_all_reports_display[col] = ""
                                    
                                    st.dataframe(df_all_reports_display[
                                        ['Date', 'Shift', 'Room', 'Paper Code', 'Paper Name', 'Class', 
                                         'Invigilators', 'Absent Roll Numbers', 'UFM Roll Numbers', 'Report Key']
                                    ])
                                else:
                                    st.info("No reports saved yet.")

        elif cs_panel_option == "View Full Timetable": # New section for CS timetable view
            st.subheader("Full Examination Timetable")
            if timetable.empty:
                st.warning("Timetable data is missing. Please upload it via the Admin Panel.")
            else:
                st.dataframe(timetable)

        elif cs_panel_option == "Room Chart Report": # New Room Chart Report section for CS
            st.subheader("📄 Room Chart Report")
            st.info("Generate a detailed room chart showing student seating arrangements for a specific exam session.")

            if sitting_plan.empty or timetable.empty or assigned_seats_df.empty:
                st.warning("Please upload 'sitting_plan.csv', 'timetable.csv', and ensure seats are assigned via 'Assign Rooms & Seats to Students' (Admin Panel) to generate this report.")
                st.stop() # Use st.stop() to halt execution if critical data is missing
            
            # Date and Shift filters for the room chart
            chart_date_options = sorted(timetable["Date"].dropna().unique())
            chart_shift_options = sorted(timetable["Shift"].dropna().unique())

            if not chart_date_options or not chart_shift_options:
                st.info("No exam dates or shifts found in the timetable to generate a room chart.")
                st.stop() # Use st.stop() to halt execution if no options

            selected_chart_date = st.selectbox("Select Date", chart_date_options, key="cs_room_chart_date")
            selected_chart_shift = st.selectbox("Select Shift", chart_shift_options, key="cs_room_chart_shift")

            if st.button("Generate Room Chart"):
                with st.spinner("Generating room chart..."):
                    # The generate_room_chart_report function now returns a string message if there's an error
                    room_chart_output = generate_room_chart_report(selected_chart_date, selected_chart_shift, sitting_plan, assigned_seats_df, timetable)
                    
                    # Check if the output is an error message (string) or the actual chart data
                    if room_chart_output and "Error:" in room_chart_output:
                        st.error(room_chart_output) # Display the error message
                    elif room_chart_output:
                        st.text_area("Generated Room Chart", room_chart_output, height=600)
                        
                        # Download button
                        file_name = f"room_chart_{selected_chart_date}_{selected_chart_shift}.csv"
                        st.download_button(
                            label="Download Room Chart as CSV",
                            data=room_chart_output.encode('utf-8'),
                            file_name=file_name,
                            mime="text/csv",
                        )
                    else:
                        st.warning("Could not generate room chart. Please ensure data is complete and assignments are made.")

    else:
        st.warning("Enter valid Centre Superintendent credentials.")
