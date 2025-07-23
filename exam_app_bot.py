import streamlit as st
import pandas as pd
import datetime
import os
import io
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font

# Load data
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

# Save uploaded files
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

# Get all exams for a roll number
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
                # Use .str.strip() and .str.lower() for robust matching
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

# Get sitting details for a specific roll number and date
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
                # Use .str.strip() and .str.lower() for robust matching
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

# Function to generate the room chart data for Excel
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

# Function to get all students for a given date and shift in the requested text format
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
    output_string_parts.append("परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107")
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
        output_string_parts.append(f"कक्ष :-{room_num}")
        current_room_students = students_by_room[room_num]
        
        num_cols = 10 
        
        for i in range(0, len(current_room_students), num_cols):
            block_students = current_room_students[i : i + num_cols]
            
            # Create a single line for 10 students
            single_line_students = []
            for student in block_students:
                single_line_students.append(
                    f"{student['roll_num']}(कक्ष-{student['room_num']}-सीट-{student['seat_num_display']}){student['paper_name']}"
                )
            
            output_string_parts.append("".join(single_line_students)) # Join directly without spaces

    final_text_output = "\n".join(output_string_parts)

    # --- Prepare Excel output data ---
    excel_output_data = []

    # Excel Header
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107"])
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

# New function to get all students for a given date and shift, sorted by roll number
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
    output_string_parts.append("परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107")
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
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107"])
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


# Main app
st.title("📘 Exam Room & Seat Finder")

menu = st.radio("Select Module", ["Student View", "Admin Panel"])

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
            "Get All Students for Date & Shift (Roll Number Wise)" # New feature
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

    else:
        st.warning("Enter valid admin credentials.")
