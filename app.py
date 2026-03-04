import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import calendar as py_calendar
from streamlit_calendar import calendar as st_calendar

st.set_page_config(layout="wide", page_title="Class Scheduler")

# --- 1. INITIALIZE DATA STORAGE ---
if 'schedule' not in st.session_state:
    st.session_state.schedule = []
if 'teachers_df' not in st.session_state:
    st.session_state.teachers_df = pd.DataFrame(columns=["ID", "Name", "Type"])
if 'rooms_df' not in st.session_state:
    st.session_state.rooms_df = pd.DataFrame(columns=["ID", "Name", "Campus"])

# --- 2. CONFLICT DETECTION LOGIC (UPDATED FOR CO-TEACHING) ---
def check_conflicts(class_code, teacher_ids, room_id, start, end):
    room_matches = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == room_id]
    if room_matches.empty:
        return f"Room ID '{room_id}' not found."
    room_info = room_matches.iloc[0]
    new_campus = room_info['Campus']

    for cls in st.session_state.schedule:
        # Check Time Overlap
        if start < cls["end"] and end > cls["start"]:
            
            # 1. Room Conflict: Room already occupied by a DIFFERENT class code
            if cls["room_id"] == room_id and cls["class_code"] != class_code:
                return f"Room Overlap: {cls['room_name']} is already occupied by {cls['class_code']} ({cls['start'].strftime('%H:%M')})"
            
            # 2. Teacher Conflict: Any of the new teachers already scheduled
            overlapping_teachers = set(cls["teacher_ids"]).intersection(set(teacher_ids))
            if overlapping_teachers:
                # If exact same class and room, it's a duplicate entry
                if cls["class_code"] == class_code and cls["room_id"] == room_id:
                    return f"Duplicate: Teachers {list(overlapping_teachers)} are already assigned to this exact class."
                # Otherwise, teacher is double-booked
                return f"Teacher Overlap: {list(overlapping_teachers)} already teaching {cls['class_code']} ({cls['start'].strftime('%H:%M')})"

        # 3. Travel Warning (Check specific to each assigned teacher)
        overlapping_teachers = set(cls["teacher_ids"]).intersection(set(teacher_ids))
        if overlapping_teachers:
            prev_room = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == cls['room_id']]
            if prev_room.empty:
                continue
            prev_room = prev_room.iloc[0]
            if new_campus != prev_room['Campus']:
                if start.date() == cls["start"].date():
                    gap_after  = (start - cls["end"]).total_seconds() / 60
                    gap_before = (cls["start"] - end).total_seconds() / 60
                    if (0 <= gap_after < 30) or (0 <= gap_before < 30):
                        return f"Travel Warning: Teachers {list(overlapping_teachers)} need 30m between {prev_room['Campus']} & {new_campus}"
    return None

# --- 3. SIDEBAR: DATA UPLOAD ---
with st.sidebar:
    st.title("⚙️ Data Management")
    t_file = st.file_uploader("Upload Teachers (CSV/XLSX)", type=["csv", "xlsx"])
    r_file = st.file_uploader("Upload Rooms (CSV/XLSX)",    type=["csv", "xlsx"])

    if t_file:
        df = pd.read_csv(t_file) if t_file.name.endswith('csv') else pd.read_excel(t_file)
        if 'Type' not in df.columns:
            df['Type'] = 'Full-time'
        st.session_state.teachers_df = df

    if r_file:
        st.session_state.rooms_df = (
            pd.read_csv(r_file) if r_file.name.endswith('csv') else pd.read_excel(r_file)
        )

    if not st.session_state.teachers_df.empty:
        st.divider()
        st.subheader("Teacher Classifications")
        st.session_state.teachers_df = st.data_editor(
            st.session_state.teachers_df, hide_index=True
        )

    # --- BULK SCHEDULE UPLOAD ---
    st.divider()
    st.subheader("📂 Bulk Schedule Upload")

    with st.expander("ℹ️ Required CSV Format"):
        st.markdown(
            "Your CSV must have these columns:\n"
            "- `class_code` — e.g. `MATH101`\n"
            "- `teacher_ids` — comma separated (e.g. `T001, T002`)\n"
            "- `room_id` — must match a loaded Room ID\n"
            "- `date` — `YYYY-MM-DD`\n"
            "- `start_time` — `HH:MM` (24h)\n"
            "- `end_time` — `HH:MM` (24h)"
        )
        st.dataframe(pd.DataFrame({
            "class_code": ["MATH101", "ENG201"],
            "teacher_ids": ["T001, T003", "T002"],
            "room_id":    ["R101",    "R102"],
            "date":       ["2026-03-03", "2026-03-03"],
            "start_time": ["09:00",   "10:00"],
            "end_time":   ["10:00",   "11:00"],
        }), hide_index=True, use_container_width=True)

    sched_file = st.file_uploader("Upload Class Schedule (CSV)", type=["csv"], key="sched_upload")

    if sched_file:
        if st.session_state.teachers_df.empty or st.session_state.rooms_df.empty:
            st.warning("Please upload Teachers and Rooms data before importing a schedule.")
        else:
            try:
                sched_csv = pd.read_csv(sched_file)
                required_cols = {"class_code", "teacher_ids", "room_id", "date", "start_time", "end_time"}
                missing_cols  = required_cols - set(sched_csv.columns)

                if missing_cols:
                    st.error(f"Missing columns: {', '.join(missing_cols)}")
                else:
                    valid_teacher_ids = set(st.session_state.teachers_df['ID'].astype(str))
                    valid_room_ids    = set(st.session_state.rooms_df['ID'].astype(str))
                    import_successes, import_errors = 0, []

                    for idx, row in sched_csv.iterrows():
                        row_label = f"Row {idx + 2}"
                        
                        # Parse multi-teachers
                        raw_t_ids = str(row['teacher_ids']).split(',')
                        t_ids_parsed = [t.strip() for t in raw_t_ids]

                        invalid_teachers = [t for t in t_ids_parsed if t not in valid_teacher_ids]
                        if invalid_teachers:
                            import_errors.append(f"{row_label}: Unknown teacher_ids '{invalid_teachers}'")
                            continue

                        if str(row['room_id']) not in valid_room_ids:
                            import_errors.append(f"{row_label}: Unknown room_id '{row['room_id']}'")
                            continue

                        try:
                            start_dt = datetime.strptime(f"{row['date']} {row['start_time']}", "%Y-%m-%d %H:%M")
                            end_dt   = datetime.strptime(f"{row['date']} {row['end_time']}",   "%Y-%m-%d %H:%M")
                        except ValueError:
                            import_errors.append(f"{row_label}: Invalid date/time format")
                            continue

                        if end_dt <= start_dt:
                            import_errors.append(f"{row_label}: End time must be after start time")
                            continue

                        conflict = check_conflicts(row['class_code'], t_ids_parsed, row['room_id'], start_dt, end_dt)
                        if conflict:
                            import_errors.append(f"{row_label} ({row['class_code']}): {conflict}")
                            continue

                        room_name = st.session_state.rooms_df[
                            st.session_state.rooms_df['ID'] == row['room_id']
                        ]['Name'].values[0]

                        st.session_state.schedule.append({
                            "class_code": row['class_code'],
                            "teacher_ids": t_ids_parsed,
                            "room_id":    row['room_id'],
                            "room_name":  room_name,
                            "start":      start_dt,
                            "end":        end_dt,
                        })
                        import_successes += 1

                    if import_successes:
                        st.success(f"✅ Imported {import_successes} classes successfully.")
                    if import_errors:
                        st.error(f"⚠️ {len(import_errors)} rows skipped.")
                        for e in import_errors:
                            st.caption(e)

            except Exception as ex:
                st.error(f"Failed to read file: {ex}")

    st.divider()
    if st.button("Clear All Schedule Data"):
        st.session_state.schedule = []
        st.rerun()

# --- 4. MAIN INTERFACE ---
st.title("🗓️ Master Timetable")

if st.session_state.teachers_df.empty or st.session_state.rooms_df.empty:
    st.info("Please upload Teacher and Room lists in the sidebar to begin.")
else:
    tab1, tab2, tab3, tab4 = st.tabs([
        "➕ Schedule Class",
        "📅 Timetable",
        "📊 Reports",
        "📝 Master List"
    ])

# --- TAB 1: SCHEDULING ---
    with tab1:
        method = st.radio(
            "Scheduling Method",
            ["Single 1-Day Class", "Recurring Weekly Classes"],
            horizontal=True
        )

        # 1. Move Campus and Room Selection OUTSIDE the form to allow reactivity
        st.subheader("Class & Location")
        c1, c2 = st.columns([1, 1])
        class_code = c1.text_input("Class Code", placeholder="e.g., MATH101")
        
        t_ids = c2.multiselect(
            "Teachers",
            st.session_state.teachers_df['ID'].tolist(),
            format_func=lambda x: st.session_state.teachers_df[
                st.session_state.teachers_df['ID'].astype(str) == str(x)
            ]['Name'].values[0]
        )

        campus_options = ["All"] + sorted(st.session_state.rooms_df['Campus'].dropna().unique().tolist())
        f_col, r_col = st.columns([1, 2])
        
        # This radio button now triggers an immediate rerun
        campus_filter = f_col.radio("Filter by Campus", campus_options, horizontal=True)

        if campus_filter == "All":
            filtered_rooms = st.session_state.rooms_df
        else:
            filtered_rooms = st.session_state.rooms_df[st.session_state.rooms_df['Campus'] == campus_filter]

        r_id = r_col.selectbox(
            "Room",
            filtered_rooms['ID'].tolist(),
            key=f"room_select_{campus_filter}", 
            format_func=lambda x: (
                f"{st.session_state.rooms_df[st.session_state.rooms_df['ID'].astype(str)==str(x)]['Name'].values[0]}"
                f" ({st.session_state.rooms_df[st.session_state.rooms_df['ID'].astype(str)==str(x)]['Campus'].values[0]})"
            )
        )

        # 2. Keep the Date/Time inputs and the "Add" button inside a form if you want to group the submission
        with st.form("time_date_form"):
            st.subheader("Time & Date")
            t_start = st.time_input("Start Time", time(9, 0))
            t_end   = st.time_input("End Time",   time(10, 0))

            dates_to_schedule = []

            if method == "Single 1-Day Class":
                sel_date = st.date_input("Select Date")
                submit_btn = st.form_submit_button("Add Single Class")
                if submit_btn:
                    dates_to_schedule = [datetime.combine(sel_date, time.min)]
            else:
                col_m, col_y = st.columns(2)
                target_month = col_m.selectbox("Month", list(range(1, 13)), format_func=lambda x: py_calendar.month_name[x], index=datetime.now().month - 1)
                target_year = col_y.number_input("Year", min_value=2025, max_value=2030, value=2026)
                days_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
                selected_days = st.multiselect("Repeat on:", list(days_map.keys()), default=["Mon"])
                
                submit_btn = st.form_submit_button("Generate Monthly Schedule")
                if submit_btn:
                    num_days  = py_calendar.monthrange(target_year, target_month)[1]
                    all_days  = [datetime(target_year, target_month, d) for d in range(1, num_days + 1)]
                    day_indices = [days_map[d] for d in selected_days]
                    dates_to_schedule = [d for d in all_days if d.weekday() in day_indices]

            # Logic to process the "dates_to_schedule" remains the same...
            if dates_to_schedule:
                # (Validation and session_state.schedule.append logic here)
                pass

    # --- TAB 2: VISUAL TIMETABLE ---
    with tab2:
        st.markdown("""
            <style>
                .fc-timegrid-slot-label { width: 60px !important; }
                .fc-timegrid-axis { width: 60px !important; }
            </style>
        """, unsafe_allow_html=True)

        if 'clipboard' not in st.session_state:
            st.session_state.clipboard = None

        @st.dialog("Edit & Confirm Paste", width="large")
        def paste_dialog(paste_start, current_view_mode, current_sid):
            clip = st.session_state.clipboard
            paste_end = paste_start + timedelta(minutes=clip['duration_mins'])
            
            def_t_ids = [current_sid] if current_view_mode == "Teacher" and current_sid not in clip['teacher_ids'] else clip['teacher_ids']
            def_r_id = current_sid if current_view_mode == "Room" else clip['room_id']

            st.markdown("### 📝 Edit Class Details")
            new_class_code = st.text_input("Class Code", value=clip['class_code'])
            
            col1, col2 = st.columns(2)
            
            t_options = st.session_state.teachers_df['ID'].tolist()
            with col1:
                new_teacher_ids = st.multiselect(
                    "Assign Teachers",
                    options=t_options,
                    default=[t for t in def_t_ids if t in t_options],
                    format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID'] == x]['Name'].values[0]
                )
                
            r_options = st.session_state.rooms_df['ID'].tolist()
            with col2:
                new_room_id = st.selectbox(
                    "Assign Room",
                    options=r_options,
                    index=r_options.index(def_r_id) if def_r_id in r_options else 0,
                    format_func=lambda x: st.session_state.rooms_df[st.session_state.rooms_df['ID'] == x]['Name'].values[0]
                )

            st.info(f"🕒 **Time Slot:** {paste_start.strftime('%H:%M')} - {paste_end.strftime('%H:%M')} on {paste_start.strftime('%Y-%m-%d')}")
            new_room_name = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == new_room_id]['Name'].values[0]

            if st.button("🚀 Confirm & Add to Master Data", use_container_width=True):
                if not new_teacher_ids:
                    st.error("Please assign at least one teacher.")
                    return
                
                conflict = check_conflicts(new_class_code, new_teacher_ids, new_room_id, paste_start, paste_end)
                if conflict:
                    st.error(f"❌ {conflict}")
                else:
                    new_entry = {
                        "class_code": new_class_code,
                        "teacher_ids": new_teacher_ids,
                        "room_id": new_room_id,
                        "room_name": new_room_name,
                        "start": paste_start, "end": paste_end
                    }
                    st.session_state.schedule.append(new_entry)
                    st.session_state.clipboard = None 
                    st.rerun()

        if st.session_state.clipboard:
            st.warning(f"📋 **In Clipboard:** {st.session_state.clipboard['class_code']} | Click any time slot to paste.")

        action_container = st.container()

        st.divider()
        v_c1, v_c2 = st.columns([1, 2])
        v_mode = v_c1.radio("View Mode:", ["Teacher", "Room"], horizontal=True, key="tm_view_mode")
        
        if v_mode == "Teacher":
            sid = v_c2.selectbox("Select Teacher", st.session_state.teachers_df['ID'].tolist(), 
                                 format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID']==x]['Name'].values[0])
        else:
            sid = v_c2.selectbox("Select Room", st.session_state.rooms_df['ID'].tolist(), 
                                 format_func=lambda x: st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Name'].values[0])

        events = []
        for idx, x in enumerate(st.session_state.schedule):
            if (v_mode == "Teacher" and sid in x['teacher_ids']) or (v_mode == "Room" and x['room_id'] == sid):
                events.append({
                    "id": str(idx),
                    "title": f"[{x['class_code']}]",
                    "start": x['start'].isoformat(),
                    "end": x['end'].isoformat(),
                    "color": "#3D9DF3" if v_mode == "Teacher" else "#FF4B4B"
                })

        calendar_options = {
            "initialView": "timeGridWeek",
            "slotMinTime": "09:00:00",
            "slotMaxTime": "19:00:00",
            "timeZone": "UTC",
            "editable": True,
            "selectable": True,
            "slotLabelWidth": "60",
            "slotDuration":'00:15:00',
            "allDaySlot": False, 
        }

        state = st_calendar(events=events, options=calendar_options, key=f"cal_{v_mode}_{sid}")

        if state.get("eventClick"):
            event_id = int(state["eventClick"]["event"]["id"])
            item = st.session_state.schedule[event_id]
            with action_container:
                st.info(f"📍 **Selected:** {item['class_code']}")
                c1, c2, c3 = st.columns([1, 1, 2])
                if c1.button("📋 Copy Class", use_container_width=True):
                    dur = (item['end'] - item['start']).total_seconds() / 60
                    st.session_state.clipboard = {**item, "duration_mins": dur}
                    st.rerun()
                if c2.button("🗑️ Delete", use_container_width=True):
                    st.session_state.schedule.pop(event_id)
                    st.rerun()

        if state.get("eventChange"):
            event_id = int(state["eventChange"]["event"]["id"])
            new_start = datetime.fromisoformat(state["eventChange"]["event"]["start"].split(".")[0].replace("Z", "")).replace(tzinfo=None)
            new_end = datetime.fromisoformat(state["eventChange"]["event"]["end"].split(".")[0].replace("Z", "")).replace(tzinfo=None)
            item = st.session_state.schedule.pop(event_id)
            
            conflict = check_conflicts(item['class_code'], item['teacher_ids'], item['room_id'], new_start, new_end)
            if not conflict:
                item.update({"start": new_start, "end": new_end})
                st.session_state.schedule.insert(event_id, item)
                st.rerun()
            else:
                st.error(conflict)
                st.session_state.schedule.insert(event_id, item)

        if state.get("dateClick") and st.session_state.clipboard:
            raw_date = state["dateClick"]["date"].split(".")[0].replace("Z", "")
            clicked_time = datetime.fromisoformat(raw_date).replace(tzinfo=None)
            paste_dialog(clicked_time, v_mode, sid)
            
    # --- TAB 3: REPORTS ---
    with tab3:
        st.subheader("📊 Workload & Occupancy Reports")
        r_today = datetime.now().date()
        r_range = st.date_input(
            "Filter Reports by Date Range",
            value=(r_today, r_today + timedelta(days=30))
        )

        if isinstance(r_range, tuple) and len(r_range) == 2:
            s_dt   = datetime.combine(r_range[0], time.min)
            e_dt   = datetime.combine(r_range[1], time.max)
            r_data = [x for x in st.session_state.schedule if s_dt <= x['start'] <= e_dt]

            if r_data:
                df_r = pd.DataFrame(r_data)
                df_r['Hrs'] = (df_r['end'] - df_r['start']).dt.total_seconds() / 3600

                col_rep1, col_rep2 = st.columns(2)

                with col_rep1:
                    st.write("**Teacher Workload Summary**")
                    # Explode the teacher_ids list so co-teachers both get the hours credited
                    df_t_exp = df_r.explode('teacher_ids')
                    t_sum = df_t_exp.groupby('teacher_ids')['Hrs'].sum().reset_index()
                    t_sum = t_sum.merge(
                        st.session_state.teachers_df[['ID', 'Name', 'Type']],
                        left_on='teacher_ids', right_on='ID'
                    )
                    st.dataframe(
                        t_sum[['Name', 'Type', 'Hrs']].sort_values('Hrs', ascending=False),
                        hide_index=True, use_container_width=True
                    )

                with col_rep2:
                    st.write("**Room Occupancy Summary**")
                    r_sum = df_r.groupby('room_id')['Hrs'].sum().reset_index()
                    r_sum = r_sum.merge(
                        st.session_state.rooms_df[['ID', 'Name', 'Campus']],
                        left_on='room_id', right_on='ID'
                    )
                    st.dataframe(
                        r_sum[['Name', 'Campus', 'Hrs']].sort_values('Hrs', ascending=False),
                        hide_index=True, use_container_width=True
                    )

                st.download_button(
                    "📥 Export Range Report (CSV)",
                    df_r.to_csv(index=False).encode('utf-8'),
                    "report.csv"
                )
            else:
                st.info("No data found for this range.")

    # --- TAB 4: MASTER LIST ---
    with tab4:
        st.subheader("📝 Master Schedule Editor")
        if st.session_state.schedule:
            df_m = pd.DataFrame(st.session_state.schedule)

            t_map     = dict(zip(st.session_state.teachers_df['ID'], st.session_state.teachers_df['Name']))
            rev_t_map = dict(zip(st.session_state.teachers_df['Name'], st.session_state.teachers_df['ID']))
            r_map     = dict(zip(st.session_state.rooms_df['ID'], st.session_state.rooms_df['Name']))
            rev_r_map = dict(zip(st.session_state.rooms_df['Name'], st.session_state.rooms_df['ID']))
            c_map     = dict(zip(st.session_state.rooms_df['ID'], st.session_state.rooms_df['Campus']))

            # Convert ID lists to comma-separated teacher names for easier display/editing
            df_m['Teacher Names'] = df_m['teacher_ids'].apply(lambda ids: ", ".join([t_map.get(i, i) for i in ids]))

            disp_df = pd.DataFrame({
                "Class Code":   df_m['class_code'],
                "Teacher Names": df_m['Teacher Names'],
                "Room Name":    df_m['room_id'].map(r_map),
                "Campus":       df_m['room_id'].map(c_map),
                "Start Time":   df_m['start'],
                "End Time":     df_m['end']
            })

            e_df = st.data_editor(
                disp_df,
                column_config={
                    "Teacher Names": st.column_config.TextColumn(
                        "Teacher Names (Comma Separated)", required=True, help="Separate multiple teacher names with commas"
                    ),
                    "Room Name": st.column_config.SelectboxColumn(
                        "Room Name", options=list(r_map.values()), required=True
                    ),
                    "Campus": st.column_config.TextColumn("Campus", disabled=True),
                    "Start Time": st.column_config.DatetimeColumn(
                        "Start Time", format="YYYY-MM-DD HH:mm", required=True
                    ),
                    "End Time": st.column_config.DatetimeColumn(
                        "End Time", format="YYYY-MM-DD HH:mm", required=True
                    ),
                },
                num_rows="dynamic", use_container_width=True, key="m_edit"
            )

            c_s, c_e = st.columns(2)

            if c_s.button("💾 Save All Changes"):
                new_s = []
                for _, row in e_df.iterrows():
                    if pd.isna(row['Teacher Names']) or pd.isna(row['Room Name']):
                        continue
                    
                    # Parse back to IDs
                    raw_names = str(row['Teacher Names']).split(',')
                    parsed_t_ids = [rev_t_map.get(n.strip(), n.strip()) for n in raw_names if n.strip() in rev_t_map]

                    new_s.append({
                        "class_code": row['Class Code'],
                        "teacher_ids": parsed_t_ids,
                        "room_id":    rev_r_map[row['Room Name']],
                        "room_name":  row['Room Name'],
                        "start":      row['Start Time'],
                        "end":        row['End Time']
                    })
                st.session_state.schedule = new_s
                st.success("Schedule Updated!")
                st.rerun()

            if c_e.button("📥 Export Master Schedule"):
                export_rows = []
                for _, row in e_df.iterrows():
                    if pd.isna(row['Teacher Names']) or pd.isna(row['Room Name']):
                        continue
                    
                    raw_names = str(row['Teacher Names']).split(',')
                    parsed_t_ids = [rev_t_map.get(n.strip(), n.strip()) for n in raw_names if n.strip() in rev_t_map]

                    export_rows.append({
                        "class_code": row['Class Code'],
                        "teacher_ids": ", ".join(parsed_t_ids),
                        "room_id":    rev_r_map.get(row['Room Name'], ""),
                        "date":       pd.to_datetime(row['Start Time']).strftime("%Y-%m-%d"),
                        "start_time": pd.to_datetime(row['Start Time']).strftime("%H:%M"),
                        "end_time":   pd.to_datetime(row['End Time']).strftime("%H:%M"),
                    })
                export_df = pd.DataFrame(export_rows)
                st.download_button(
                    "⬇️ Download CSV",
                    export_df.to_csv(index=False).encode('utf-8'),
                    "master_schedule.csv",
                    mime="text/csv"
                )
        else:
            st.warning("Schedule is empty.")