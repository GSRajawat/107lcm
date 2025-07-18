

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
    file_path = "exam room sitting.csv"
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()

    # Extract roll and seat columns dynamically
    roll_columns = [col for col in df.columns if col.strip().startswith("Roll Number")]
    seat_columns = [col for col in df.columns if col.strip().startswith("Seat Number")]

    # Strip and convert data
    for col in roll_columns:
        df[col] = df[col].astype(str).str.strip()

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
                        st.markdown(f"""
- 📅 **Date**: {row['Date']}
- 🧑‍🏫 **Class**: {row.get('Class', 'N/A')}
- 🏫 **Room Number**: {row.get('Room Number', 'N/A')}
- 🪑 **Seat Number**: {row[s_col]}
- 📘 **Paper**: {row.get('Paper', 'N/A')}
- 🕘 **Shift**: {row.get('Shift', 'N/A')}
                        """)
                        found = True
                        break
            if found:
                break

        if not found:
            st.error("❌ No exam details found for the given Roll Number and Date.")
st.subheader("📄 Raw Data Preview")
st.dataframe(df)

