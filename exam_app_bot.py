
import streamlit as st
import pandas as pd
import datetime
import os

# Load data
def load_data():
    if os.path.exists("sitting_plan.csv") and os.path.exists("timetable.csv"):
        sitting_plan = pd.read_csv("sitting_plan.csv")
        timetable = pd.read_csv("timetable.csv")
        return sitting_plan, timetable
    else:
        return pd.DataFrame(), pd.DataFrame()

# Save uploaded files
def save_uploaded_file(uploaded_file, filename):
    with open(filename, "wb") as f:
        f.write(uploaded_file.getbuffer())

# Admin login (simple hardcoded credentials)
def admin_login():
    user = st.text_input("Username", type="default")
    pwd = st.text_input("Password", type="password")
    return user == "admin" and pwd == "admin123"  # You can change this

# Existing student functions (unchanged) ...
# [Add your `get_sitting_details()` and `get_all_exams()` functions here as before]

# Get all exams for a roll number
def get_all_exams(roll_number, sitting_plan, timetable):
    student_exams = []
    for _, row in sitting_plan.iterrows():
        for i in range(1, 11):
            r_col = f"Roll Number {i}"

            if str(row[r_col]).strip() == str(roll_number).strip():
                paper = row["Paper"]
                paper_code = row["Paper Code"]
                paper_name = row["Paper Name"]
                _class = row["Class"]

                matches = timetable[
                    (timetable["Paper"] == paper) &
                    (timetable["Paper Code"] == paper_code) &
                    (timetable["Paper Name"] == paper_name) &
                    (timetable["Class"].str.strip().str.lower() == _class.strip().lower())
                ]

                for _, match in matches.iterrows():
                    student_exams.append({
                        "Date": match["Date"],
                        "Shift": match["Shift"],
                        "Class": _class,
                        "Paper": paper,
                        "Paper Code": paper_code,
                        "Paper Name": paper_name
                    })
    return student_exams



def get_sitting_details(roll_number, date, sitting_plan, timetable):
    for _, row in sitting_plan.iterrows():
        for i in range(1, 11):
            r_col = f"Roll Number {i}"
            s_col = f"Seat Number {i}"

            if str(row[r_col]).strip() == str(roll_number).strip():
                paper = str(row["Paper"]).strip()
                paper_code = str(row["Paper Code"]).strip()
                paper_name = str(row["Paper Name"]).strip()
                _class = str(row["Class"]).strip()

                # Find if this paper's date matches the search
                matching_exam = timetable[
                    (timetable["Class"].str.strip().str.lower() == _class.lower()) &
                    (timetable["Paper"].str.strip() == paper) &
                    (timetable["Paper Code"].str.strip() == paper_code) &
                    (timetable["Paper Name"].str.strip() == paper_name) &
                    (timetable["Date"].str.strip() == date)
                ]

                if not matching_exam.empty:
                    tt_row = matching_exam.iloc[0]
                    return {
                        "Room Number": row["Room Number "],
                        "Seat Number": row[s_col],
                        "Class": _class,
                        "Paper": paper,
                        "Paper Code": paper_code,
                        "Paper Name": paper_name,
                        "Date": tt_row["Date"],
                        "Shift": tt_row["Shift"],
                        "Mode": row.get("Mode", ""),
                        "Type": row.get("Type", "")
                    }
    return None



# Main app
st.title("📘 Exam Room & Seat Finder")

menu = st.radio("Select Module", ["Student View", "Admin Panel"])

if menu == "Student View":
    sitting_plan, timetable = load_data()

    option = st.radio("Choose Search Option:", ["Search by Roll Number and Date", "Get Full Exam Schedule by Roll Number"])

    if option == "Search by Roll Number and Date":
        roll = st.text_input("Enter Roll Number")
        date_input = st.date_input("Enter Exam Date", value=datetime.date.today())
        if st.button("Search"):
            result = get_sitting_details(roll, date_input.strftime('%d-%m-%Y'), sitting_plan, timetable)
            if result:
                st.success(f"Room Number: {int(result['Room Number'])}")
                st.info(f"🪑 Seat Number: {int(result['Seat Number'])}")
                st.write(f"📚 Paper: {result['Paper']} - {result['Paper Name']} - ({result['Paper Code']})")
                st.write(f"🏫 Class: {result['Class']}")
                st.write(f"🎓 Student type: {result['Mode']} - {result['Type']}")
                st.write(f"🕐 Shift: {result['Shift']}, 📅 Date: {result['Date']}")
            else:
                st.warning("No data found for the given inputs.")

    elif option == "Get Full Exam Schedule by Roll Number":
        roll = st.text_input("Enter Roll Number")
        if st.button("Get Schedule"):
            schedule = get_all_exams(roll, sitting_plan, timetable)
            if schedule:
                df = pd.DataFrame(schedule)
                df = df.sort_values(by="Date")
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
            save_uploaded_file(uploaded_sitting, "sitting_plan.csv")
            st.success("Sitting plan uploaded successfully.")

        st.subheader("📤 Upload Timetable")
        uploaded_timetable = st.file_uploader("Upload timetable.csv", type=["csv"])
        if uploaded_timetable:
            save_uploaded_file(uploaded_timetable, "timetable.csv")
            st.success("Timetable uploaded successfully.")
    else:
        st.warning("Enter valid admin credentials.")
