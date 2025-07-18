

import streamlit as st
import pandas as pd
import os

# Clear Cache Button
if st.button("🔄 Clear Cache"):
    st.cache_data.clear()
    st.success("✅ Cache cleared! Please reload the app.")

# Load Data
@st.cache_data
def load_data():
    df = pd.read_csv("exam room sitting.csv")
    df.columns = df.columns.str.strip()
    
    roll_columns = [col for col in df.columns if col.startswith("Roll Number")]
    seat_columns = [col for col in df.columns if col.startswith("Seat Number")]
    
    # Ensure roll numbers are strings and remove any ".0"
    for col in roll_columns:
        df[col] = df[col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        
    df["Date"] = df["Date"].astype(str).str.strip()
    return df, roll_columns, seat_columns
# Load
try:
    df, roll_columns, seat_columns = load_data()
except Exception as e:
    st.error(f"❌ Failed to load data: {e}")
    st.stop()

# UI
st.title("🧑‍🎓 Exam Info Web App")
st.write("Enter your **Roll Number** and **Exam Date** to get your exam details.")

roll = st.text_input("🔢 Roll Number").strip()
date = st.text_input("📅 Exam Date (DD-MM-YYYY)").strip()

# Action
if st.button("Get Exam Info"):
    if not roll or not date:
        st.warning("⚠️ Please enter both Roll Number and Date.")
    else:
        found = False
        for _, row in df.iterrows():
            if row["Date"] == date:
                for r_col, s_col in zip(roll_columns, seat_columns):
                    if row[r_col] == roll:
                        st.success("✅ Exam Details Found!")
                        room = str(row["Room Number"]).replace(".0", "") if pd.notnull(row["Room Number"]) else ""
                        seat = str(row[s_col]).replace(".0", "") if pd.notnull(row[s_col]) else ""
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
st.subheader("📄 Raw Data Preview")
st.dataframe(df)

