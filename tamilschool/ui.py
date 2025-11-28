import streamlit as st
from datetime import datetime, timezone, timedelta
from utils import VolunteerIn, SERVICES, send_confirmation_email
import db
import csv
import io
import os
from tamilschool import services


def run():
    """Run the Streamlit UI previously in `app.py`.

    This function contains the full UI logic and is called from the root `app.py`.
    """
    st.set_page_config(page_title="TamilSchool Volunteer Signup", layout="centered")

    # Ensure DB exists
    db.init_db()

    st.title("TamilSchool Volunteer — Signup")

    # Simple admin authentication using environment variable ADMIN_PASSWORD
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    if 'is_admin' not in st.session_state:
        st.session_state['is_admin'] = False

    view = st.sidebar.selectbox("Choose view", ["Signup", "Admin"])

    if view == "Signup":
        st.header("Join our weekly volunteer services")

        services_list = db.list_services()
        # build mapping id->name for confirmation text
        svc_id_to_name = {str(s['id']): s['name'] for s in services_list}

        with st.form("signup_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            phone = st.text_input("Phone (optional)")
            committed = st.checkbox("I can commit weekly")

            assigned_map = {}
            if services_list:
                st.markdown("#### Choose services and dates")
                for s in services_list:
                    with st.expander(s['name']):
                        sign = st.checkbox(f"Sign up for {s['name']}", key=f"svc_check_{s['id']}")
                        dates = db.list_service_dates(s['id'])
                        sel_dates = []
                        if dates:
                            sel_dates = st.multiselect("Select dates", options=dates, key=f"svc_dates_{s['id']}")
                        if sign:
                            assigned_map[str(s['id'])] = sel_dates
            else:
                # fallback: show static service names without scheduled dates
                st.markdown("#### Choose services")
                for name in SERVICES:
                    checked = st.checkbox(f"Sign up for {name}", key=f"svc_fallback_{name}")
                    if checked:
                        assigned_map[name] = []

            submitted = st.form_submit_button("Sign Up")

        if submitted:
            try:
                # build a friendly weekly_service string for basic validation (comma-separated service names)
                svc_names_str = None
                if assigned_map:
                    svc_names_str = ", ".join([svc_id_to_name.get(sid, sid) for sid in assigned_map.keys()])
                v = VolunteerIn(name=name, email=email, phone=phone or None, weekly_service=svc_names_str, committed_weekly=committed)
            except Exception as e:
                st.error(f"Validation error: {e}")
            else:
                try:
                    # store assigned_map (mapping service_id -> [dates])
                    added = db.add_volunteer(v.name, v.email, v.phone, assigned_map if assigned_map else None, v.committed_weekly)
                    st.success(f"Thanks {v.name}! You were registered.")
                    st.info("We have recorded your signup and sent a confirmation email if configured.")
                    # send confirmation email (best-effort) with a readable summary
                    if assigned_map:
                        assigned_dates_text = "; ".join([f"{svc_id_to_name.get(sid, sid)}: {', '.join(dates) if dates else 'No dates selected'}" for sid, dates in assigned_map.items()])
                    else:
                        assigned_dates_text = None
                    sent = send_confirmation_email(v.email, v.name, svc_names_str or 'Volunteer', assigned_dates_text)
                    if not sent:
                        st.warning("Email confirmation not sent (SMTP not configured or failed).")
                except Exception as e:
                    st.error(f"Could not register: {e}")

        st.markdown("---")
        st.write("Admins can manage services and view reports on the Admin tab (password required).")

    else:  # Admin view
        st.header("Admin — Services & Volunteers")

        if not st.session_state.get('is_admin'):
            pw = st.text_input("Admin password", type="password")
            if st.button("Login"):
                if pw == ADMIN_PASSWORD:
                    st.session_state['is_admin'] = True
                    try:
                        st.rerun()
                    except Exception:
                        st.stop()
                else:
                    st.error("Invalid admin password")

        if st.session_state.get('is_admin'):
            tabs = st.tabs(["Volunteers", "Services", "Reports", "Volunteer Assign", "Master"]) 

            with tabs[0]:
                volunteers = db.list_volunteers()
                st.write(f"Total volunteers: {len(volunteers)}")
                if volunteers:
                    # build service name lookup
                    services = db.list_services()
                    svc_lookup = {str(s['id']): s['name'] for s in services}
                    # Prepare display rows where assigned_dates mapping is a readable string
                    display_vols = []
                    for v in volunteers:
                        vcopy = v.copy()
                        ad = v.get('assigned_dates') or {}
                        if isinstance(ad, dict):
                            parts = []
                            for sid, dates in ad.items():
                                name = svc_lookup.get(str(sid), str(sid))
                                parts.append(f"{name}: {', '.join(dates) if dates else ''}")
                            vcopy['assigned_dates'] = '; '.join(parts)
                        else:
                            # fallback if list
                            vcopy['assigned_dates'] = ', '.join(ad) if ad else ''
                        display_vols.append(vcopy)
                    st.dataframe(display_vols)
                    if st.button("Export CSV"):
                        buffer = io.StringIO()
                        writer = csv.DictWriter(buffer, fieldnames=display_vols[0].keys())
                        writer.writeheader()
                        writer.writerows(display_vols)
                        st.download_button("Download CSV", data=buffer.getvalue(), file_name=f"volunteers_{datetime.now(timezone.utc).date()}.csv")

                    st.markdown("---")
                    st.subheader("Assign or change a volunteer's service")
                    emails = [v['email'] for v in volunteers]
                    sel_email = st.selectbox("Choose volunteer (by email)", [""] + emails)
                    services = db.list_services()
                    service_map = {s['name']: s['id'] for s in services}
                    new_service_name = st.selectbox("New service", [""] + list(service_map.keys()))
                    new_assigned_dates = []
                    if new_service_name:
                        s_id = service_map[new_service_name]
                        dates = db.list_service_dates(s_id)
                        if dates:
                            new_assigned_dates = st.multiselect("Assign dates (optional)", options=dates)
                    new_committed = st.checkbox("Committed weekly", value=False)
                    if st.button("Update Service"):
                        if sel_email and new_service_name:
                            ok = db.assign_service(sel_email, service_map[new_service_name], new_assigned_dates, new_committed)
                            if ok:
                                st.success("Volunteer updated")
                            else:
                                st.error("Update failed")
                        else:
                            st.warning("Select a volunteer and a new service first")
                else:
                    st.info("No volunteers registered yet.")

            with tabs[1]:
                st.subheader("Configure Services")
                with st.form("create_service"):
                    sname = st.text_input("Service name")
                    max_cap = st.number_input("Max capacity", min_value=0, value=10)
                    start = st.date_input("Start date (for Saturday schedule)")
                    end = st.date_input("End date (for Saturday schedule)")
                    create = st.form_submit_button("Create service")
                if create:
                    try:
                        sid = db.create_service(sname, int(max_cap), start.isoformat(), end.isoformat())
                        st.success(f"Service '{sname}' created (id {sid}).")
                    except Exception as e:
                        st.error(f"Could not create service: {e}")

                st.markdown("---")
                st.subheader("Existing Services")
                svc = db.list_services()
                if svc:
                    for s in svc:
                        st.write(f"**{s['name']}** — max: {s['max_capacity']} — dates: {s['start_date']} → {s['end_date']}")
                        dates = db.list_service_dates(s['id'])
                        if dates:
                            st.write("Upcoming Saturdays:", ", ".join(dates))
                        # subservices for this service
                        subs = db.list_subservices(s['id'])
                        if subs:
                            st.write("Sub-services:")
                            for sub in subs:
                                st.write(f"- {sub['name']} (max: {sub['max_capacity']})")
                        # create subservice form
                        with st.expander(f"Create sub-service for {s['name']}"):
                            with st.form(f"create_sub_{s['id']}"):
                                sub_name = st.text_input("Sub-service name", key=f"subname_{s['id']}")
                                sub_cap = st.number_input("Max capacity", min_value=0, value=5, key=f"subcap_{s['id']}")
                                sub_create = st.form_submit_button("Create sub-service")
                            if sub_create:
                                try:
                                    sid = db.create_subservice(s['id'], sub_name, int(sub_cap))
                                    st.success(f"Sub-service '{sub_name}' created (id {sid}).")
                                except Exception as e:
                                    st.error(f"Could not create sub-service: {e}")
                else:
                    st.info("No services configured yet.")

                st.markdown("---")
                st.subheader("Assign Sub-service to Volunteers")
                # select sub-service across all services
                all_subs = db.list_subservices()
                sub_map = {f"{s['name']} (service {s['service_id']})": s['id'] for s in all_subs}
                if all_subs:
                    sel_sub_label = st.selectbox("Choose sub-service", [""] + list(sub_map.keys()))
                    if sel_sub_label:
                        sel_sub_id = sub_map[sel_sub_label]
                        # try to get dates from parent service
                        # find parent service id
                        parent_id = None
                        for s in svc:
                            if any(ss['id'] == sel_sub_id for ss in db.list_subservices(s['id'])):
                                parent_id = s['id']
                                break
                        dates = db.list_service_dates(parent_id) if parent_id else []
                        assign_date = None
                        if dates:
                            assign_date = st.selectbox("Select date to assign", dates)
                        else:
                            assign_date = st.date_input("Assign date (no scheduled Saturdays)")
                        # choose volunteers to assign
                        volunteers = db.list_volunteers()
                        emails = [v['email'] for v in volunteers]
                        chosen = st.multiselect("Select volunteers to assign", options=emails)
                        if st.button("Assign sub-service"):
                            if not chosen:
                                st.warning("Select at least one volunteer")
                            else:
                                # map emails to ids
                                vids = []
                                for e in chosen:
                                    v = db.get_volunteer_by_email(e)
                                    if v:
                                        vids.append(v['id'])
                                date_iso = assign_date if isinstance(assign_date, str) else assign_date.isoformat()
                                inserted = db.assign_subservice(sel_sub_id, date_iso, vids)
                                st.success(f"Assigned {inserted} volunteers to sub-service on {date_iso}")
                                # show current assignments
                                assigns = db.list_subservice_assignments(sel_sub_id, date_iso)
                                if assigns:
                                    st.write("Current assignments:")
                                    st.table(assigns)

            with tabs[2]:
                st.subheader("Reports")
                services = db.list_services()
                svc_map = {s['name']: s['id'] for s in services}
                sel_service = st.selectbox("Filter by service", ["All"] + list(svc_map.keys()), key="report_service_filter")
                
                # Get all available service dates
                all_service_dates = db.list_all_dates()
                sel_service_date = st.selectbox(
                    "Filter by service date",
                    [""] + all_service_dates if all_service_dates else [""],
                    key="report_service_date_filter"
                )
                
                if st.button("Generate Report"):
                    # Ensure a service date is selected
                    if not sel_service_date:
                        st.warning("Please select a service date to generate the report.")
                    else:
                        date_iso = sel_service_date
                        # Get volunteers signed up for this service date
                        vols = db.volunteers_by_date(date_iso)
                        st.write(f"Results: {len(vols)}")
                        if vols:
                            # Build lookups for services and sub-services
                            services = db.list_services()
                            svc_lookup = {str(s['id']): s['name'] for s in services}
                            subs = db.list_subservices()
                            sub_lookup = {s['id']: s['name'] for s in subs}

                            # Get existing subservice assignments for this date
                            assigns = db.list_subservice_assignments(date_iso=date_iso)
                            vol_to_subs = {}
                            vol_completed_count = {}
                            for a in assigns:
                                vid = a['volunteer_id']
                                subname = sub_lookup.get(a['subservice_id'], '')
                                vol_to_subs.setdefault(vid, []).append(subname)
                                # Count completed assignments
                                if a.get('completed', False):
                                    vol_completed_count[vid] = vol_completed_count.get(vid, 0) + 1

                            rows = []
                            for v in vols:
                                # get full volunteer record to access assigned_dates
                                full = db.get_volunteer_by_email(v['email']) or {}
                                assigned = full.get('assigned_dates') or {}
                                svc_names = []
                                if isinstance(assigned, dict):
                                    for sid, dates in assigned.items():
                                        try:
                                            if date_iso in dates:
                                                svc_names.append(svc_lookup.get(str(sid), str(sid)))
                                        except Exception:
                                            pass
                                # sub-services assigned (if any)
                                subs_for_vol = vol_to_subs.get(v['id'], [])
                                completed_count = vol_completed_count.get(v['id'], 0)
                                rows.append({
                                    'name': v['name'],
                                    'email': v['email'],
                                    'services': ', '.join(svc_names) if svc_names else '',
                                    'subservices': ', '.join(subs_for_vol) if subs_for_vol else '',
                                    'no_of_completed_services': completed_count
                                })

                            st.dataframe(rows)
                            # CSV export
                            buf = io.StringIO()
                            writer = csv.DictWriter(buf, fieldnames=['name', 'email', 'services', 'subservices', 'no_of_completed_services'])
                            writer.writeheader()
                            writer.writerows(rows)
                            st.download_button("Download CSV", data=buf.getvalue(), file_name=f"report_{date_iso}.csv")
                
                st.divider()
                st.markdown("### Volunteer Fee Eligibility Report")
                st.write("View volunteers by number of sub-services completed and fee eligibility status.")
                
                if st.button("Generate Eligibility Report"):
                    # Get all volunteers across all dates
                    all_vols = db.list_volunteers()
                    subs = db.list_subservices()

                    if not all_vols:
                        st.info("No volunteers in the system.")
                    else:
                        # Get all assignments across all dates
                        all_assigns = db.list_subservice_assignments()
                        # Track unique assigned sub-services, service dates, and completed count per volunteer
                        vol_subservice_set = {}
                        vol_service_dates = {}
                        vol_completed_count = {}
                        for a in all_assigns:
                            vid = a['volunteer_id']
                            subservice_id = a['subservice_id']
                            date_assigned = a.get('date')
                            if vid not in vol_subservice_set:
                                vol_subservice_set[vid] = set()
                            vol_subservice_set[vid].add(subservice_id)
                            if vid not in vol_service_dates:
                                vol_service_dates[vid] = set()
                            if date_assigned:
                                vol_service_dates[vid].add(date_assigned)
                            # Count completed assignments
                            if a.get('completed', False):
                                vol_completed_count[vid] = vol_completed_count.get(vid, 0) + 1
                        # Build eligibility report rows
                        report_rows = []
                        for v in all_vols:
                            num_completed = len(vol_subservice_set.get(v['id'], set()))
                            dates = sorted(list(vol_service_dates.get(v['id'], set())))
                            dates_str = ', '.join(dates) if dates else ''
                            completed_count = vol_completed_count.get(v['id'], 0)
                            eligible = "Eligible for Vol. Fees return" if num_completed >= 3 else ""
                            report_rows.append({
                                'name': v['name'],
                                'email': v['email'],
                                'phone': v['phone'] or '',
                                'no_of_subservices': num_completed,
                                'no_of_completed_services': completed_count,
                                'service_dates': dates_str,
                                'eligibility': eligible
                            })

                        # Sort by number of sub-services (descending)
                        report_rows.sort(key=lambda x: x['no_of_subservices'], reverse=True)

                        st.write(f"Total Volunteers: {len(report_rows)}")
                        st.dataframe(report_rows, use_container_width=True)

                        # CSV export
                        buf = io.StringIO()
                        writer = csv.DictWriter(buf, fieldnames=['name', 'email', 'phone', 'no_of_subservices', 'no_of_completed_services', 'service_dates', 'eligibility'])
                        writer.writeheader()
                        writer.writerows(report_rows)
                        st.download_button("Download Eligibility Report CSV", data=buf.getvalue(), file_name=f"eligibility_report_{datetime.now(timezone.utc).date()}.csv")

            # Volunteer Assign tab: show volunteers for a selected service date and allow assigning sub-services
            with tabs[3]:
                st.subheader("Volunteer Assign")
                st.write("Search by service date to view volunteers and assign sub-services to them.")
                
                # Get all available service dates
                all_service_dates = db.list_all_dates()
                sel_service_date = st.selectbox(
                    "Select service date",
                    [""] + all_service_dates if all_service_dates else [""],
                    key="vol_assign_service_date"
                )
                
                if sel_service_date:
                    # Get volunteers who have this date in their assigned_dates
                    vols_for_date = db.volunteers_by_date(sel_service_date)
                    st.write(f"**Volunteers for service date {sel_service_date}: {len(vols_for_date)}**")
                    
                    if vols_for_date:
                        # Get available sub-services
                        subs = db.list_subservices()
                        if not subs:
                            st.info("No sub-services configured yet. Create sub-services in the Services tab first.")
                        else:
                            sub_map = {f"{s['name']} (service {s['service_id']})": s['id'] for s in subs}
                            sub_names = list(sub_map.keys())
                            sub_id_to_name = {s['id']: f"{s['name']} (service {s['service_id']})" for s in subs}
                            
                            # Get all existing assignments for this date to show as defaults
                            all_assigns_for_date = db.list_subservice_assignments(date_iso=sel_service_date)
                            # Map volunteer_id -> latest assignment dict (if any)
                            vol_assign_map = {a['volunteer_id']: a for a in all_assigns_for_date}

                            # Display volunteers in a clean table-like form with aligned controls
                            st.markdown("#### Assign Sub-Services to Volunteers")

                            # Build sub-service options
                            sub_options = [""] + sub_names

                            with st.form("assign_subservices_form"):
                                # Header row
                                hdr_cols = st.columns([2, 2, 2.5, 1.5])
                                hdr_cols[0].markdown("**Name**")
                                hdr_cols[1].markdown("**Email**")
                                hdr_cols[2].markdown("**Sub-Service**")
                                hdr_cols[3].markdown("**Completed**")
                                st.divider()

                                # Collect selections in local dicts (Streamlit returns widget values on submit)
                                sel_by_vol = {}
                                comp_by_vol = {}

                                for vol in vols_for_date:
                                    cols = st.columns([2, 2, 2.5, 1.5])
                                    cols[0].write(vol.get('name', ''))
                                    cols[1].write(vol.get('email', ''))

                                    existing = vol_assign_map.get(vol['id'])
                                    default_idx = 0
                                    if existing:
                                        default_label = sub_id_to_name.get(existing['subservice_id'], "")
                                        if default_label in sub_names:
                                            default_idx = sub_names.index(default_label) + 1

                                    sel_key = f"assign_sub_{sel_service_date}_{vol['id']}"
                                    comp_key = f"assign_comp_{sel_service_date}_{vol['id']}"

                                    sel_choice = cols[2].selectbox(
                                        "Sub-service",
                                        sub_options,
                                        index=default_idx,
                                        key=sel_key,
                                        label_visibility="collapsed",
                                    )

                                    comp_default = bool(existing.get('completed')) if existing else False
                                    # Provide a non-empty label for accessibility, hide it visually
                                    comp_choice = cols[3].checkbox(
                                        f"Completed for {vol.get('name', '')}",
                                        value=comp_default,
                                        key=comp_key,
                                        label_visibility="collapsed",
                                    )

                                    sel_by_vol[vol['id']] = sel_choice
                                    comp_by_vol[vol['id']] = comp_choice

                                submitted_assignments = st.form_submit_button("Save Assignments")

                            if submitted_assignments:
                                # Build mapping: subservice_id -> list of volunteer ids to assign
                                assigns_by_sub = {}
                                for vol in vols_for_date:
                                    vid = vol['id']
                                    sel_label = sel_by_vol.get(vid) or ""
                                    if sel_label:
                                        sel_sub_id = sub_map.get(sel_label)
                                        if sel_sub_id:
                                            assigns_by_sub.setdefault(sel_sub_id, []).append(vid)

                                inserted_total = 0
                                # Perform assignment per sub-service to avoid repeated deletes/insert conflicts
                                for sub_id, vids in assigns_by_sub.items():
                                    try:
                                        inserted = db.assign_subservice(sub_id, sel_service_date, vids)
                                        inserted_total += inserted
                                    except Exception as e:
                                        st.error(f"Assignment failed for sub-service id {sub_id}: {e}")

                                # Update completion flags: fetch all assignments for the date once
                                try:
                                    all_assigns_now = db.list_subservice_assignments(date_iso=sel_service_date)
                                except Exception:
                                    all_assigns_now = []

                                # Map volunteer_id -> desired completed state (from form)
                                desired_completed_map = {vol['id']: bool(comp_by_vol.get(vol['id'], False)) for vol in vols_for_date}

                                # Apply completed flag to assignments as needed
                                updated_count = 0
                                for a in all_assigns_now:
                                    vid = a['volunteer_id']
                                    desired = desired_completed_map.get(vid, False)
                                    if a.get('completed', False) != desired:
                                        try:
                                            ok = db.mark_assignment_completed(a['id'], desired)
                                            if ok:
                                                updated_count += 1
                                        except Exception:
                                            st.error(f"Could not update completion for volunteer id {vid}")

                                st.success(f"Saved assignments (added {inserted_total} new, updated {updated_count} completion flags).")
                                # refresh view
                                try:
                                    st.rerun()
                                except Exception:
                                    st.stop()
                    else:
                        st.info("No volunteers assigned to this service date.")

            with tabs[4]:
                st.subheader("Master — Edit / Delete Records")

                st.markdown("### Create New Records")
                create_col1, create_col2, create_col3 = st.columns(3)
                
                with create_col1:
                    st.markdown("**Create Volunteer**")
                    with st.form("master_create_volunteer"):
                        crv_name = st.text_input("Name")
                        crv_email = st.text_input("Email")
                        crv_phone = st.text_input("Phone (optional)")
                        crv_committed = st.checkbox("Committed weekly")
                        crv_submit = st.form_submit_button("Create Volunteer")
                    if crv_submit:
                        if crv_name and crv_email:
                            try:
                                result = db.add_volunteer(crv_name, crv_email, crv_phone if crv_phone else None, None, crv_committed)
                                st.success(f"Volunteer '{crv_name}' created")
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Name and Email are required")
                
                with create_col2:
                    st.markdown("**Create Service**")
                    with st.form("master_create_service"):
                        crs_name = st.text_input("Service name")
                        crs_cap = st.number_input("Max capacity", min_value=0, value=10)
                        crs_start = st.date_input("Start date")
                        crs_end = st.date_input("End date")
                        crs_submit = st.form_submit_button("Create Service")
                    if crs_submit:
                        if crs_name:
                            try:
                                db.create_service(crs_name, int(crs_cap), crs_start.isoformat(), crs_end.isoformat())
                                st.success(f"Service '{crs_name}' created")
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Service name is required")
                
                with create_col3:
                    st.markdown("**Create Sub-Service**")
                    services = db.list_services()
                    svc_map_create = {s['name']: s['id'] for s in services}
                    with st.form("master_create_subservice"):
                        crsub_svc = st.selectbox("Parent Service", options=list(svc_map_create.keys()) if svc_map_create else [])
                        crsub_name = st.text_input("Sub-service name")
                        crsub_cap = st.number_input("Max capacity", min_value=0, value=5)
                        crsub_submit = st.form_submit_button("Create Sub-Service")
                    if crsub_submit:
                        if crsub_svc and crsub_name:
                            try:
                                db.create_subservice(svc_map_create[crsub_svc], crsub_name, int(crsub_cap))
                                st.success(f"Sub-service '{crsub_name}' created")
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Service and Sub-service name are required")
                
                st.divider()
                st.markdown("### Edit / Delete Records")

                st.markdown("**Volunteers**")
                all_vols = db.list_volunteers()
                vol_map = {f"{v['name']} <{v['email']}>": v['id'] for v in all_vols}
                sel_vol_label = st.selectbox("Select volunteer to edit", [""] + list(vol_map.keys()))
                if sel_vol_label:
                    vid = vol_map[sel_vol_label]
                    vol = None
                    for v in all_vols:
                        if v['id'] == vid:
                            vol = v
                            break
                    if vol:
                        with st.form(f"edit_vol_{vid}"):
                            new_name = st.text_input("Name", value=vol['name'])
                            new_email = st.text_input("Email", value=vol['email'])
                            new_phone = st.text_input("Phone", value=vol.get('phone') or '')
                            new_committed = st.checkbox("Committed weekly", value=bool(vol.get('committed_weekly')))
                            st.write("To change service assignments, use the Assign or change a volunteer's service section in the Volunteers tab.")
                            save = st.form_submit_button("Save Volunteer")
                            if save:
                                ok = db.update_volunteer(vid, new_name, new_email, new_phone if new_phone else None, vol.get('assigned_dates'), new_committed)
                                if ok:
                                    st.success("Volunteer updated")
                                else:
                                    st.error("Update failed or no changes made")
                    if st.checkbox("Confirm delete volunteer", key=f"confirm_del_vol_{vid}"):
                        if st.button("Delete Volunteer", key=f"del_vol_{vid}"):
                            ok = db.delete_volunteer(vid)
                            if ok:
                                st.success("Volunteer deleted")
                            else:
                                st.error("Delete failed")

                st.markdown("---")
                st.markdown("**Services**")
                services = db.list_services()
                svc_map = {f"{s['name']} (id:{s['id']})": s['id'] for s in services}
                sel_svc_label = st.selectbox("Select service to edit", [""] + list(svc_map.keys()))
                if sel_svc_label:
                    sid = svc_map[sel_svc_label]
                    svc = None
                    for s in services:
                        if s['id'] == sid:
                            svc = s
                            break
                    if svc:
                        with st.form(f"edit_svc_{sid}"):
                            svc_name = st.text_input("Service name", value=svc['name'])
                            svc_cap = st.number_input("Max capacity", min_value=0, value=svc.get('max_capacity') or 0)
                            svc_start = st.date_input("Start date", value=datetime.fromisoformat(svc['start_date']).date() if svc.get('start_date') else datetime.now(timezone.utc).date())
                            svc_end = st.date_input("End date", value=datetime.fromisoformat(svc['end_date']).date() if svc.get('end_date') else datetime.now(timezone.utc).date())
                            svc_save = st.form_submit_button("Save Service")
                            if svc_save:
                                ok = db.update_service(sid, svc_name, int(svc_cap), svc_start.isoformat(), svc_end.isoformat())
                                if ok:
                                    st.success("Service updated")
                                else:
                                    st.error("Update failed")
                    if st.checkbox("Confirm delete service (this removes sub-services & dates)", key=f"confirm_del_svc_{sid}"):
                        if st.button("Delete Service", key=f"del_svc_{sid}"):
                            ok = db.delete_service(sid)
                            if ok:
                                st.success("Service deleted")
                            else:
                                st.error("Delete failed")

                st.markdown("---")
                st.markdown("**Sub-Services**")
                subs = db.list_subservices()
                sub_map = {f"{s['name']} (id:{s['id']}, service:{s['service_id']})": s['id'] for s in subs}
                sel_sub_label = st.selectbox("Select sub-service to edit", [""] + list(sub_map.keys()))
                if sel_sub_label:
                    sub_id = sub_map[sel_sub_label]
                    sub = None
                    for s in subs:
                        if s['id'] == sub_id:
                            sub = s
                            break
                    if sub:
                        with st.form(f"edit_sub_{sub_id}"):
                            sub_name = st.text_input("Sub-service name", value=sub['name'])
                            sub_cap = st.number_input("Max capacity", min_value=0, value=sub.get('max_capacity') or 0)
                            sub_save = st.form_submit_button("Save Sub-service")
                            if sub_save:
                                ok = db.update_subservice(sub_id, sub_name, int(sub_cap))
                                if ok:
                                    st.success("Sub-service updated")
                                else:
                                    st.error("Update failed")
                    if st.checkbox("Confirm delete sub-service (this removes assignments)", key=f"confirm_del_sub_{sub_id}"):
                        if st.button("Delete Sub-service", key=f"del_sub_{sub_id}"):
                            ok = db.delete_subservice(sub_id)
                            if ok:
                                st.success("Sub-service deleted")
                            else:
                                st.error("Delete failed")

            st.markdown("---")
            if st.button("Logout Admin"):
                st.session_state['is_admin'] = False
                try:
                    st.rerun()
                except Exception:
                    st.stop()
