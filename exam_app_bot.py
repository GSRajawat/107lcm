# --- Updated Remuneration Calculation Functions (from bill.py) ---
def calculate_remuneration(shift_assignments_df, room_invigilator_assignments_df, timetable_df, assigned_seats_df,
                            manual_rates, prep_closing_assignments, holiday_dates, selected_classes_for_bill):
    """
    Calculates the remuneration for all team members based on assignments and rules,
    including individually selected preparation and closing days and holiday conveyance allowance.
    
    Updated Rules:
    1. Person gets conveyance in evening shift of selected exam (if also worked in evening shift of selected/non-selected exam)
    2. Person doesn't get conveyance in morning shift of selected exam (if also worked in evening shift of selected/non-selected exam)
    3. Senior CS gets daily remuneration if worked in either shift of selected exam in bill of selected exam
    4. Senior CS doesn't get daily remuneration if worked in morning shift of selected exam and evening shift of non-selected exam in bill of selected exam
    5. Senior CS gets daily remuneration if worked in both shifts of selected exam in bill of selected exam
    """
    remuneration_data_detailed_raw = []
    
    # Define remuneration rules and their base rates
    remuneration_rules = {
        'senior_center_superintendent': {'role_display': 'Senior Center Superintendent', 'rate': manual_rates['senior_center_superintendent_rate'], 'unit': 'day', 'eligible_prep_close': True, 'exam_conveyance': False},
        'center_superintendent': {'role_display': 'Center Superintendent', 'rate': manual_rates['center_superintendent_rate'], 'unit': 'shift', 'eligible_prep_close': True, 'exam_conveyance': True},
        'assistant_center_superintendent': {'role_display': 'Assistant Center Superintendent', 'rate': manual_rates['assistant_center_superintendent_rate'], 'unit': 'shift', 'eligible_prep_close': True, 'exam_conveyance': True},
        'permanent_invigilator': {'role_display': 'Permanent Invigilator', 'rate': manual_rates['permanent_invigilator_rate'], 'unit': 'shift', 'eligible_prep_close': True, 'exam_conveyance': True},
        'assistant_permanent_invigilator': {'role_display': 'Assistant Permanent Invigilator', 'rate': manual_rates['assistant_permanent_invigilator_rate'], 'unit': 'shift', 'eligible_prep_close': False, 'exam_conveyance': True},
        'invigilator': {'role_display': 'Invigilator', 'rate': manual_rates['invigilator_rate'], 'unit': 'shift', 'eligible_prep_close': False, 'exam_conveyance': True},
    }

    # Define rates for Class 3 and 4 workers (per student, applied to total students)
    class_worker_rates = {
        'class_3_worker': {'role_display': 'Class 3 Worker', 'rate_per_student': manual_rates['class_3_worker_rate_per_student']},
        'class_4_worker': {'role_display': 'Class 4 Worker', 'rate_per_student': manual_rates['class_4_worker_rate_per_student']},
    }

    # Create a unified list of all assigned personnel and their roles for easier iteration
    unified_assignments = []

    # Collect unique Class 3 and Class 4 workers for overall remuneration calculation
    unique_class_3_workers = set()
    unique_class_4_workers = set()

    # Process shift assignments (all shifts, for conveyance and Senior CS daily rate)
    for index, row in shift_assignments_df.iterrows():
        current_date = row['date']
        current_shift = row['shift']

        for role_col in remuneration_rules.keys():
            if role_col in row and isinstance(row[role_col], list):
                for person in row[role_col]:
                    unified_assignments.append({
                        'Name': person,
                        'Role_Key': role_col,
                        'Date': current_date,
                        'Shift': current_shift,
                        'Source': 'shift_assignments'
                    })
        
        # Collect unique Class 3 and 4 workers
        if 'class_3_worker' in row and isinstance(row['class_3_worker'], list):
            unique_class_3_workers.update(row['class_3_worker'])
        if 'class_4_worker' in row and isinstance(row['class_4_worker'], list):
            unique_class_4_workers.update(row['class_4_worker'])

    # Process room invigilator assignments (all shifts, for conveyance)
    for index, row in room_invigilator_assignments_df.iterrows():
        current_date = row['date']
        current_shift = row['shift']
        invigilators_list = row['invigilators']

        for invigilator in invigilators_list:
            is_assigned_higher_role = False
            for assignment in unified_assignments:
                if (assignment['Name'] == invigilator and
                    assignment['Date'] == current_date and
                    assignment['Shift'] == current_shift and
                    assignment['Role_Key'] != 'invigilator'):
                    is_assigned_higher_role = True
                    break
            
            if not is_assigned_higher_role:
                unified_assignments.append({
                    'Name': invigilator,
                    'Role_Key': 'invigilator',
                    'Date': current_date,
                    'Shift': current_shift,
                    'Source': 'room_invigilator_assignments'
                })

    # Convert to DataFrame for easier processing
    df_assignments = pd.DataFrame(unified_assignments)
    
    # Create mapping from (Date, Shift) to Classes for exam classification
    session_classes_map = {}
    for _, tt_row in timetable_df.iterrows():
        date_shift_key = (str(tt_row['Date']), str(tt_row['Shift']))
        if date_shift_key not in session_classes_map:
            session_classes_map[date_shift_key] = set()
        session_classes_map[date_shift_key].add(str(tt_row['Class']).strip())

    # NEW CONVEYANCE LOGIC: Check if person worked evening shift of any exam (selected or non-selected)
    evening_shift_workers = {}
    if not df_assignments.empty:
        df_assignments['Date_dt'] = pd.to_datetime(df_assignments['Date'], format='%d-%m-%Y', errors='coerce')
        evening_workers = df_assignments[df_assignments['Shift'] == 'Evening']
        for _, row in evening_workers.iterrows():
            name = row['Name']
            if name not in evening_shift_workers:
                evening_shift_workers[name] = set()
            evening_shift_workers[name].add((row['Date'], row['Role_Key']))

    # Now calculate remuneration for all entries in unified_assignments
    for assignment in unified_assignments:
        name = assignment['Name']
        role_key = assignment['Role_Key']
        date = assignment['Date']
        shift = assignment['Shift']

        # Get classes for this session
        session_classes = list(session_classes_map.get((date, shift), set()))
        is_selected_exam = any(cls in selected_classes_for_bill for cls in [c.strip() for c in session_classes]) if selected_classes_for_bill else True

        # Base remuneration for the shift
        base_rem_for_shift = remuneration_rules[role_key]['rate']
        
        # NEW CONVEYANCE LOGIC IMPLEMENTATION
        conveyance = 0
        if remuneration_rules[role_key]['exam_conveyance']:
            # Rule 1: Person gets conveyance in evening shift of selected exam (if also worked in evening shift)
            if shift == 'Evening' and is_selected_exam and name in evening_shift_workers:
                conveyance = manual_rates['conveyance_rate']
            
            # Rule 2: Person doesn't get conveyance in morning shift of selected exam (if also worked in evening shift)
            elif shift == 'Morning' and is_selected_exam and name in evening_shift_workers:
                conveyance = 0
            
            # Default conveyance for other cases (non-selected exams, etc.)
            elif shift == 'Evening' and not name in evening_shift_workers:
                conveyance = manual_rates['conveyance_rate']

        remuneration_data_detailed_raw.append({
            'Name': name,
            'Role_Key': role_key,
            'Role_Display': remuneration_rules[role_key]['role_display'],
            'Date': date,
            'Shift': shift,
            'Base_Remuneration_Per_Shift_Unfiltered': base_rem_for_shift,
            'Conveyance': conveyance,
            'Is_Selected_Exam': is_selected_exam,
            'Classes_in_Session': session_classes,
        })
    
    df_detailed_remuneration = pd.DataFrame(remuneration_data_detailed_raw)

    # --- Generate Individual Bills ---
    individual_bills = []
    unique_person_roles = df_detailed_remuneration[['Name', 'Role_Display', 'Role_Key']].drop_duplicates()

    for idx, row in unique_person_roles.iterrows():
        name = row['Name']
        role_display = row['Role_Display']
        role_key = row['Role_Key']

        person_data = df_detailed_remuneration[
            (df_detailed_remuneration['Name'] == name) &
            (df_detailed_remuneration['Role_Display'] == role_display)
        ].copy()
        
        # UPDATED SENIOR CS REMUNERATION LOGIC
        if role_key == 'senior_center_superintendent':
            # Get person's work pattern
            selected_shifts = person_data[person_data['Is_Selected_Exam'] == True]
            non_selected_shifts = person_data[person_data['Is_Selected_Exam'] == False]
            
            # Group by date to check daily patterns
            selected_dates = {}
            non_selected_dates = {}
            
            for _, shift_row in selected_shifts.iterrows():
                date = shift_row['Date']
                if date not in selected_dates:
                    selected_dates[date] = []
                selected_dates[date].append(shift_row['Shift'])
            
            for _, shift_row in non_selected_shifts.iterrows():
                date = shift_row['Date']
                if date not in non_selected_dates:
                    non_selected_dates[date] = []
                non_selected_dates[date].append(shift_row['Shift'])
            
            # Apply Senior CS rules
            eligible_days = set()
            
            for date, shifts in selected_dates.items():
                # Rule 3: Gets daily remuneration if worked in either shift of selected exam
                # Rule 5: Gets daily remuneration if worked in both shifts of selected exam
                if 'Morning' in shifts or 'Evening' in shifts:
                    eligible_days.add(date)
            
            # Rule 4: Remove days where worked morning shift of selected exam and evening shift of non-selected exam
            for date in list(eligible_days):
                if (date in selected_dates and 'Morning' in selected_dates[date] and
                    date in non_selected_dates and 'Evening' in non_selected_dates[date] and
                    date not in selected_dates or 'Evening' not in selected_dates.get(date, [])):
                    eligible_days.remove(date)
            
            filtered_person_data = person_data[person_data['Date'].isin(eligible_days)]
        else:
            # Filter other roles by selected classes for duties on exam days
            if selected_classes_for_bill:
                filtered_person_data = person_data[person_data['Is_Selected_Exam'] == True].copy()
            else:
                filtered_person_data = person_data.copy()

        # Group dates by month for display for morning shifts (filtered data)
        duty_dates_morning_str = ""
        morning_shifts_df = filtered_person_data[filtered_person_data['Shift'] == 'Morning']
        if not morning_shifts_df.empty:
            morning_shifts_df['Date_dt'] = pd.to_datetime(morning_shifts_df['Date'], format='%d-%m-%Y', errors='coerce')
            morning_shifts_df = morning_shifts_df.sort_values(by='Date_dt')
            grouped_dates_morning = morning_shifts_df.groupby(morning_shifts_df['Date_dt'].dt.to_period('M'))['Date_dt'].apply(lambda x: sorted(x.dt.day.tolist()))
            date_parts = []
            for period, days in grouped_dates_morning.items():
                month_name = period.strftime('%b')
                days_str = ", ".join(map(str, days))
                date_parts.append(f"{month_name} - {days_str}")
            if date_parts:
                duty_dates_morning_str = ", ".join(date_parts) + f" {morning_shifts_df['Date_dt'].min().year}"

        # Group dates by month for display for evening shifts (filtered data)
        duty_dates_evening_str = ""
        evening_shifts_df = filtered_person_data[filtered_person_data['Shift'] == 'Evening']
        if not evening_shifts_df.empty:
            evening_shifts_df['Date_dt'] = pd.to_datetime(evening_shifts_df['Date'], format='%d-%m-%Y', errors='coerce')
            evening_shifts_df = evening_shifts_df.sort_values(by='Date_dt')
            grouped_dates_evening = evening_shifts_df.groupby(evening_shifts_df['Date_dt'].dt.to_period('M'))['Date_dt'].apply(lambda x: sorted(x.dt.day.tolist()))
            date_parts = []
            for period, days in grouped_dates_evening.items():
                month_name = period.strftime('%b')
                days_str = ", ".join(map(str, days))
                date_parts.append(f"{month_name} - {days_str}")
            if date_parts:
                duty_dates_evening_str = ", ".join(date_parts) + f" {evening_shifts_df['Date_dt'].min().year}"

        total_morning_shifts = len(morning_shifts_df)
        total_evening_shifts = len(evening_shifts_df)
        total_shifts = total_morning_shifts + total_evening_shifts
        rate_in_rs = remuneration_rules[role_key]['rate'] if role_key in remuneration_rules else 0

        # Calculate base remuneration
        total_base_remuneration = 0
        if role_key == 'senior_center_superintendent':
            # Senior CS: Rs. per day based on eligible days
            unique_dates = filtered_person_data['Date'].nunique()
            total_base_remuneration = unique_dates * rate_in_rs
        else:
            # Other roles (per shift): Filter base remuneration by selected classes
            total_base_remuneration = filtered_person_data['Base_Remuneration_Per_Shift_Unfiltered'].sum()
        
        # Conveyance is calculated based on all shifts (not filtered by selected classes)
        total_conveyance = person_data['Conveyance'].sum() 
        
        # Calculate preparation and closing day remuneration - ROLE SPECIFIC
        total_prep_remuneration = 0
        total_closing_remuneration = 0
        total_holiday_conveyance = 0
        
        # Check if this person is eligible and assigned prep/closing days for THIS SPECIFIC ROLE
        if remuneration_rules[role_key]['eligible_prep_close']:
            person_assignments = prep_closing_assignments.get(name, {})
            assigned_role = person_assignments.get('role')
            
            # Only apply prep/closing if the assignment matches current role
            if assigned_role == role_key:
                # Preparation days
                prep_days = person_assignments.get('prep_days', [])
                total_prep_remuneration = len(prep_days) * rate_in_rs
                
                # Closing days
                closing_days = person_assignments.get('closing_days', [])
                total_closing_remuneration = len(closing_days) * rate_in_rs
                
                # Holiday conveyance for prep/closing days that are holidays
                all_assigned_days = prep_days + closing_days
                holiday_assigned_days = [day for day in all_assigned_days if day in holiday_dates]
                total_holiday_conveyance = len(holiday_assigned_days) * manual_rates['holiday_conveyance_allowance_rate']

        grand_total_amount = total_base_remuneration + total_conveyance + total_prep_remuneration + total_closing_remuneration + total_holiday_conveyance

        individual_bills.append({
            'SN': len(individual_bills) + 1,
            'Name (with role)': f"{name} ({role_display})",
            'Duty dates of selected class exam Shift (morning)': duty_dates_morning_str,
            'Duty dates of selected class exam Shift (evening)': duty_dates_evening_str,
            'Total shifts of selected class exams (morning/evening)': total_shifts,
            'Rate in Rs': rate_in_rs,
            'Total Remuneration in Rs': total_base_remuneration,
            'Total Conveyance (in evening shift)': total_conveyance,
            'Preparation Day Remuneration': total_prep_remuneration,
            'Closing Day Remuneration': total_closing_remuneration,
            'Total Holiday Conveyance Added': total_holiday_conveyance,
            'Total amount in Rs': grand_total_amount,
            'Signature': ''
        })

    df_individual_bills = pd.DataFrame(individual_bills)

    # --- Generate Role-wise Summary Matrix ---
    role_summary_matrix = []
    
    for role_key, rule in remuneration_rules.items():
        role_df = df_detailed_remuneration[df_detailed_remuneration['Role_Key'] == role_key]
        
        if not role_df.empty:
            total_shifts_count = len(role_df)
            
            # UPDATED REMUNERATION CALCULATION FOR SUMMARY
            total_base_rem = 0
            if role_key == 'senior_center_superintendent':
                # Senior CS: Apply the same logic as individual bills
                for name in role_df['Name'].unique():
                    person_data = role_df[role_df['Name'] == name]
                    
                    # Apply Senior CS rules for this person
                    selected_shifts = person_data[person_data['Is_Selected_Exam'] == True]
                    non_selected_shifts = person_data[person_data['Is_Selected_Exam'] == False]
                    
                    selected_dates = {}
                    non_selected_dates = {}
                    
                    for _, shift_row in selected_shifts.iterrows():
                        date = shift_row['Date']
                        if date not in selected_dates:
                            selected_dates[date] = []
                        selected_dates[date].append(shift_row['Shift'])
                    
                    for _, shift_row in non_selected_shifts.iterrows():
                        date = shift_row['Date']
                        if date not in non_selected_dates:
                            non_selected_dates[date] = []
                        non_selected_dates[date].append(shift_row['Shift'])
                    
                    eligible_days = set()
                    
                    for date, shifts in selected_dates.items():
                        if 'Morning' in shifts or 'Evening' in shifts:
                            eligible_days.add(date)
                    
                    for date in list(eligible_days):
                        if (date in selected_dates and 'Morning' in selected_dates[date] and
                            date in non_selected_dates and 'Evening' in non_selected_dates[date] and
                            (date not in selected_dates or 'Evening' not in selected_dates.get(date, []))):
                            eligible_days.remove(date)
                    
                    total_base_rem += len(eligible_days) * rule['rate']
            else:
                # Other roles (per shift): Filter base remuneration by selected classes for summary
                for _, r_row in role_df.iterrows():
                    if r_row['Is_Selected_Exam']:
                        total_base_rem += r_row['Base_Remuneration_Per_Shift_Unfiltered']

            total_conveyance = role_df['Conveyance'].sum() # Conveyance is NOT filtered by selected classes
            
            # Calculate total prep/closing remuneration for this role - ROLE SPECIFIC
            total_prep_added = 0
            total_closing_added = 0
            total_holiday_conveyance = 0
            
            if rule['eligible_prep_close']:
                # Only count prep/closing for people assigned to THIS specific role
                for name, person_assignments in prep_closing_assignments.items():
                    assigned_role = person_assignments.get('role')
                    if assigned_role == role_key:
                        prep_days = person_assignments.get('prep_days', [])
                        closing_days = person_assignments.get('closing_days', [])
                        total_prep_added += len(prep_days) * rule['rate']
                        total_closing_added += len(closing_days) * rule['rate']
                        
                        # Holiday conveyance
                        all_assigned_days = prep_days + closing_days
                        holiday_assigned_days = [day for day in all_assigned_days if day in holiday_dates]
                        total_holiday_conveyance += len(holiday_assigned_days) * manual_rates['holiday_conveyance_allowance_rate']
            
            grand_total = total_base_rem + total_conveyance + total_prep_added + total_closing_added + total_holiday_conveyance

            role_summary_matrix.append({
                'SN': len(role_summary_matrix) + 1,
                'Name (with role)': rule['role_display'],
                'Duty dates': '',
                'Shift (morning/evening)': '',
                'Total shifts (morning/evening)': total_shifts_count,
                'Rate in Rs': rule['rate'],
                'Total Remuneration in Rs': total_base_rem,
                'Total Conveyance (in evening shift)': total_conveyance,
                'Preparation Day Remuneration': total_prep_added,
                'Closing Day Remuneration': total_closing_added,
                'Total Holiday Conveyance Added': total_holiday_conveyance,
                'Total amount in Rs': grand_total,
                'Signature': ''
            })
    
    df_role_summary_matrix = pd.DataFrame(role_summary_matrix)

    # --- Generate Class 3 and Class 4 Worker Bills ---
    class_3_4_final_bills = []

    # --- UPDATED LOGIC FOR TOTAL STUDENTS FOR CLASS WORKERS ---
    # Class 3/4 worker remuneration is based on total unique students, filtered by selected classes
    if selected_classes_for_bill:
        # Get paper codes for the selected classes from the timetable
        papers_for_selected_classes = timetable_df[timetable_df['Class'].isin(selected_classes_for_bill)]['Paper Code'].unique()

        # Filter assigned seats based on these paper codes
        filtered_assigned_seats = assigned_seats_df[assigned_seats_df['Paper Code'].isin(papers_for_selected_classes)]

        # Calculate total unique students from the filtered list
        total_students_for_class_workers = filtered_assigned_seats['Roll Number'].nunique()
    else:
        # If no specific class is selected, consider all students across all exams
        total_students_for_class_workers = assigned_seats_df['Roll Number'].nunique()

    # Calculate remuneration for Class 3 workers
    if unique_class_3_workers:
        class_3_total_fixed_amount = total_students_for_class_workers * class_worker_rates['class_3_worker']['rate_per_student']
        num_class_3_workers = len(unique_class_3_workers)
        rem_per_class_3_worker = class_3_total_fixed_amount / num_class_3_workers if num_class_3_workers > 0 else 0

        for sn, worker_name in enumerate(sorted(list(unique_class_3_workers))):
            class_3_4_final_bills.append({
                'S.N.': len(class_3_4_final_bills) + 1,
                'Name': worker_name,
                'Role': class_worker_rates['class_3_worker']['role_display'],
                'Total Students (Center-wide)': total_students_for_class_workers,
                'Rate per Student (for category)': class_worker_rates['class_3_worker']['rate_per_student'],
                'Total Remuneration for Category (Rs.)': class_3_total_fixed_amount,
                'Number of Workers in Category': num_class_3_workers,
                'Remuneration per Worker in Rs.': rem_per_class_3_worker,
                'Signature of Receiver': ''
            })

    # Calculate remuneration for Class 4 workers
    if unique_class_4_workers:
        class_4_total_fixed_amount = total_students_for_class_workers * class_worker_rates['class_4_worker']['rate_per_student']
        num_class_4_workers = len(unique_class_4_workers)
        rem_per_class_4_worker = class_4_total_fixed_amount / num_class_4_workers if num_class_4_workers > 0 else 0

        for sn, worker_name in enumerate(sorted(list(unique_class_4_workers))):
            class_3_4_final_bills.append({
                'S.N.': len(class_3_4_final_bills) + 1,
                'Name': worker_name,
                'Role': class_worker_rates['class_4_worker']['role_display'],
                'Total Students (Center-wide)': total_students_for_class_workers,
                'Rate per Student (for category)': class_worker_rates['class_4_worker']['rate_per_student'],
                'Total Remuneration for Category (Rs.)': class_4_total_fixed_amount,
                'Number of Workers in Category': num_class_4_workers,
                'Remuneration per Worker in Rs.': rem_per_class_4_worker,
                'Signature of Receiver': ''
            })

    df_class_3_4_final_bills = pd.DataFrame(class_3_4_final_bills)
    
    return df_individual_bills, df_role_summary_matrix, df_class_3_4_final_bills

def add_total_row(df):
    """Add a total row to the dataframe"""
    if df.empty:
        return df
    
    total_row = {}
    for col in df.columns:
        if col in ['SN', 'S.N.']:
            total_row[col] = 'TOTAL'
        elif col in ['Name (with role)', 'Name', 'Role', 'Duty dates', 'Shift (morning/evening)', 'Signature', 'Signature of Receiver',
                     'Duty dates of selected class exam Shift (morning)', 'Duty dates of selected class exam Shift (evening)']:
            total_row[col] = ''
        elif df[col].dtype in ['int64', 'float64']:
            total_row[col] = df[col].sum()
        else:
            total_row[col] = ''
    
    total_df = pd.DataFrame([total_row])
    return pd.concat([df, total_df], ignore_index=True)

def save_bills_to_excel(individual_bills_df, role_summary_df, class_workers_df, filename="remuneration_bills.xlsx"):
    """
    Saves the three remuneration dataframes into a single Excel file with multiple sheets.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not individual_bills_df.empty:
            individual_bills_df.to_excel(writer, sheet_name='Individual Bills', index=False)
            # Auto-adjust column width for individual bills
            worksheet = writer.sheets['Individual Bills']
            for column in worksheet.columns:
                max_length = 0
                column_name = column[0].column_letter # Get the column name
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_name].width = adjusted_width

        if not role_summary_df.empty:
            role_summary_df.to_excel(writer, sheet_name='Role Summary', index=False)
            # Auto-adjust column width for role summary
            worksheet = writer.sheets['Role Summary']
            for column in worksheet.columns:
                max_length = 0
                column_name = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_name].width = adjusted_width

        if not class_workers_df.empty:
            class_workers_df.to_excel(writer, sheet_name='Class Workers', index=False)
            # Auto-adjust column width for class workers
            worksheet = writer.sheets['Class Workers']
            for column in worksheet.columns:
                max_length = 0
                column_name = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_name].width = adjusted_width
    
    output.seek(0)
    return output, filename
