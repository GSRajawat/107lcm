import streamlit as st
import pandas as pd
import datetime
import os

# Load data
def load_data():
    # Check if files exist before attempting to read them
    if os.path.exists("sitting_plan.csv") and os.path.exists("timetable.csv"):
        try:
            sitting_plan = pd.read_csv("sitting_plan.csv")
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
                # Call the modified get_sitting_details which returns a list
                results = get_sitting_details(roll, date_input.strftime('%d-%m-%Y'), sitting_plan, timetable)
                if results:
                    st.success(f"Found {len(results)} exam(s) for Roll Number {roll} on {date_input.strftime('%d-%m-%Y')}:")
                    for i, result in enumerate(results):
                        st.markdown(f"---") # Separator for multiple results
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
                    # Convert 'Date' column to datetime objects for proper sorting
                    df['Date_dt'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')
                    df = df.sort_values(by="Date_dt").drop(columns=['Date_dt']) # Sort and then drop helper column
                    st.write(df)
                else:
                    st.warning("No exam records found for this roll number.")

elif menu == "Admin Panel":
    st.subheader("🔐 Admin Login")
    if admin_login():
        st.success("Login successful!")
        st.subheader("📤 Upload Sitting Plan")
        uploaded_sitting = st.file_uploader("Upload sitting_plan.csv", type=["csv"])
        if uploaded_sitting:
            if save_uploaded_file(uploaded_sitting, "sitting_plan.csv"):
                st.success("Sitting plan uploaded successfully.")

        st.subheader("📤 Upload Timetable")
        uploaded_timetable = st.file_uploader("Upload timetable.csv", type=["csv"])
        if uploaded_timetable:
            if save_uploaded_file(uploaded_timetable, "timetable.csv"):
                st.success("Timetable uploaded successfully.")
    else:
        st.warning("Enter valid admin credentials.")
