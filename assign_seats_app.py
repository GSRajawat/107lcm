import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="centered", page_title="Room & Seat Assignment Tool")
st.title("📘 Room & Seat Assignment Tool")
st.markdown("""
This tool helps manage seat assignments for exams, offering real-time status updates,
capacity warnings, and clear error messages based on your selected seat format.
""")

# --- File Paths ---
sitting_file = "sitting_plan.csv"
timetable_file = "timetable.csv"
assigned_file = "assigned_seats.csv"

# --- Load Data ---
# Check if sitting_plan.csv exists
if os.path.exists(sitting_file):
    sitting_df = pd.read_csv(sitting_file)
else:
    st.error(f"Error: `{sitting_file}` not found. Please upload this file to run the application.")
    st.stop() # Stop execution if critical file is missing

# Check if timetable.csv exists
if os.path.exists(timetable_file):
    timetable_df = pd.read_csv(timetable_file)
else:
    st.error(f"Error: `{timetable_file}` not found. Please upload this file to run the application.")
    st.stop() # Stop execution if critical file is missing

# Load or initialize assigned_seats.csv
if os.path.exists(assigned_file):
    # Ensure Room Number is read as string to prevent type mismatch issues
    assigned_df = pd.read_csv(assigned_file, dtype={"Roll Number": str, "Room Number": str})
else:
    assigned_df = pd.DataFrame(columns=["Roll Number", "Paper Code", "Paper Name", "Room Number", "Seat Number", "Date", "Shift"])
    st.info(f"Note: `{assigned_file}` not found. A new empty file will be created upon first assignment.")

st.markdown("---")

# --- Session State for consistent UI updates (optional, for more complex state) ---
if 'current_room_status_a_rem' not in st.session_state:
    st.session_state.current_room_status_a_rem = None
if 'current_room_status_b_rem' not in st.session_state:
    st.session_state.current_room_status_b_rem = None
if 'current_room_status_total_rem' not in st.session_state:
    st.session_state.current_room_status_total_rem = None


# --- Input Widgets ---
st.subheader("Exam Details")
date = st.selectbox("Select Exam Date", sorted(timetable_df["Date"].dropna().unique()))
shift = st.selectbox("Select Shift", sorted(timetable_df["Shift"].dropna().unique()))

# Filter relevant papers based on selected date and shift
filtered_papers = timetable_df[(timetable_df["Date"] == date) & (timetable_df["Shift"] == shift)]
paper_options = filtered_papers[["Paper Code", "Paper Name"]].drop_duplicates().values.tolist()
paper_display = [f"{code} - {name}" for code, name in paper_options]

selected_paper = st.selectbox("Select Paper Code and Name", paper_display)

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
    # This block ensures real-time status is always visible based on current inputs
    if room:
        # Get all assigned seats for the current room, date, and shift
        room_assigned_seats_current = assigned_df[
            (assigned_df["Room Number"] == room) &
            (assigned_df["Date"] == date) &
            (assigned_df["Shift"] == shift)
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

        # Extract roll numbers for the selected paper from sitting_df
        roll_cols = [col for col in sitting_df.columns if col.lower().startswith("roll number")]
        paper_rows = sitting_df[sitting_df["Paper Code"] == int(paper_code)]
        all_rolls = paper_rows[roll_cols].values.flatten()
        all_rolls = [str(r).strip() for r in all_rolls if str(r).strip() and str(r).lower() != 'nan']

        # Remove previously assigned roll numbers for this paper/date/shift
        already_assigned_rolls = assigned_df[
            (assigned_df["Paper Code"] == int(paper_code)) &
            (assigned_df["Date"] == date) &
            (assigned_df["Shift"] == shift)
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

        # --- MODIFICATION START ---
        # Get a set of all *physically occupied seat keys* for the current room, date, and shift
        # This set will contain tuples like ('1', '1A', '30-07-2025', 'Evening') for ALL occupied seats,
        # regardless of which paper they were assigned to.
        # Ensure all components of the tuple are strings for consistent hashing and comparison.
        occupied_physical_seat_keys = set(
            (str(x[0]), str(x[1]), str(x[2]), str(x[3]))
            for x in assigned_df[
                (assigned_df["Room Number"] == room) &
                (assigned_df["Date"] == date) &
                (assigned_df["Shift"] == shift)
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
        # --- MODIFICATION END ---

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

        # This `occupied_physical_seat_keys` is now correctly populated at the beginning of the button click
        # and used to prevent adding conflicting assignments.
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
            st.stop()

        # Merge new assignments with existing ones and save
        # The `occupied_physical_seat_keys` check above ensures no physical seat duplicates are added.
        # We now simply concatenate.
        assigned_df = pd.concat([assigned_df, new_assignments_df], ignore_index=True)
        # Re-add drop_duplicates on Roll Number/Paper Code/Date/Shift to prevent a student
        # from being assigned the *same paper* multiple times if the button is clicked repeatedly.
        assigned_df.drop_duplicates(subset=["Roll Number", "Paper Code", "Date", "Shift"], inplace=True)
        assigned_df.to_csv(assigned_file, index=False)

        st.success(f"✅ Successfully assigned **{len(new_assignments_df)}** students to Room **{room}** using **{seat_format}** format.")
        st.dataframe(new_assignments_df) # Display only the newly assigned students

        # --- Display Updated Room Status AFTER assignment ---
        st.subheader("📊 Updated Room Status")
        updated_room_assigned_seats = assigned_df[
            (assigned_df["Room Number"] == room) &
            (assigned_df["Date"] == date) &
            (assigned_df["Shift"] == shift)
        ]["Seat Number"].tolist()

        updated_a_seats_used = len([s for s in updated_room_assigned_seats if s.endswith("A")])
        updated_b_seats_used = len([s for s in updated_room_assigned_seats if s.endswith("B")])
        no_suffix_seats_used = len([s for s in updated_room_assigned_seats if not s.endswith("A") and not s.endswith("B")])

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

    st.markdown("---")

    # --- Display all assignments for the selected room/date/shift ---
    if room:
        with st.expander(f"📄 View all current assignments for Room {room} on {date} ({shift})"):
            room_assignments_display = assigned_df[
                (assigned_df["Room Number"] == room) &
                (assigned_df["Date"] == date) &
                (assigned_df["Shift"] == shift)
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
    if os.path.exists(assigned_file):
        os.remove(assigned_file)
        st.success("`assigned_seats.csv` has been deleted. All assignments reset.")
    else:
        st.info("No `assigned_seats.csv` found to reset.")
    st.experimental_rerun() # Rerun the app to reflect the changes
