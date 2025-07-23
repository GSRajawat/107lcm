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
                matching_exam_tt = timetable[
                    (timetable["Class"].str.strip().str.lower() == _class.lower()) &
                    (timetable["Paper"].str.strip() == paper) &
                    (timetable["Paper Code"].str.strip() == paper_code) &
                    (timetable["Paper Name"].str.strip() == paper_name) &
                    (timetable["Date"].str.strip() == date_str) # Match against the provided date
                ]

                if not matching_exam_tt.empty:
                    # If there are multiple timetable entries for the same paper/class/date (e.g., different shifts),
                    # add all of them as separate sitting details.
                    for _, tt_row in matching_exam_tt.iterrows():
                        found_sittings.append({
                            "Room Number": sp_row["Room Number "], # Note: "Room Number " has a trailing space in CSV
                            "Seat Number": sp_row[s_col],
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

# New function to generate the room chart data for Excel
def generate_room_chart(date_str, shift, room_number, sitting_plan, timetable):
    # Get all exams scheduled for the given date and shift
    current_day_exams_tt = timetable[
        (timetable["Date"].astype(str).str.strip() == date_str) &
        (timetable["Shift"].astype(str).str.strip().str.lower() == shift.lower())
    ]

    if current_day_exams_tt.empty:
        return None, "No exams found in timetable for the given Date and Shift."

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
                seat_col = f"Seat Number {i}"

                roll_num = str(sp_row.get(roll_col, '')).strip()
                seat_num = str(sp_row.get(seat_col, '')).strip()

                if roll_num and roll_num != 'nan':
                    try:
                        seat_num_int = int(seat_num)
                    except ValueError:
                        seat_num_int = 999999
                    student_entries_parsed.append({
                        "roll_num": roll_num,
                        "room_num": room_number,
                        "seat_num": seat_num_int,
                        "paper_name": sp_paper_name,
                        "paper_code": sp_paper_code,
                        "class_name": sp_class,
                        "mode": sp_mode, # Add mode
                        "type": sp_type # Add type
                    })
    
    if not student_entries_parsed:
        return None, "No students found in the specified room for any exam on the selected date and shift."

    student_entries_parsed.sort(key=lambda x: x['seat_num'])

    # Prepare data for Excel output
    excel_output_data = []

    # --- Header Section ---
    excel_output_data.append(["जीवाजी विश्वविद्यालय ग्वालियर"])
    excel_output_data.append(["परीक्षा केंद्र :- शासकीय विधि महाविद्यालय, मुरैना (म. प्र.) कोड :- G107"])
    excel_output_data.append([f"Examination {datetime.datetime.now().year}"]) # More general
    excel_output_data.append([]) # Blank line
    excel_output_data.append(["दिनांक :-", date_str])
    excel_output_data.append(["पाली :-", shift])
    excel_output_data.append([f"कक्ष :- {room_number}"])
    excel_output_data.append([f"समय :- "]) # Placeholder
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
                details_row.append(f"(कक्ष-{entry['room_num']}-सीट-{entry['seat_num']})-{entry['paper_name']}")
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


# Main app
st.title("📘 Exam Room & Seat Finder")

menu = st.radio("Select Module", ["Student View", "Admin Panel"])

if menu == "Student View":
    sitting_plan, timetable = load_data()

    # Check if dataframes are empty, indicating files were not loaded
    if sitting_plan.empty or timetable.empty:
        st.warning("Sitting plan or timetable data not found. Please upload them via the Admin Panel.")
    else:
        option = st.radio("Choose Search Option:", ["Search by Roll Number and Date", "Get Full Exam Schedule by Roll Number"])

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
                        st.write(f"**Room Number:** {int(result['Room Number'])}")
                        st.write(f"**🪑 Seat Number:** {int(result['Seat Number'])}")
                        st.write(f"**📚 Paper:** {result['Paper']} - {result['Paper Name']} - ({result['Paper Code']})")
                        st.write(f"**🏫 Class:** {result['Class']}")
                        st.write(f"**🎓 Student type:** {result['Mode']} - {result['Type']}")
                        st.write(f"**🕐 Shift:** {result['Shift']}, **📅 Date:** {result['Date']}")
                else:
                    st.warning("No data found for the given inputs.")

        elif option == "Get Full Exam Schedule by Roll Number":
            roll = st.text_input("Enter Roll Number")
            if st.button("Get Schedule"):
                schedule = get_all_exams(roll, sitting_plan, timetable)
                if schedule:
                    df = pd.DataFrame(schedule)
                    df['Date_dt'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')
                    df = df.sort_values(by="Date_dt").drop(columns=['Date_dt'])
                    st.write(df)
                else:
                    st.warning("No exam records found for this roll number.")

elif menu == "Admin Panel":
    st.subheader("🔐 Admin Login")
    if admin_login():
        st.success("Login successful!")
        
        # File Upload Section
        st.subheader("📤 Upload Data Files")
        uploaded_sitting = st.file_uploader("Upload sitting_plan.csv", type=["csv"])
        if uploaded_sitting:
            if save_uploaded_file(uploaded_sitting, "sitting_plan.csv"):
                st.success("Sitting plan uploaded successfully.")

        uploaded_timetable = st.file_uploader("Upload timetable.csv", type=["csv"])
        if uploaded_timetable:
            if save_uploaded_file(uploaded_timetable, "timetable.csv"):
                st.success("Timetable uploaded successfully.")
        
        st.markdown("---") # Separator

        # Generate Room Chart Section
        st.subheader("📊 Generate Room Chart")
        sitting_plan, timetable = load_data() # Reload data to ensure latest uploads are used

        if sitting_plan.empty or timetable.empty:
            st.info("Please upload both 'sitting_plan.csv' and 'timetable.csv' to generate room charts.")
        else:
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
                        # Create a DataFrame from the list of lists for display
                        df_display = pd.DataFrame(chart_data_for_excel)
                        st.dataframe(df_display) # Use st.dataframe for interactive table display

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
    else:
        st.warning("Enter valid admin credentials.")

