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


# --- 2. CONFLICT DETECTION LOGIC ---
def check_conflicts(teacher_id, room_id, start, end):
    room_matches = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == room_id]
    if room_matches.empty:
        return f"Room ID '{room_id}' not found."
    room_info = room_matches.iloc[0]
    new_campus = room_info['Campus']

    for cls in st.session_state.schedule:
        if cls["teacher_id"] == teacher_id:
            if start < cls["end"] and end > cls["start"]:
                return f"Overlap: Already in {cls['room_name']} ({cls['start'].strftime('%H:%M')})"

            prev_room = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == cls['room_id']]
            if prev_room.empty:
                continue
            prev_room = prev_room.iloc[0]
            if new_campus != prev_room['Campus']:
                if start.date() == cls["start"].date():
                    gap_after  = (start - cls["end"]).total_seconds() / 60
                    gap_before = (cls["start"] - end).total_seconds() / 60
                    if (0 <= gap_after < 30) or (0 <= gap_before < 30):
                        return f"Travel Warning: Needs 30m between {prev_room['Campus']} & {new_campus}"
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
            "- `teacher_id` — must match a loaded Teacher ID\n"
            "- `room_id` — must match a loaded Room ID\n"
            "- `date` — `YYYY-MM-DD`\n"
            "- `start_time` — `HH:MM` (24h)\n"
            "- `end_time` — `HH:MM` (24h)"
        )
        st.dataframe(pd.DataFrame({
            "class_code": ["MATH101", "ENG201"],
            "teacher_id": ["T001",    "T002"],
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
                required_cols = {"class_code", "teacher_id", "room_id", "date", "start_time", "end_time"}
                missing_cols  = required_cols - set(sched_csv.columns)

                if missing_cols:
                    st.error(f"Missing columns: {', '.join(missing_cols)}")
                else:
                    valid_teacher_ids = set(st.session_state.teachers_df['ID'].astype(str))
                    valid_room_ids    = set(st.session_state.rooms_df['ID'].astype(str))
                    import_successes, import_errors = 0, []

                    for idx, row in sched_csv.iterrows():
                        row_label = f"Row {idx + 2}"

                        if str(row['teacher_id']) not in valid_teacher_ids:
                            import_errors.append(f"{row_label}: Unknown teacher_id '{row['teacher_id']}'")
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

                        conflict = check_conflicts(row['teacher_id'], row['room_id'], start_dt, end_dt)
                        if conflict:
                            import_errors.append(f"{row_label} ({row['class_code']}): {conflict}")
                            continue

                        room_name = st.session_state.rooms_df[
                            st.session_state.rooms_df['ID'] == row['room_id']
                        ]['Name'].values[0]

                        st.session_state.schedule.append({
                            "class_code": row['class_code'],
                            "teacher_id": row['teacher_id'],
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

        with st.form("scheduling_form"):
            c1, c2 = st.columns([1, 1])
            class_code = c1.text_input("Class Code", placeholder="e.g., MATH101")
            t_id = c2.selectbox(
                "Teacher",
                st.session_state.teachers_df['ID'].tolist(),
                format_func=lambda x: st.session_state.teachers_df[
                    st.session_state.teachers_df['ID'] == x
                ]['Name'].values[0]
            )

            # --- NEW: Campus pre-filter for room selection ---
            campus_options = ["All"] + sorted(
                st.session_state.rooms_df['Campus'].dropna().unique().tolist()
            )
            f_col, r_col = st.columns([1, 2])
            campus_filter = f_col.radio("Filter by Campus", campus_options, horizontal=True)

            if campus_filter == "All":
                filtered_rooms = st.session_state.rooms_df
            else:
                filtered_rooms = st.session_state.rooms_df[
                    st.session_state.rooms_df['Campus'] == campus_filter
                ]

            r_id = r_col.selectbox(
                "Room",
                filtered_rooms['ID'].tolist(),
                # Adding a dynamic key forces the dropdown to completely reset when the campus changes
                key=f"room_select_{campus_filter}", 
                format_func=lambda x: (
                    f"{st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Name'].values[0]}"
                    f" ({st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Campus'].values[0]})"
                )
            )
            # -----------------------------------------------

            t_start = st.time_input("Start Time", time(9, 0))
            t_end   = st.time_input("End Time",   time(10, 0))

            dates_to_schedule = []

            if method == "Single 1-Day Class":
                sel_date = st.date_input("Select Date")
                if st.form_submit_button("Add Single Class"):
                    dates_to_schedule = [datetime.combine(sel_date, time.min)]
            else:
                col_m, col_y = st.columns(2)
                target_month = col_m.selectbox(
                    "Month", list(range(1, 13)),
                    format_func=lambda x: py_calendar.month_name[x],
                    index=datetime.now().month - 1
                )
                target_year = col_y.number_input(
                    "Year", min_value=2025, max_value=2030, value=2026
                )
                days_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
                selected_days = st.multiselect("Repeat on:", list(days_map.keys()), default=["Mon"])

                if st.form_submit_button("Generate Monthly Schedule"):
                    num_days  = py_calendar.monthrange(target_year, target_month)[1]
                    all_days  = [datetime(target_year, target_month, d) for d in range(1, num_days + 1)]
                    day_indices = [days_map[d] for d in selected_days]
                    dates_to_schedule = [d for d in all_days if d.weekday() in day_indices]

            if dates_to_schedule:
                successes, errors = 0, []
                for d in dates_to_schedule:
                    start_dt = datetime.combine(d.date(), t_start)
                    end_dt   = datetime.combine(d.date(), t_end)
                    err = check_conflicts(t_id, r_id, start_dt, end_dt)
                    if err:
                        errors.append(f"{d.strftime('%b %d')}: {err}")
                    else:
                        st.session_state.schedule.append({
                            "class_code": class_code,
                            "teacher_id": t_id,
                            "room_id":    r_id,
                            "start":      start_dt,
                            "end":        end_dt,
                            "room_name":  st.session_state.rooms_df[
                                st.session_state.rooms_df['ID'] == r_id
                            ]['Name'].values[0]
                        })
                        successes += 1
                if successes:
                    st.success(f"Added {successes} classes for {class_code}.")
                if errors:
                    st.error(f"Conflicts found on {len(errors)} dates.")
                for e in errors:
                    st.caption(e)

# --- TAB 2: VISUAL TIMETABLE (Optimized Layout) ---
    with tab2:
        # 1. CUSTOM CSS: Fixes the width of the time column (the '6pm' issue)
        st.markdown("""
            <style>
                /* Adjusts the width of the time labels column in FullCalendar */
                .fc-timegrid-slot-label { width: 60px !important; }
                .fc-timegrid-axis { width: 60px !important; }
            </style>
        """, unsafe_allow_html=True)

        if 'clipboard' not in st.session_state:
            st.session_state.clipboard = None

        # --- NEW DIALOG: EDIT & PASTE ---
        @st.dialog("Edit & Confirm Paste", width="large")
        def paste_dialog(paste_start):
            clip = st.session_state.clipboard
            paste_end = paste_start + timedelta(minutes=clip['duration_mins'])
            
            st.markdown("### 📝 Edit Class Details")
            new_class_code = st.text_input("Class Code", value=clip['class_code'])
            
            col1, col2 = st.columns(2)
            with col1:
                new_teacher_id = st.selectbox(
                    "Assign Teacher",
                    options=st.session_state.teachers_df['ID'].tolist(),
                    index=st.session_state.teachers_df['ID'].tolist().index(clip['teacher_id']),
                    format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID'] == x]['Name'].values[0]
                )
            with col2:
                new_room_id = st.selectbox(
                    "Assign Room",
                    options=st.session_state.rooms_df['ID'].tolist(),
                    index=st.session_state.rooms_df['ID'].tolist().index(clip['room_id']),
                    format_func=lambda x: st.session_state.rooms_df[st.session_state.rooms_df['ID'] == x]['Name'].values[0]
                )

            st.info(f"🕒 **Time Slot:** {paste_start.strftime('%H:%M')} - {paste_end.strftime('%H:%M')} on {paste_start.strftime('%Y-%m-%d')}")
            new_room_name = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == new_room_id]['Name'].values[0]

            if st.button("🚀 Confirm & Add to Master Data", use_container_width=True):
                conflict = check_conflicts(new_teacher_id, new_room_id, paste_start, paste_end)
                if conflict:
                    st.error(f"❌ {conflict}")
                else:
                    new_entry = {
                        "class_code": new_class_code,
                        "teacher_id": new_teacher_id,
                        "room_id": new_room_id,
                        "room_name": new_room_name,
                        "start": paste_start, "end": paste_end
                    }
                    st.session_state.schedule.append(new_entry)
                    st.session_state.clipboard = None 
                    st.rerun()

        # --- 2. MOVE ACTIONS TO TOP (Above View Mode) ---
        # We retrieve the calendar state first to see if anything was clicked
        # Note: In Streamlit, we define the calendar further down, but we process the previous run's state here.
        # However, for a cleaner 'Top-Down' UI, we use a placeholder or check the 'state' variable after it's defined.
        
        # --- (A) CLIPBOARD INDICATOR ---
        if st.session_state.clipboard:
            st.warning(f"📋 **In Clipboard:** {st.session_state.clipboard['class_code']} | Click any time slot to paste.")

        # --- (B) QUICK ACTION BAR (Moved to top) ---
        # This will populate if a user clicks an event on the calendar
        # We check the 'calendar_state' from the SESSION or directly from the component return
        # Using a container to ensure it stays at the top
        action_container = st.container()

        # --- 3. VIEW MODE & FILTERS ---
        st.divider()
        v_c1, v_c2 = st.columns([1, 2])
        v_mode = v_c1.radio("View Mode:", ["Teacher", "Room"], horizontal=True, key="tm_view_mode")
        
        if v_mode == "Teacher":
            sid = v_c2.selectbox("Select Teacher", st.session_state.teachers_df['ID'].tolist(), 
                                 format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID']==x]['Name'].values[0])
        else:
            sid = v_c2.selectbox("Select Room", st.session_state.rooms_df['ID'].tolist(), 
                                 format_func=lambda x: st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Name'].values[0])

        # Prepare Events
        events = []
        for idx, x in enumerate(st.session_state.schedule):
            if (v_mode == "Teacher" and x['teacher_id'] == sid) or (v_mode == "Room" and x['room_id'] == sid):
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
            "slotLabelWidth": "60", # Explicitly request width in pixels
        }

        # --- 4. RENDER CALENDAR ---
        state = st_calendar(events=events, options=calendar_options, key=f"cal_{v_mode}_{sid}")

        # --- 5. LOGIC PROCESSING ---
        # Update the 'Action Container' at the top if an event is clicked
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

        # Handle Dragging (Auto-save)
        if state.get("eventChange"):
            event_id = int(state["eventChange"]["event"]["id"])
            new_start = datetime.fromisoformat(state["eventChange"]["event"]["start"].split(".")[0].replace("Z", "")).replace(tzinfo=None)
            new_end = datetime.fromisoformat(state["eventChange"]["event"]["end"].split(".")[0].replace("Z", "")).replace(tzinfo=None)
            item = st.session_state.schedule.pop(event_id)
            conflict = check_conflicts(item['teacher_id'], item['room_id'], new_start, new_end)
            if not conflict:
                item.update({"start": new_start, "end": new_end})
                st.session_state.schedule.insert(event_id, item)
                st.rerun()
            else:
                st.error(conflict)
                st.session_state.schedule.insert(event_id, item)

        # Handle Pasting (Dialog)
        if state.get("dateClick") and st.session_state.clipboard:
            raw_date = state["dateClick"]["date"].split(".")[0].replace("Z", "")
            clicked_time = datetime.fromisoformat(raw_date).replace(tzinfo=None)
            paste_dialog(clicked_time)
            
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
                    t_sum = df_r.groupby('teacher_id')['Hrs'].sum().reset_index()
                    t_sum = t_sum.merge(
                        st.session_state.teachers_df[['ID', 'Name', 'Type']],
                        left_on='teacher_id', right_on='ID'
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

            disp_df = pd.DataFrame({
                "Class Code":   df_m['class_code'],
                "Teacher Name": df_m['teacher_id'].map(t_map),
                "Room Name":    df_m['room_id'].map(r_map),
                "Campus":       df_m['room_id'].map(c_map),
                "Start Time":   df_m['start'],
                "End Time":     df_m['end']
            })

            e_df = st.data_editor(
                disp_df,
                column_config={
                    "Teacher Name": st.column_config.SelectboxColumn(
                        "Teacher Name", options=list(t_map.values()), required=True
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
                    if pd.isna(row['Teacher Name']) or pd.isna(row['Room Name']):
                        continue
                    new_s.append({
                        "class_code": row['Class Code'],
                        "teacher_id": rev_t_map[row['Teacher Name']],
                        "room_id":    rev_r_map[row['Room Name']],
                        "room_name":  row['Room Name'],
                        "start":      row['Start Time'],
                        "end":        row['End Time']
                    })
                st.session_state.schedule = new_s
                st.success("Schedule Updated!")
                st.rerun()

            # --- FIX 1: Export in bulk-upload-compatible format ---
            if c_e.button("📥 Export Master Schedule"):
                export_rows = []
                for _, row in e_df.iterrows():
                    if pd.isna(row['Teacher Name']) or pd.isna(row['Room Name']):
                        continue
                    export_rows.append({
                        "class_code": row['Class Code'],
                        "teacher_id": rev_t_map.get(row['Teacher Name'], ""),
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
