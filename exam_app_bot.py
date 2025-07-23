import streamlit as st
import pandas as pd
import datetime
import os
import io
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font
import json
import ast # Added for literal_eval to convert string representations of lists back to lists

# --- Configuration ---
CS_REPORTS_FILE = "cs_reports.csv"

# --- Firebase related code removed as per user request ---
# Initialize session state for Centre Superintendent reports if not already present
if 'cs_reports' not in st.session_state:
    st.session_state.cs_reports = {}

# Load data from CSV files (sitting_plan.csv, timetable.csv)
def load_data():
    # Check if files exist before attempting to read them
    if os.path.exists("sitting_plan.csv") and os.path.exists("timetable.csv"):
        try:
            # Read CSVs, ensuring string types for relevant columns to prevent type issues
            sitting_plan = pd.read_csv("sitting_plan.csv", dtype={
                f"Roll Number {i}": str for i in range(1, 11)
            })
            timetable = pd.read_csv("timetable.csv")
            return sitting_plan, timetable
        except Exception as e:
            st.error(f"Error loading CSV files: {e}")
            return pd.DataFrame(), pd.DataFrame()
    else:
        # Return empty DataFrames if files are not found
        return pd.DataFrame(), pd.DataFrame()

# Save uploaded files (for admin panel)
def save_uploaded_file(uploaded_file, filename):
    try:
        with open(filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        st.error(f"Error saving file {filename}: {e}")
        return False

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
                    # Use ast.literal_eval for safe conversion of stringified lists
                    df[col] = df[col].apply(lambda x: ast.literal_eval(x) if pd.notna(x) and x.strip() else [])
            return df
        except Exception as e:
            st.error(f"Error loading CS reports from CSV: {e}")
            # Ensure 'class' column is present in the empty DataFrame for consistency
            return pd.DataFrame(columns=['report_key', 'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'class', 'invigilators', 'absent_roll_numbers', 'ufm_roll_numbers'])
    else:
        # Ensure 'class' column is present in the empty DataFrame for consistency
        return pd.DataFrame(columns=['report_key', 'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'class', 'invigilators', 'absent_roll_numbers', 'ufm_roll_numbers'])

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
        # Find the index of the existing row
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
                # Removed the 'Shift' matching condition here as per user request
                matches_in_timetable = timetable[
                    (timetable["Paper"].str.strip() == paper) &
                    (timetable["Paper Code"].str.strip() == paper_code) &
                    (timetable["Paper Name"].str.strip() == paper_name) &
                    (timetable["Class"].str.strip().str.lower() == _class.lower())
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
                # Extract details from the current sitting plan row
                paper = str(sp_row["Paper"]).strip()
                paper_code = str(sp_row["Paper Code"]).strip()
                paper_name = str(sp_row["Paper Name"]).strip()
                _class = str(sp_row["Class"]).strip()

                # Find if this paper's date matches the search in the timetable
                # Removed the 'Shift' matching condition here as per user request
                matches_in_timetable = timetable[
                    (timetable["Class"].str.strip().str.lower() == _class.lower()) &
                    (timetable["Paper"].str.strip() == paper) &
                    (timetable["Paper Code"].str.strip() == paper_code) &
                    (timetable["Paper Name"].str.strip() == paper_name) &
                    (timetable["Date"].str.strip() == date_str) # Match against the provided date
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
                            "Room Number": sp_row["Room Number "], # Note: "Room Number " has a trailing space in CSV
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

# Function to generate the room chart data for Excel (Admin Panel)
def generate_room_chart(date_str, shift, room_number, sitting_plan, timetable):
    # Get all exams scheduled for the given date and shift
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if current_day_exams_tt.empty:
        return None, "No exams found in timetable for the given Date and Shift."

    # Extract time from the timetable. Assuming all exams in a given shift have the same time.
    exam_time = current_day_exams_tt.iloc[0]["Time"].strip() if "Time" in current_day_exams_tt.columns else "TBD"

    # Filter sitting plan for the specific room
    filtered_sp_by_room = sitting_plan[
        (sitting_plan["Room Number "].astype(str).str.strip() == str(room_number).strip())
    ]

    if filtered_sp_by_room.empty:
        return None, "No students found in sitting plan for the specified room. Check room number."

    student_entries_parsed = []
    # Iterate through students in the filtered sitting plan for the room
    for _, sp_row in filtered_sp_by_room.iterrows():
        # Extract paper and class details from this sitting plan row
        sp_paper = str(sp_row["Paper"]).strip()
        sp_paper_code = str(sp_row["Paper Code"]).strip()
        sp_paper_name = str(sp_row["Paper Name"]).strip()
        sp_class = str(sp_row["Class"]).strip()
        sp_mode = str(sp_row.get("Mode", "")).strip() # Get Mode
        sp_type = str(sp_row.get("Type", "")).strip() # Get Type

        # Check if this specific paper (from sitting plan) is scheduled for the selected date/shift
        is_exam_scheduled = current_day_exams_tt[
            (current_day_exams_tt["Class"].astype(str).str.strip().str.lower() == sp_class.lower()) &
            (current_day_exams_tt["Paper"].astype(str).str.strip() == sp_paper) &
            (current_day_exams_tt["Paper Code"].astype(str).str.strip() == sp_paper_code) &
            (current_day_exams_tt["Paper Name"].astype(str).str.strip() == sp_paper_name)
        ]

        if not is_exam_scheduled.empty:
            # If the paper is scheduled, then add all students from this sitting plan row
            for i in range(1, 11):
                roll_col = f"Roll Number {i}"
                s_col = f"Seat Number {i}" # Define s_col here

                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num_display = ""
                seat_num_sort_key = float('inf')

                if roll_num and roll_num != 'nan':
                    if s_col in sp_row.index: # Check if column exists
                        seat_num_raw = str(sp_row[s_col]).strip()
                        try:
                            seat_num_sort_key = int(float(seat_num_raw)) # Convert to float first to handle .0, then int
                            seat_num_display = str(int(float(seat_num_raw))) # Display as integer string
                        except ValueError:
                            seat_num_display = seat_num_raw if seat_num_raw else "N/A"
                    else:
                        seat_num_display = "N/A" # Column itself is missing
                    
                    student_entries_parsed.append({
                        "roll_num": roll_num,
                        "room_num": room_number,
                        "seat_num_display": seat_num_display, # This is what will be displayed/exported
                        "seat_num_sort_key": seat_num_sort_key, # This is for sorting
                        "paper_name": sp_paper_name,
                        "paper_code": sp_paper_code,
                        "class_name": sp_class,
                        "mode": sp_mode, # Add mode
                        "type": sp_type # Add type
                    })
    
    if not student_entries_parsed:
        return None, "No students found in the specified room for any exam on the selected date and shift."

    student_entries_parsed.sort(key=lambda x: x['seat_num_sort_key']) # Sort using the sort key

    # Prepare data for Excel output
    excel_output_data = []

    # --- Header Section ---
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107"])
    excel_output_data.append([f"Examination {datetime.datetime.now().year}"]) # More general
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["दिनांक :-", date_str])
    excel_output_data.append(["पाली :-", shift])
    excel_output_data.append([f"कक्ष :- {room_number} (Ground Floor)"])
    excel_output_data.append([f"समय :- {exam_time}"]) # Use extracted time
    excel_output_data.append([]) # Blank line

    # --- Answer Sheet Table Section (Dynamic counts for each paper) ---
    excel_output_data.append(["परीक्षा का नाम", "प्रश्न पत्र", "उत्तर पुस्तिकाएं", "", ""])
    excel_output_data.append(["", "", "प्राप्त", "प्रयुक्त", "शेष"])
    
    # Group students by Class, Paper, Paper Code, Paper Name, Mode, Type to get counts per paper
    paper_counts = {}
    for student in student_entries_parsed:
        key = (student['class_name'], student['paper_code'], student['paper_name'], student['mode'], student['type'])
        paper_counts[key] = paper_counts.get(key, 0) + 1

    total_students_in_room = 0
    for (class_name, paper_code, paper_name, mode, type_), count in paper_counts.items():
        excel_output_data.append([
            f"{class_name} - {mode} - {type_}", # Dynamic mode and type
            f"{paper_code} - {paper_name}",
            str(count), "", "" # Dynamic count for 'प्राप्त'
        ])
        total_students_in_room += count

    excel_output_data.append(["Total", "", str(total_students_in_room), "", ""]) # Dynamic total students in room

    excel_output_data.append([]) # Blank line
    excel_output_data.append([]) # Blank line
    excel_output_data.append([]) # Blank line

    excel_output_data.append(["अनुक्रमांक (कक्ष क्र. - सीट क्र.)"])
    excel_output_data.append([]) # Blank line

    # --- Student Data Section (mimicking PDF's 10-column layout) ---
    num_student_cols_pdf = 10 # 10 students per logical row in the PDF

    for i in range(0, len(student_entries_parsed), num_student_cols_pdf):
        current_block_students = student_entries_parsed[i : i + num_student_cols_pdf]
        
        roll_numbers_row = []
        details_row = []
        
        for k in range(num_student_cols_pdf):
            if k < len(current_block_students):
                entry = current_block_students[k]
                roll_numbers_row.append(str(entry['roll_num']))
                details_row.append(f"(कक्ष-{entry['room_num']}-सीट-{entry['seat_num_display']})-{entry['paper_name']}") # Use seat_num_display
            else:
                roll_numbers_row.append("")
                details_row.append("")

        excel_output_data.append(roll_numbers_row)
        excel_output_data.append(details_row)
        excel_output_data.append([""] * num_student_cols_pdf) # Blank row for spacing between student blocks

    # --- Footer Section ---
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["अनुपस्थित परीक्षार्थी"])
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["स. क्र.", "प्रश्न पत्र", "अनुपस्थित अनुक्रमांक", "कुल", "UFM अनुक्रमांक एवं अतिरिक्त", "कुल"])
    excel_output_data.append(["", "", "", "", "", ""]) # Placeholder row
    excel_output_data.append(["", "", "", "", "", ""]) # Placeholder row
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["पर्यवेक्षक का नाम"])
    excel_output_data.append(["हस्ताक्षर"])
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["पर्यवेक्षक का नाम"])
    excel_output_data.append(["हस्ताक्षर"])
    excel_output_data.append([]) # Blank line

    return excel_output_data, None

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

    # Determine the exam time for the header
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
            room_num = str(sp_row["Room Number "]).strip() # Note the space
            
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
                single_line_students.append(
                    f"{student['roll_num']}( कक्ष-{student['room_num']}-सीट-{student['seat_num_display']}){student['paper_name']}"
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
                # Each cell contains the full student string
                excel_row_for_students[k] = (
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']}){student['paper_name']}"
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
            room_num = str(sp_row["Room Number "]).strip()
            
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

# Function to display the Report Panel
def display_report_panel():
    st.subheader("📊 Exam Session Reports")

    sitting_plan, timetable = load_data()
    all_reports_df = load_cs_reports_csv()

    if all_reports_df.empty or sitting_plan.empty:
        st.info("No Centre Superintendent reports or sitting plan data available yet for statistics.")
        return

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
                'Room Number ': str(row['Room Number ']).strip(),
                'Class': str(row['Class']).strip().lower(),
                'Paper': str(row['Paper']).strip().lower(),
                'Paper Code': str(row['Paper Code']).strip().lower(),
                'Paper Name': str(row['Paper Name']).strip().lower(),
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

    # Standardize merge keys in expected_students_df (already done during creation, but ensuring consistency for safety)
    expected_students_df['Room Number '] = expected_students_df['Room Number '].astype(str).str.strip()
    expected_students_df['Paper Code'] = expected_students_df['Paper Code'].astype(str).str.strip().str.lower()
    expected_students_df['Paper Name'] = expected_students_df['Paper Name'].astype(str).str.strip().str.lower()
    expected_students_df['Class'] = expected_students_df['Class'].astype(str).str.strip().str.lower()


    # Merge all_reports_df with expected_students_df
    # We want to keep all report entries and add expected counts where available
    merged_reports_df = pd.merge(
        all_reports_df,
        expected_students_df,
        left_on=['room_num', 'paper_code', 'paper_name', 'class'],
        right_on=['Room Number ', 'Paper Code', 'Paper Name', 'Class'],
        how='left', # Use left merge to keep all reports
        suffixes=('_report', '_sp')
    )

    # Fill NaN expected_students_count with 0 for reports where no matching sitting plan entry was found
    merged_reports_df['expected_students_count'] = merged_reports_df['expected_students_count'].fillna(0).astype(int)

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
    unique_dates = sorted(all_reports_df['date'].unique())
    unique_shifts = sorted(all_reports_df['shift'].unique())
    unique_rooms = sorted(all_reports_df['room_num'].unique())
    unique_papers = sorted(all_reports_df['paper_name'].unique())

    filter_date = st.selectbox("Filter by Date", ["All"] + unique_dates, key="report_filter_date")
    filter_shift = st.selectbox("Filter by Shift", ["All"] + unique_shifts, key="report_filter_shift")
    filter_room = st.selectbox("Filter by Room Number", ["All"] + unique_rooms, key="report_filter_room")
    filter_paper = st.selectbox("Filter by Paper Name", ["All"] + unique_papers, key="report_filter_paper")

    filtered_reports_df = all_reports_df.copy()

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
            'date', 'shift', 'room_num', 'paper_code', 'paper_name', 'invigilators',
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
st.title("📘 Exam Room & Seat Finder")

menu = st.radio("Select Module", ["Student View", "Admin Panel", "Centre Superintendent Panel"])

if menu == "Student View":
    sitting_plan, timetable = load_data()

    # Check if dataframes are empty, indicating files were not loaded
    if sitting_plan.empty or timetable.empty:
        st.warning("Sitting plan or timetable data not found. Please upload them via the Admin Panel.")
    else:
        option = st.radio("Choose Search Option:", [
            "Search by Roll Number and Date",
            "Get Full Exam Schedule by Roll Number"
        ])

        if option == "Search by Roll Number and Date":
            roll = st.text_input("Enter Roll Number")
            date_input = st.date_input("Enter Exam Date", value=datetime.date.today())
            if st.button("Search"):
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
                schedule = pd.DataFrame(get_all_exams(roll, sitting_plan, timetable))
                if not schedule.empty:
                    schedule['Date_dt'] = pd.to_datetime(schedule['Date'], format='%d-%m-%Y', errors='coerce')
                    schedule = schedule.sort_values(by="Date_dt").drop(columns=['Date_dt'])
                    st.write(schedule)
                else:
                    st.warning("No exam records found for this roll number.")


elif menu == "Admin Panel":
    st.subheader("🔐 Admin Login")
    if admin_login():
        st.success("Login successful!")
        
        # Load data here, inside the successful login block
        sitting_plan, timetable = load_data()

        # File Upload Section
        st.subheader("📤 Upload Data Files")
        uploaded_sitting = st.file_uploader("Upload sitting_plan.csv", type=["csv"])
        if uploaded_sitting:
            if save_uploaded_file(uploaded_sitting, "sitting_plan.csv"):
                st.success("Sitting plan uploaded successfully.")
                sitting_plan, timetable = load_data() # Reload data after successful upload

        uploaded_timetable = st.file_uploader("Upload timetable.csv", type=["csv"])
        if uploaded_timetable:
            if save_uploaded_file(uploaded_timetable, "timetable.csv"):
                st.success("Timetable uploaded successfully.")
                sitting_plan, timetable = load_data() # Reload data after successful upload
        
        st.markdown("---") # Separator

        # Admin Panel Options
        admin_option = st.radio("Select Admin Task:", [
            "Generate Room Chart",
            "Get All Students for Date & Shift (Room Wise)", # Moved and renamed
            "Get All Students for Date & Shift (Roll Number Wise)", # New feature
            "Report Panel" # Added new option
        ])

        if sitting_plan.empty or timetable.empty:
            st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' to use these features.")
        else:
            if admin_option == "Generate Room Chart":
                st.subheader("📊 Generate Room Chart")
                
                # Input fields for chart generation
                chart_date_input = st.date_input("Select Exam Date for Chart", value=datetime.date.today())
                chart_shift_options = ["Morning", "Evening"]
                chart_shift = st.selectbox("Select Shift", chart_shift_options)
                
                all_room_numbers = sitting_plan['Room Number '].dropna().astype(str).str.strip().unique()
                selected_room_number_for_chart = st.selectbox("Select Room Number", [""] + sorted(all_room_numbers.tolist()))

                if st.button("Generate Chart"):
                    if not (selected_room_number_for_chart):
                        st.warning("Please select a Room Number to generate the chart.")
                    else:
                        chart_data_for_excel, error_message = generate_room_chart(
                            chart_date_input.strftime('%d-%m-%Y'),
                            chart_shift,
                            selected_room_number_for_chart,
                            sitting_plan,
                            timetable
                        )
                        if chart_data_for_excel:
                            st.success("Room Chart Generated!")
                            
                            # Display the chart data in Streamlit
                            start_display_idx = -1
                            for idx, row in enumerate(chart_data_for_excel):
                                if row and isinstance(row[0], str) and "अनुक्रमांक (कक्ष क्र. - सीट क्र.)" in row[0]:
                                    start_display_idx = idx
                                    break
                            
                            if start_display_idx != -1:
                                st.dataframe(pd.DataFrame(chart_data_for_excel[start_display_idx:]))
                            else:
                                st.dataframe(pd.DataFrame(chart_data_for_excel))


                            output = io.BytesIO()
                            workbook = Workbook()
                            sheet = workbook.active
                            sheet.title = "Room Chart"

                            for row_data in chart_data_for_excel:
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
                                    except:
                                        pass
                            adjusted_width = (max_length + 2)
                            sheet.column_dimensions[get_column_letter(col_idx + 1)].width = adjusted_width

                            workbook.save(output)
                            processed_data = output.getvalue()

                            file_name = (
                                f"room_chart_R{selected_room_number_for_chart}_"
                                f"{chart_date_input.strftime('%Y%m%d')}_"
                                f"{chart_shift.lower()}.xlsx"
                            )
                            st.download_button(
                                label="Download Room Chart as Excel",
                                data=processed_data,
                                file_name=file_name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.error(f"Failed to generate chart: {error_message}")
            
            elif admin_option == "Get All Students for Date & Shift (Room Wise)": # Moved module UI
                st.subheader("List All Students for a Date and Shift (Room Wise)")
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
                                    except:
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

            elif admin_option == "Get All Students for Date & Shift (Roll Number Wise)": # New feature UI
                st.subheader("List All Students for a Date and Shift (Roll Number Wise)")
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
                                    except:
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

            elif admin_option == "Report Panel": # New Report Panel option
                display_report_panel() # Call the new function to display reports

    else:
        st.warning("Enter valid admin credentials.")

elif menu == "Centre Superintendent Panel":
    st.subheader("🔐 Centre Superintendent Login")
    if cs_login():
        st.success("Login successful!")

        # Load data for CS panel
        sitting_plan, timetable = load_data()

        # No Firebase check needed here, as we are using CSV
        
        if sitting_plan.empty or timetable.empty:
            st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' via the Admin Panel to use this feature.")
        else:
            st.subheader("📝 Report Exam Session")

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
                available_exams_tt_temp['merge_key'] = available_exams_tt_temp['Class'].astype(str).str.strip().str.lower() + "_" + \
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
                    merged_data['exam_session_id'] = merged_data['Room Number '].astype(str).str.strip() + " - " + \
                                                      merged_data['Paper Code_tt'].astype(str).str.strip() + " (" + \
                                                      merged_data['Paper Name_tt'].astype(str).str.strip() + ")"
                    
                    unique_exam_sessions = merged_data[['Room Number ', 'Paper Code_tt', 'Paper Name_tt', 'exam_session_id']].drop_duplicates().sort_values(by='exam_session_id')
                    
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
                                (merged_data['Room Number '].astype(str).str.strip() == selected_room_num) &
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
                                (merged_data['Room Number '].astype(str).str.strip() == selected_room_num) &
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

                            invigilators_input = st.text_area(
                                "Invigilator Names (comma-separated)", 
                                value=loaded_report.get('invigilators', ""), 
                                key="invigilators_input"
                            )
                            
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
                                    
                                    # 4. Ensure all expected students are accounted for (present, absent, or UFM)
                                    # Students who are present and not UFM = expected - absent - ufm (from expected)
                                    accounted_for_set = absent_set.union(ufm_set)
                                    if len(accounted_for_set) > len(expected_set):
                                        validation_errors.append("Error: The total count of absent and UFM students exceeds the total expected students.")
                                    elif len(accounted_for_set) < len(expected_set):
                                        unaccounted_students = list(expected_set.difference(accounted_for_set))
                                        if len(unaccounted_students) > 0:
                                            # This means there are students who are expected but not reported as absent or UFM.
                                            # These are implicitly "present and clean". This is usually fine.
                                            # The user's request "total number of students become equal to present + absent + ufm case students"
                                            # is satisfied if all students are categorized.
                                            # If the intent is that *every single student* must be explicitly marked,
                                            # then this 'unaccounted_students' check would be an error.
                                            # Given the previous context, it's more about data integrity than explicit marking of every present student.
                                            # However, if the sum of reported categories (absent + ufm + implicit present) doesn't match expected, it's an error.
                                            # The current check ensures no over-reporting. The under-reporting (students not marked) is implied as "present and clean".
                                            # Let's add a check if the total sum of categories doesn't match the expected.
                                            # Total accounted for = (Expected - Absent - UFM) + Absent + UFM
                                            # This is implicitly handled by the set operations.
                                            # The most important part is that the sum of the *explicitly reported* categories (absent, UFM)
                                            # plus the *implicitly present and clean* students must equal the total expected.
                                            # The current logic for `total_present_students` and `total_answer_sheets_collected` in display_report_panel
                                            # already handles this correctly.
                                            # The specific validation here is to prevent inconsistent reporting.
                                            pass # No error for unaccounted students, they are implicitly present and clean.


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
                                            'invigilators': invigilators_input,
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
                            all_reports_df = load_cs_reports_csv()
                            
                            if not all_reports_df.empty:
                                # Reorder columns for better readability
                                display_cols = [
                                    "date", "shift", "room_num", "paper_code", "paper_name", "class", # Added 'class' here
                                    "invigilators", "absent_roll_numbers", "ufm_roll_numbers", "report_key"
                                ]
                                # Map internal keys to display keys
                                df_all_reports_display = all_reports_df.rename(columns={
                                    'date': 'Date', 'shift': 'Shift', 'room_num': 'Room',
                                    'paper_code': 'Paper Code', 'paper_name': 'Paper Name', 'class': 'Class', # Added 'class' here
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
                                    ['Date', 'Shift', 'Room', 'Paper Code', 'Paper Name', 'Class', # Added 'Class' here
                                     'Invigilators', 'Absent Roll Numbers', 'UFM Roll Numbers', 'Report Key']
                                ])
                            else:
                                st.info("No reports saved yet.")

    else:
        st.warning("Enter valid Centre Superintendent credentials.")
