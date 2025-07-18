import streamlit as st
import pandas as pd

import os
if st.button("🔄 Clear Cache"):
    st.cache_data.clear()
    st.success("Cache cleared! Reload the app.")

@st.cache_data
def load_data():
    file_path = "exam room sitting.csv"
    ext = os.path.splitext(file_path)[1].lower()

@st.cache_data
def load_data():
    df = pd.read_csv("exam room sitting.csv")
    df.columns = df.columns.str.strip()
    
    roll_columns = [col for col in df.columns if col.startswith("Roll Number")]
    seat_columns = [col for col in df.columns if col.startswith("Seat Number")]
    
    # Strip and convert Roll Numbers to string
    for col in roll_columns:
        df[col] = df[col].astype(str).str.strip()
        
    df["Date"] = df["Date"].astype(str).str.strip()
    return df, roll_columns, seat_columns

# Load
df, roll_columns, seat_columns = load_data()

# UI
st.title("🧑‍🎓 Exam Info Web App")
st.write("Enter your **Roll Number** and **Exam Date** to get your exam details.")

roll = st.text_input("🔢 Roll Number")
date = st.text_input("📅 Exam Date (DD-MM-YYYY)")

if st.button("Get Exam Info"):
    found = False
    roll = roll.strip()

    for _, row in df.iterrows():
        if row["Date"] == date:
            for r_col, s_col in zip(roll_columns, seat_columns):
                if row[r_col] == roll:
                    st.success("✅ Exam Details Found!")
                    st.markdown(f"""
- 📅 **Date**: {row['Date']}
- 🧑‍🏫 **Class**: {row['Class']}
- 🏫 **Room Number**: {row['Room Number']}
- 🪑 **Seat Number**: {row[s_col]}
- 📘 **Paper**: {row['Paper']}
- 🕘 **Shift**: {row['Shift']}
                    """)
                    found = True
                    break
        if found:
            break

    if not found:
        st.error("❌ No exam details found for the given Roll Number and Date.")
