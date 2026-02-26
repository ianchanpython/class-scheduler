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
    room_info = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == room_id].iloc[0]
    new_campus = room_info['Campus']
    
    for cls in st.session_state.schedule:
        if cls["teacher_id"] == teacher_id:
            if start < cls["end"] and end > cls["start"]:
                return f"Overlap: Already in {cls['room_name']} ({cls['start'].strftime('%H:%M')})"
            
            prev_room = st.session_state.rooms_df[st.session_state.rooms_df['ID'] == cls['room_id']].iloc[0]
            if new_campus != prev_room['Campus']:
                if start.date() == cls["start"].date():
                    gap_after = (start - cls["end"]).total_seconds() / 60
                    gap_before = (cls["start"] - end).total_seconds() / 60
                    
                    if (0 <= gap_after < 30) or (0 <= gap_before < 30):
                        return f"Travel Warning: Needs 30m between {prev_room['Campus']} & {new_campus}"
    return None

# --- 3. SIDEBAR: DATA UPLOAD ---
with st.sidebar:
    st.title("⚙️ Data Management")
    t_file = st.file_uploader("Upload Teachers (CSV/XLSX)", type=["csv", "xlsx"])
    r_file = st.file_uploader("Upload Rooms (CSV/XLSX)", type=["csv", "xlsx"])

    if t_file:
        df = pd.read_csv(t_file) if t_file.name.endswith('csv') else pd.read_excel(t_file)
        if 'Type' not in df.columns: df['Type'] = 'Full-time'
        st.session_state.teachers_df = df
    
    if r_file:
        st.session_state.rooms_df = pd.read_csv(r_file) if r_file.name.endswith('csv') else pd.read_excel(r_file)

    if not st.session_state.teachers_df.empty:
        st.divider()
        st.subheader("Teacher Classifications")
        st.session_state.teachers_df = st.data_editor(st.session_state.teachers_df, hide_index=True)
    
    if st.button("Clear All Schedule Data"):
        st.session_state.schedule = []
        st.rerun()

# --- 4. MAIN INTERFACE ---
st.title("🗓️ Master Timetable")

if st.session_state.teachers_df.empty or st.session_state.rooms_df.empty:
    st.info("Please upload Teacher and Room lists in the sidebar to begin.")
else:
    # Updated Tab Structure
    tab1, tab2, tab3, tab4 = st.tabs([
        "➕ Schedule Class", 
        "📅 Timetable", 
        "📊 Reports", 
        "📝 Master List"
    ])

    # --- TAB 1: SCHEDULING ---
    with tab1:
        method = st.radio("Scheduling Method", ["Single 1-Day Class", "Recurring Weekly Classes"], horizontal=True)
        
        with st.form("scheduling_form"):
            c1, c2, c3 = st.columns([1, 1, 1])
            class_code = c1.text_input("Class Code", placeholder="e.g., MATH101")
            t_id = c2.selectbox("Teacher", st.session_state.teachers_df['ID'].tolist(), 
                               format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID']==x]['Name'].values[0])
            r_id = c3.selectbox("Room", st.session_state.rooms_df['ID'].tolist(), 
                               format_func=lambda x: f"{st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Name'].values[0]} ({st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Campus'].values[0]})")
            
            t_start = st.time_input("Start Time", time(9, 0))
            t_end = st.time_input("End Time", time(10, 0))

            dates_to_schedule = []

            if method == "Single 1-Day Class":
                sel_date = st.date_input("Select Date")
                if st.form_submit_button("Add Single Class"):
                    dates_to_schedule = [datetime.combine(sel_date, time.min)]
            else:
                col_m, col_y = st.columns(2)
                target_month = col_m.selectbox("Month", list(range(1, 13)), format_func=lambda x: py_calendar.month_name[x], index=datetime.now().month - 1)
                target_year = col_y.number_input("Year", min_value=2025, max_value=2030, value=2026)
                
                days_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
                selected_days = st.multiselect("Repeat on:", list(days_map.keys()), default=["Mon"])
                
                if st.form_submit_button("Generate Monthly Schedule"):
                    num_days = py_calendar.monthrange(target_year, target_month)[1]
                    all_days = [datetime(target_year, target_month, d) for d in range(1, num_days + 1)]
                    day_indices = [days_map[d] for d in selected_days]
                    dates_to_schedule = [d for d in all_days if d.weekday() in day_indices]

            if dates_to_schedule:
                successes, errors = 0, []
                for d in dates_to_schedule:
                    start_dt = datetime.combine(d.date(), t_start)
                    end_dt = datetime.combine(d.date(), t_end)
                    err = check_conflicts(t_id, r_id, start_dt, end_dt)
                    if err:
                        errors.append(f"{d.strftime('%b %d')}: {err}")
                    else:
                        st.session_state.schedule.append({
                            "class_code": class_code,
                            "teacher_id": t_id, "room_id": r_id, "start": start_dt, "end": end_dt,
                            "room_name": st.session_state.rooms_df[st.session_state.rooms_df['ID']==r_id]['Name'].values[0]
                        })
                        successes += 1
                if successes: st.success(f"Added {successes} classes for {class_code}.")
                if errors: st.error(f"Conflicts found on {len(errors)} dates.")
                for e in errors: st.caption(e)

    # --- TAB 2: VISUAL TIMETABLE ---
    with tab2:
        st.subheader("📅 Weekly Timetable View")
        v_c1, v_c2 = st.columns([1, 2])
        v_mode = v_c1.radio("Filter Calendar By:", ["Teacher", "Room"], horizontal=True)
        
        if v_mode == "Teacher":
            sid = v_c2.selectbox("Select Teacher", st.session_state.teachers_df['ID'].tolist(), format_func=lambda x: st.session_state.teachers_df[st.session_state.teachers_df['ID']==x]['Name'].values[0])
            cal_events = [x for x in st.session_state.schedule if x['teacher_id'] == sid]
        else:
            sid = v_c2.selectbox("Select Room", st.session_state.rooms_df['ID'].tolist(), format_func=lambda x: st.session_state.rooms_df[st.session_state.rooms_df['ID']==x]['Name'].values[0])
            cal_events = [x for x in st.session_state.schedule if x['room_id'] == sid]

        events = [{
            "title": f"[{x.get('class_code', 'N/A')}] {x['room_name'] if v_mode=='Teacher' else st.session_state.teachers_df[st.session_state.teachers_df['ID']==x['teacher_id']]['Name'].values[0]}",
            "start": x['start'].isoformat(), "end": x['end'].isoformat()
        } for x in cal_events]

        st_calendar(events=events, options={
            "initialView": "timeGridWeek", 
            "slotMinTime": "08:00:00",
            "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek,timeGridDay"}
        })

    # --- TAB 3: REPORTS ---
    with tab3:
        st.subheader("📊 Workload & Occupancy Reports")
        r_today = datetime.now().date()
        r_range = st.date_input("Filter Reports by Date Range", value=(r_today, r_today + timedelta(days=30)))

        if isinstance(r_range, tuple) and len(r_range) == 2:
            s_dt = datetime.combine(r_range[0], time.min)
            e_dt = datetime.combine(r_range[1], time.max)
            r_data = [x for x in st.session_state.schedule if s_dt <= x['start'] <= e_dt]

            if r_data:
                df_r = pd.DataFrame(r_data)
                df_r['Hrs'] = (df_r['end'] - df_r['start']).dt.total_seconds() / 3600
                
                col_rep1, col_rep2 = st.columns(2)
                
                with col_rep1:
                    st.write("**Teacher Workload Summary**")
                    t_sum = df_r.groupby('teacher_id')['Hrs'].sum().reset_index()
                    t_sum = t_sum.merge(st.session_state.teachers_df[['ID', 'Name', 'Type']], left_on='teacher_id', right_on='ID')
                    st.dataframe(t_sum[['Name', 'Type', 'Hrs']].sort_values('Hrs', ascending=False), hide_index=True, use_container_width=True)
                
                with col_rep2:
                    st.write("**Room Occupancy Summary**")
                    r_sum = df_r.groupby('room_id')['Hrs'].sum().reset_index()
                    r_sum = r_sum.merge(st.session_state.rooms_df[['ID', 'Name', 'Campus']], left_on='room_id', right_on='ID')
                    st.dataframe(r_sum[['Name', 'Campus', 'Hrs']].sort_values('Hrs', ascending=False), hide_index=True, use_container_width=True)
                
                st.download_button("📥 Export Range Report (CSV)", df_r.to_csv(index=False).encode('utf-8'), "report.csv")
            else:
                st.info("No data found for this range.")

    # --- TAB 4: MASTER LIST ---
    with tab4:
        st.subheader("📝 Master Schedule Editor")
        if st.session_state.schedule:
            df_m = pd.DataFrame(st.session_state.schedule)
            
            # Mappings
            t_map = dict(zip(st.session_state.teachers_df['ID'], st.session_state.teachers_df['Name']))
            rev_t_map = dict(zip(st.session_state.teachers_df['Name'], st.session_state.teachers_df['ID']))
            r_map = dict(zip(st.session_state.rooms_df['ID'], st.session_state.rooms_df['Name']))
            rev_r_map = dict(zip(st.session_state.rooms_df['Name'], st.session_state.rooms_df['ID']))
            c_map = dict(zip(st.session_state.rooms_df['ID'], st.session_state.rooms_df['Campus']))

            disp_df = pd.DataFrame({
                "Class Code": df_m['class_code'],
                "Teacher Name": df_m['teacher_id'].map(t_map),
                "Room Name": df_m['room_id'].map(r_map),
                "Campus": df_m['room_id'].map(c_map),
                "Start Time": df_m['start'],
                "End Time": df_m['end']
            })
            
            e_df = st.data_editor(
                disp_df,
                column_config={
                    "Teacher Name": st.column_config.SelectboxColumn("Teacher Name", options=list(t_map.values()), required=True),
                    "Room Name": st.column_config.SelectboxColumn("Room Name", options=list(r_map.values()), required=True),
                    "Campus": st.column_config.TextColumn("Campus", disabled=True),
                    "Start Time": st.column_config.DatetimeColumn("Start Time", format="YYYY-MM-DD HH:mm", required=True),
                    "End Time": st.column_config.DatetimeColumn("End Time", format="YYYY-MM-DD HH:mm", required=True),
                },
                num_rows="dynamic", use_container_width=True, key="m_edit"
            )
            
            c_s, c_e = st.columns(2)
            if c_s.button("💾 Save All Changes"):
                new_s = []
                for _, row in e_df.iterrows():
                    if pd.isna(row['Teacher Name']) or pd.isna(row['Room Name']): continue
                    new_s.append({
                        "class_code": row['Class Code'],
                        "teacher_id": rev_t_map[row['Teacher Name']],
                        "room_id": rev_r_map[row['Room Name']],
                        "room_name": row['Room Name'],
                        "start": row['Start Time'],
                        "end": row['End Time']
                    })
                st.session_state.schedule = new_s
                st.success("Schedule Updated!")
                st.rerun()
            
            c_e.download_button("📥 Export Master Schedule", e_df.to_csv(index=False).encode('utf-8'), "master_schedule.csv")
        else:
            st.warning("Schedule is empty.")