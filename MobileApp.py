import os
import streamlit as st
import pandas as pd
import requests
from io import BytesIO

st.set_page_config(
    page_title="Toptan Telecalling Audit",
    page_icon="📞",
    layout="wide"
)


def get_secret(key: str, default: str = "") -> str:
    """Safely reads from Streamlit secrets or environment variables without crashing."""
    try:
        if key in st.secrets:
            val = st.secrets[key]
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    except Exception:
        pass
    env_val = os.getenv(key)
    if env_val and env_val.strip() != "":
        return env_val.strip()
    return default


# ==========================================
# 1. SUPABASE & ACCESS CODE SETTINGS
# ==========================================
SUPABASE_URL = get_secret("SUPABASE_URL", "https://ujfviovuuchcwmsfshri.supabase.co")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY", "sb_publishable_RiErm9ZforRqNjFH91ZHKQ_tIO0EVKc")

# നിങ്ങൾക്ക് ഷെയർ ചെയ്യാൻ കൊടുക്കാവുന്ന Access Codes (പിന്നീട് എളുപ്പത്തിൽ മാറ്റാം)
ACCESS_CODES = {
    "TOPTAN2026": {"name": "Viewer Access", "role": "viewer"},
    "MANAGER4": {"name": "Branch Manager View", "role": "viewer"},
    "ADMIN999": {"name": "Admin Access", "role": "admin"},
}

BRANCHES = [
    "Ayikkarapadi",
    "Karuvarakundu",
    "Pandalur",
    "Valluvambram"
]

# Session State Defaults
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "role" not in st.session_state:
    st.session_state.role = "viewer"
if "records_df" not in st.session_state:
    st.session_state.records_df = None
if "deleted_cols" not in st.session_state:
    st.session_state.deleted_cols = []


# ==========================================
# 2. SUPABASE REST HELPERS
# ==========================================
def supabase_ready() -> bool:
    return bool(
        SUPABASE_URL
        and SUPABASE_ANON_KEY
        and "YOUR_SUPABASE_ANON_KEY_HERE" not in SUPABASE_ANON_KEY
    )


def get_headers() -> dict:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def fetch_branches_map() -> dict:
    if not supabase_ready():
        return {}
    try:
        url = f"{SUPABASE_URL}/rest/v1/branches?select=id,name"
        r = requests.get(url, headers=get_headers(), timeout=15)
        if r.status_code == 200:
            return {row["name"]: row["id"] for row in r.json()}
    except Exception:
        pass
    return {}


def save_batch_to_supabase(branch_name: str, filename: str, df: pd.DataFrame, month_label: str) -> tuple[bool, str]:
    if not supabase_ready():
        return False, "Supabase Anon Key ചേർത്തിട്ടില്ല. താൽക്കാലികമായി ആപ്പിൽ മാത്രം സേവ് ആയി."

    try:
        branches_map = fetch_branches_map()
        branch_id = branches_map.get(branch_name)
        if not branch_id:
            return False, f"'{branch_name}' എന്ന ബ്രാഞ്ച് Supabase-ൽ കണ്ടെത്താനായില്ല."

        batch_payload = {
            "branch_id": branch_id,
            "filename": f"[{month_label}] {filename}" if month_label != "Unspecified" else filename,
            "record_count": int(len(df)),
            "status": "active"
        }
        r_batch = requests.post(
            f"{SUPABASE_URL}/rest/v1/upload_batches",
            headers=get_headers(),
            json=batch_payload,
            timeout=20
        )
        if r_batch.status_code not in (200, 201):
            return False, f"Upload batch save failed: {r_batch.text}"

        batch_id = r_batch.json()[0]["id"]

        requests.patch(
            f"{SUPABASE_URL}/rest/v1/branches?id=eq.{branch_id}",
            headers=get_headers(),
            json={"active_upload_id": batch_id},
            timeout=15
        )

        rows_to_insert = []
        for idx, row in df.iterrows():
            clean_dict = {}
            for col in df.columns:
                val = row[col]
                clean_dict[str(col)] = None if pd.isna(val) else str(val)

            clean_dict["_branch"] = branch_name
            clean_dict["_month"] = month_label

            rows_to_insert.append({
                "upload_id": batch_id,
                "branch_id": branch_id,
                "row_number": int(idx) + 1,
                "phone_normalized": None,
                "lead_status": None,
                "raw_data": clean_dict
            })

        chunk_size = 200
        for i in range(0, len(rows_to_insert), chunk_size):
            chunk = rows_to_insert[i:i + chunk_size]
            r_rec = requests.post(
                f"{SUPABASE_URL}/rest/v1/call_records",
                headers=get_headers(),
                json=chunk,
                timeout=30
            )
            if r_rec.status_code not in (200, 201):
                return False, f"Records insert failed: {r_rec.text}"

        return True, f"Supabase-ൽ വിജയകരമായി സേവ് ചെയ്തു ({len(df)} rows)!"
    except Exception as e:
        return False, f"Supabase error: {e}"


def load_records_from_supabase() -> pd.DataFrame | None:
    if not supabase_ready():
        return None
    try:
        url = f"{SUPABASE_URL}/rest/v1/call_records?select=id,branch_id,raw_data,created_at&order=id.asc&limit=5000"
        r = requests.get(url, headers=get_headers(), timeout=20)
        if r.status_code != 200:
            return None

        data = r.json()
        if not data:
            return None

        branches_map = fetch_branches_map()
        id_to_branch = {v: k for k, v in branches_map.items()}

        flattened = []
        for item in data:
            raw = item.get("raw_data") or {}
            if not isinstance(raw, dict):
                raw = {}
            row_obj = dict(raw)
            if "Branch" not in row_obj:
                row_obj["Branch"] = raw.get("_branch") or id_to_branch.get(item.get("branch_id"), "Unknown")
            if "Month" not in row_obj and raw.get("_month"):
                row_obj["Month"] = raw.get("_month")
            row_obj.pop("_branch", None)
            row_obj.pop("_month", None)
            flattened.append(row_obj)

        return pd.DataFrame(flattened)
    except Exception:
        return None


# ==========================================
# 3. STYLING
# ==========================================
st.markdown("""
<style>
.main-title {
    font-size: 32px;
    font-weight: 800;
    color: #E0A84B;
    margin-bottom: 0;
}
.sub-title {
    font-size: 16px;
    color: #9CA3AF;
    margin-top: 2px;
}
.role-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 700;
    background-color: #1F2937;
    color: #E0A84B;
    border: 1px solid #374151;
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 4. LOGIN SCREEN (USERNAME + ACCESS CODE)
# ==========================================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">TOPTAN FINISTORE</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Telecalling Audit System — Login</div>', unsafe_allow_html=True)
    st.divider()

    col_left, col_center, col_right = st.columns([1, 1.4, 1])
    with col_center:
        st.subheader("ലോഗിൻ ചെയ്യുക")
        st.caption("നിങ്ങളുടെ പേരും നിങ്ങൾക്ക് ലഭിച്ച Access Code-ഉം നൽകുക.")

        with st.form("login_form"):
            username_input = st.text_input("യൂസർനെയിം / പേര് (Username / Name)", placeholder="ഉദാ: Arun / Manager")
            code_input = st.text_input("ആക്സസ് കോഡ് (Access Code)", type="password", placeholder="Access Code നൽകുക")
            submitted = st.form_submit_button("പ്രവേശിക്കുക (Login)", use_container_width=True)

            if submitted:
                clean_name = username_input.strip()
                clean_code = code_input.strip()

                if not clean_name:
                    st.error("ദയവായി നിങ്ങളുടെ പേര് / യൂസർനെയിം നൽകുക.")
                elif clean_code not in ACCESS_CODES:
                    st.error("തെറ്റായ Access Code! ശരിയായ കോഡ് നൽകുക.")
                else:
                    code_info = ACCESS_CODES[clean_code]
                    st.session_state.logged_in = True
                    st.session_state.user_name = clean_name
                    st.session_state.role = code_info["role"]

                    if st.session_state.records_df is None:
                        db_df = load_records_from_supabase()
                        if db_df is not None:
                            st.session_state.records_df = db_df

                    st.rerun()

        st.info("Viewer Code: `TOPTAN2026` | Admin Code: `ADMIN999`")
    st.stop()


# ==========================================
# 5. MAIN APP (AFTER LOGIN)
# ==========================================
is_admin = (st.session_state.role == "admin")

if st.session_state.records_df is None and supabase_ready():
    db_df = load_records_from_supabase()
    if db_df is not None:
        st.session_state.records_df = db_df

st.sidebar.markdown("## TOPTAN FINISTORE")
st.sidebar.caption("Telecalling Audit System")
st.sidebar.markdown(
    f"**User:** {st.session_state.user_name}<br>"
    f"<span class='role-badge'>{'ADMIN (Full Control)' if is_admin else 'VIEWER (View Only)'}</span>",
    unsafe_allow_html=True
)

if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.role = "viewer"
    st.rerun()

st.sidebar.divider()

if is_admin:
    menu_items = [
        "Telecaller Audit",
        "Dashboard",
        "Excel Upload & Columns",
        "All Customer Data",
        "Duplicate Detection",
        "Branch Reports"
    ]
else:
    menu_items = [
        "Telecaller Audit",
        "Dashboard",
        "All Customer Data",
        "Duplicate Detection",
        "Branch Reports"
    ]

page = st.sidebar.radio("MAIN MENU", menu_items)

st.sidebar.divider()
st.sidebar.markdown("### Branches")
for b in BRANCHES:
    st.sidebar.write("📍", b)

st.markdown('<div class="main-title">TOPTAN FINISTORE</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-title">Telecalling Audit System • Department: Telecalling • '
    f'Mode: {"Admin Control" if is_admin else "View-Only"}</div>',
    unsafe_allow_html=True
)
st.divider()


def get_working_df() -> pd.DataFrame | None:
    df = st.session_state.records_df
    if df is None or df.empty:
        return None
    df = df.copy()
    cols_to_drop = [c for c in st.session_state.deleted_cols if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    return df


df = get_working_df()

if page == "Telecaller Audit":
    st.title("Telecaller Audit — Call History & Details")

    if df is None:
        st.info("നിലവിൽ ഡാറ്റ ലഭ്യമല്ല. Admin-ന് 'Excel Upload & Columns' പേജിലൂടെ Excel അപ്‌ലോഡ് ചെയ്യാം.")
    else:
        filtered = df.copy()

        month_candidates = [c for c in filtered.columns if "month" in c.lower() or "date" in c.lower()]
        if month_candidates:
            m_col = st.selectbox("Month / Date Column തിരഞ്ഞെടുക്കുക", ["None"] + month_candidates)
            if m_col != "None":
                months = ["All"] + sorted(filtered[m_col].dropna().astype(str).unique().tolist())
                sel_month = st.selectbox("മാസം / തീയതി തിരഞ്ഞെടുക്കുക (ഉദാ: October / November)", months)
                if sel_month != "All":
                    filtered = filtered[filtered[m_col].astype(str) == sel_month]

        caller_candidates = [
            c for c in filtered.columns
            if any(k in c.lower() for k in ["caller", "telecaller", "executive", "agent", "staff", "name"])
        ]
        default_idx = 0
        if not caller_candidates:
            caller_candidates = list(filtered.columns)

        caller_col = st.selectbox(
            "Telecaller പേര് / കോഡ് അടങ്ങുന്ന Column തിരഞ്ഞെടുക്കുക",
            options=list(filtered.columns),
            index=list(filtered.columns).index(caller_candidates[default_idx]) if caller_candidates else 0
        )

        callers_list = ["All Telecallers"] + sorted(
            filtered[caller_col].dropna().astype(str).str.strip().unique().tolist()
        )
        selected_caller = st.selectbox(
            "Telecaller-നെ തിരഞ്ഞെടുക്കുക (ഉദാ: അശ്വതി / Code)",
            options=callers_list
        )

        if selected_caller != "All Telecallers":
            caller_df = filtered[filtered[caller_col].astype(str).str.strip() == selected_caller]
        else:
            caller_df = filtered

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Calls / Rows", len(caller_df))
        m2.metric("Telecallers Count", caller_df[caller_col].nunique())
        m3.metric("Visible Columns", len(caller_df.columns))

        st.subheader("Telecaller Summary (ആകെ വിളിച്ച കോളുകൾ)")
        summary_df = (
            filtered.groupby(caller_col, dropna=False)
            .size()
            .reset_index(name="Total Calls")
            .sort_values("Total Calls", ascending=False)
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        st.subheader(f"Full Call Details — {selected_caller}")
        st.dataframe(caller_df, use_container_width=True, hide_index=True)

elif page == "Dashboard":
    st.title("Dashboard Overview")

    if df is None:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Branches", "4")
        c2.metric("Total Records", "0")
        c3.metric("Active Columns", "0")
        st.info("ഡാറ്റ കാണാൻ Excel അപ്‌ലോഡ് ചെയ്യുക.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Records", len(df))
        c2.metric("Visible Columns", len(df.columns))
        c3.metric("Deleted Columns", len(st.session_state.deleted_cols))

        if "Branch" in df.columns:
            st.subheader("Branch-wise Record Summary")
            b_sum = df.groupby("Branch").size().reset_index(name="Total Records")
            st.dataframe(b_sum, use_container_width=True, hide_index=True)

        st.subheader("Data Preview (First 25 Rows)")
        st.dataframe(df.head(25), use_container_width=True, hide_index=True)

elif page == "Excel Upload & Columns":
    if not is_admin:
        st.error("ഈ പേജ് Admin-ന് മാത്രമുള്ളതാണ്.")
        st.stop()

    st.title("Excel Upload & Dynamic Column Control")
    st.caption("ഏത് Excel ഫയലും അപ്‌ലോഡ് ചെയ്യാം. ആവശ്യമില്ലാത്ത കോളങ്ങൾ (Timestamp, Field A, Field B മുതലായവ) ഇവിടെ ഡിലീറ്റ് ചെയ്യാം.")

    col_b, col_m = st.columns(2)
    with col_b:
        branch = st.selectbox("Branch തിരഞ്ഞെടുക്കുക", BRANCHES)
    with col_m:
        month_label = st.selectbox(
            "Month / Batch Label",
            ["Unspecified", "October", "November", "December", "January", "February", "March"]
        )

    uploaded_file = st.file_uploader(
        "Upload Telecalling Excel / CSV File",
        type=["xlsx", "xls", "csv"]
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".csv"):
                new_df = pd.read_csv(uploaded_file)
            else:
                new_df = pd.read_excel(uploaded_file)

            new_df.columns = new_df.columns.astype(str).str.strip()
            new_df["Branch"] = branch
            if month_label != "Unspecified" and "Month" not in new_df.columns:
                new_df["Month"] = month_label

            st.success(f"ഫയൽ വായിച്ചു: {uploaded_file.name} ({len(new_df)} rows, {len(new_df.columns)} columns)")

            st.subheader("1. ആവശ്യമില്ലാത്ത Columns Delete ചെയ്യുക")
            cols_to_remove = st.multiselect(
                "Delete ചെയ്യേണ്ട Columns തിരഞ്ഞെടുക്കുക (ഉദാ: Timestamp, Field A, Field B)",
                options=list(new_df.columns),
                default=[c for c in new_df.columns if "timestamp" in c.lower()]
            )

            if st.button("Selected Columns ഒഴിവാക്കി Preview കാണുക"):
                st.session_state.deleted_cols = list(set(st.session_state.deleted_cols + cols_to_remove))

            preview_df = new_df.drop(columns=[c for c in cols_to_remove if c in new_df.columns])
            st.dataframe(preview_df.head(20), use_container_width=True, hide_index=True)

            st.subheader("2. ഡാറ്റ Save ചെയ്യുക")
            c_save1, c_save2 = st.columns(2)

            with c_save1:
                if st.button("ഈ ഡാറ്റ Replace ചെയ്ത് Active ആക്കുക (App + Supabase)", type="primary", use_container_width=True):
                    st.session_state.records_df = preview_df
                    ok, msg = save_batch_to_supabase(branch, uploaded_file.name, preview_df, month_label)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

            with c_save2:
                if st.button("നിലവിലുള്ള ഡാറ്റയോട് ചേർക്കുക (Append)", use_container_width=True):
                    if st.session_state.records_df is None:
                        st.session_state.records_df = preview_df
                    else:
                        st.session_state.records_df = pd.concat(
                            [st.session_state.records_df, preview_df],
                            ignore_index=True
                        )
                    ok, msg = save_batch_to_supabase(branch, uploaded_file.name, preview_df, month_label)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

        except Exception as e:
            st.error(f"ഫയൽ വായിക്കാൻ കഴിഞ്ഞില്ല: {e}")

    current_df = get_working_df()
    if current_df is not None:
        st.divider()
        st.subheader("നിലവിലുള്ള ഡാറ്റയിലെ Columns Manage ചെയ്യുക")
        more_delete = st.multiselect(
            "നിലവിലുള്ള ടേബിളിൽ നിന്നും Delete ചെയ്യേണ്ട Columns",
            options=list(current_df.columns),
            key="manage_delete_multiselect"
        )
        if st.button("Delete Selected Columns Now"):
            st.session_state.deleted_cols = list(set(st.session_state.deleted_cols + more_delete))
            st.rerun()

        if st.session_state.deleted_cols:
            st.write("Deleted Columns:", st.session_state.deleted_cols)
            if st.button("Deleted Columns തിരികെ കൊണ്ടുവരിക (Restore All Columns)"):
                st.session_state.deleted_cols = []
                st.rerun()

elif page == "All Customer Data":
    st.title("All Customer & Telecalling Records")

    if df is None:
        st.warning("ഡാറ്റ ലഭ്യമല്ല.")
    else:
        search_q = st.text_input("Search (ഏത് പേര്, നമ്പർ, സ്റ്റാറ്റസ്, നോട്ട് എന്നിവയും തിരയാം)")
        view_df = df.copy()
        if search_q.strip():
            mask = view_df.apply(
                lambda row: row.astype(str).str.contains(search_q.strip(), case=False, na=False).any(),
                axis=1
            )
            view_df = view_df[mask]

        st.metric("Matching Records", len(view_df))
        st.dataframe(view_df, use_container_width=True, hide_index=True)

elif page == "Duplicate Detection":
    st.title("Duplicate Phone Number Detection")

    if df is None:
        st.warning("ഡാറ്റ ലഭ്യമല്ല.")
    else:
        phone_col = st.selectbox("Phone Number Column തിരഞ്ഞെടുക്കുക", list(df.columns))
        dups = df[
            df[phone_col].notna()
            & df[phone_col].astype(str).str.strip().ne("")
            & df[phone_col].astype(str).duplicated(keep=False)
        ].sort_values(by=phone_col)

        st.metric("Duplicate Rows", len(dups))
        if len(dups) > 0:
            st.dataframe(dups, use_container_width=True, hide_index=True)
        else:
            st.success("Duplicate നമ്പറുകൾ കണ്ടെത്തിയില്ല.")

elif page == "Branch Reports":
    st.title("Branch Reports & Export")

    if df is None:
        st.warning("ഡാറ്റ ലഭ്യമല്ല.")
    else:
        if "Branch" in df.columns:
            branches_avail = sorted(df["Branch"].dropna().astype(str).unique().tolist())
            if not branches_avail:
                branches_avail = BRANCHES
            sel_b = st.selectbox("Branch തിരഞ്ഞെടുക്കുക", branches_avail)
            rep_df = df[df["Branch"].astype(str) == sel_b]
        else:
            sel_b = st.selectbox("Branch Label", BRANCHES)
            rep_df = df

        st.metric("Records Count", len(rep_df))
        st.dataframe(rep_df, use_container_width=True, hide_index=True)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            rep_df.to_excel(writer, index=False, sheet_name="Audit Report")

        st.download_button(
            label="Download Excel Report (.xlsx)",
            data=output.getvalue(),
            file_name=f"Toptan_{sel_b}_Audit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

st.divider()
st.caption("Toptan Finistore | Telecalling Audit System")
