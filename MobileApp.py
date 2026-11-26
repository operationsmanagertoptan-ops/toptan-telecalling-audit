import json
import base64
import difflib
import re
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

# ==========================================
# 1. APP & PWA CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Toptan Finistore — Operations & Audit App",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Supabase Configuration (Replace with your actual Project URL & Publishable/Anon Key)
SUPABASE_URL = "https://ujfviovuuchcwmsfshri.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_RiErm9ZforRqNjFH91ZHKQ_tIO0EVKc"
SUPABASE_TABLE = "telecalling_audit_records"

# Role Access Codes (ADMIN code is intentionally NOT displayed on UI)
ADMIN_CODE = "ADMIN999"
VIEWER_CODE = "TOPTAN2026"

ACCESS_CODES = {
    ADMIN_CODE: {"role": "ADMIN", "label": "ADMIN (Full Control)"},
    VIEWER_CODE: {"role": "VIEWER", "label": "VIEWER (View Only)"},
}

BRANCHES = [
    "Ayikkarapadi",
    "Karuvarakundu",
    "Pandalur",
    "Valluvambram",
]

REPORT_TYPES = [
    "Telecalling Audit",
    "Salesman Report",
    "Excel Report",
]

# Fuzzy / Spelling mistake aliases for auto-detection
BRANCH_ALIASES = {
    "Ayikkarapadi": [
        "ayikkarapadi", "ikkarapadi", "aikkarapadi", "ayikarapadi",
        "ikarapadi", "ayikkarappadi", "ikkarappadi", "ayikkarpadi",
    ],
    "Karuvarakundu": [
        "karuvarakundu", "karuvarkund", "karuvarakund", "karuvarkundu",
        "karuvarakundu branch", "kvr", "karuvaraknd",
    ],
    "Pandalur": [
        "pandalur", "pandallur", "pandaloor", "pandlur", "pandalur branch",
    ],
    "Valluvambram": [
        "valluvambram", "valluvambaram", "valanchery_no", "valluvambram branch",
        "valluvambram", "valambaram", "valluvambrm",
    ],
}


# ==========================================
# 2. PWA MANIFEST & MODERN UI/UX STYLING
# ==========================================
def inject_pwa_and_styles():
    manifest_data = {
        "name": "Toptan Finistore Audit App",
        "short_name": "Toptan App",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0e1117",
        "theme_color": "#e59a24",
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%23e59a24'/%3E%3Ctext x='50' y='65' font-size='52' text-anchor='middle' fill='%23111' font-family='Arial'%3ETF%3C/text%3E%3C/svg%3E",
                "sizes": "192x192",
                "type": "image/svg+xml",
            }
        ],
    }
    manifest_b64 = base64.b64encode(json.dumps(manifest_data).encode()).decode()

    st.markdown(
        f"""
        <link rel="manifest" href="data:application/manifest+json;base64,{manifest_b64}">
        <meta name="theme-color" content="#e59a24">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="Toptan App">
        <style>
            .stApp {{
                background-color: #0e1117;
            }}
            .brand-header {{
                background: linear-gradient(135deg, #1a1f2c 0%, #12151e 100%);
                border: 1px solid rgba(229, 154, 36, 0.28);
                border-radius: 14px;
                padding: 16px 20px;
                margin-bottom: 16px;
            }}
            .brand-title {{
                color: #f5b041;
                font-size: 1.45rem;
                font-weight: 800;
                letter-spacing: 0.4px;
                margin: 0;
            }}
            .brand-sub {{
                color: #b8c2d4;
                font-size: 0.88rem;
                margin-top: 4px;
            }}
            .kpi-card {{
                background: #161b26;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 14px 16px;
            }}
            .kpi-label {{
                color: #9aa6bd;
                font-size: 0.78rem;
                text-transform: uppercase;
            }}
            .kpi-value {{
                color: #ffffff;
                font-size: 1.4rem;
                font-weight: 700;
                margin-top: 4px;
            }}
            div.stButton > button {{
                border-radius: 10px;
                font-weight: 600;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==========================================
# 3. PERSISTENT AUTHENTICATION (SURVIVES REFRESH)
# ==========================================
def encode_session_token(username: str, code: str) -> str:
    payload = json.dumps({"u": username, "c": code}).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def decode_session_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        u = data.get("u", "").strip()
        c = data.get("c", "").strip()
        if u and c in ACCESS_CODES:
            return u, c, ACCESS_CODES[c]
    except Exception:
        pass
    return None, None, None


def init_auth_state():
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
        st.session_state.auth_role = None
        st.session_state.auth_label = None

    if not st.session_state.auth_user:
        token = st.query_params.get("auth")
        if token:
            u, c, info = decode_session_token(token)
            if u and info:
                st.session_state.auth_user = u
                st.session_state.auth_role = info["role"]
                st.session_state.auth_label = info["label"]


def render_login_screen():
    st.markdown(
        """
        <div class="brand-header">
            <p class="brand-title">TOPTAN FINISTORE</p>
            <p class="brand-sub">Telecalling, Salesman & Excel Audit System • Installable Web App</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.subheader("ലോഗിൻ ചെയ്യുക (Login)")
        st.caption("റീഫ്രഷ് ചെയ്താലും ലോഗിൻ നിലനിൽക്കും. ആപ്പ് ഇൻസ്റ്റാൾ ചെയ്യാൻ ബ്രൗസർ മെനുവിൽ 'Add to Home Screen / Install' ഉപയോഗിക്കുക.")

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("യൂസർനെയിം / പേര് (Username / Name)", value="Arun")
            access_code = st.text_input(
                "ആക്സസ് കോഡ് (Access Code)",
                type="password",
                placeholder="Access Code നൽകുക",
            )
            submitted = st.form_submit_button("പ്രവേശിക്കുക (Login)", use_container_width=True)

        if submitted:
            clean_user = (username or "").strip()
            clean_code = (access_code or "").strip()
            if not clean_user:
                st.error("ദയവായി യൂസർനെയിം നൽകുക.")
            elif clean_code in ACCESS_CODES:
                info = ACCESS_CODES[clean_code]
                st.session_state.auth_user = clean_user
                st.session_state.auth_role = info["role"]
                st.session_state.auth_label = info["label"]
                st.query_params["auth"] = encode_session_token(clean_user, clean_code)
                st.rerun()
            else:
                st.error("തെറ്റായ Access Code. വീണ്ടും ശ്രമിക്കുക.")

        st.info(f"Viewer Access Code: **{VIEWER_CODE}** (View-Only Access)")


# ==========================================
# 4. SUPABASE REST PERSISTENCE LAYER
# ==========================================
def supabase_configured() -> bool:
    return (
        bool(SUPABASE_URL)
        and "YOUR_SUPABASE_ANON_KEY_HERE" not in SUPABASE_ANON_KEY
        and len(SUPABASE_ANON_KEY.strip()) > 20
    )


def _supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY.strip(),
        "Authorization": f"Bearer {SUPABASE_ANON_KEY.strip()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


@st.cache_data(ttl=60, show_spinner=False)
def fetch_records_from_supabase(_cache_buster: int = 0):
    if not supabase_configured():
        return [], "Supabase Publishable/Anon Key ചേർത്തിട്ടില്ല."

    endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}?select=*&order=id.desc&limit=5000"
    try:
        resp = requests.get(endpoint, headers=_supabase_headers(), timeout=20)
        if resp.status_code == 200:
            rows = resp.json()
            normalized = []
            for r in rows:
                payload = r.get("payload")
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}
                if not isinstance(payload, dict):
                    payload = {}

                item = dict(payload)
                item["_id"] = r.get("id")
                item["Branch"] = r.get("branch") or item.get("Branch") or "Unassigned"
                item["Report_Type"] = r.get("report_type") or item.get("Report_Type") or "Telecalling Audit"
                item["Uploaded_At"] = r.get("created_at") or item.get("Uploaded_At") or ""
                normalized.append(item)
            return normalized, None
        else:
            return [], f"Supabase Fetch Error ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return [], f"Supabase Connection Error: {exc}"


def clear_supabase_table():
    if not supabase_configured():
        return False, "Supabase Publishable/Anon Key ചേർത്തിട്ടില്ല."
    endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}?id=not.is.null"
    try:
        resp = requests.delete(endpoint, headers=_supabase_headers(), timeout=20)
        if resp.status_code in (200, 204):
            return True, None
        return False, f"Delete Error ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return False, f"Delete Exception: {exc}"


def save_records_to_supabase(records: list[dict], mode: str = "append"):
    if not supabase_configured():
        return False, "Supabase Publishable/Anon Key ചേർത്തിട്ടില്ല. ആപ്പിൽ മാത്രം താൽക്കാലികമായി സേവ് ആയി."

    if not records:
        return False, "സേവ് ചെയ്യാൻ ഡാറ്റ ഒന്നും ഇല്ല."

    if mode == "replace":
        ok_del, err_del = clear_supabase_table()
        if not ok_del:
            return False, f"പഴയ ഡാറ്റ മായ്ക്കുന്നതിൽ പിശക്: {err_del}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_rows = []
    for rec in records:
        clean_rec = {k: ("" if pd.isna(v) else str(v)) for k, v in rec.items() if k != "_id"}
        branch_val = clean_rec.get("Branch") or "Unassigned"
        report_type_val = clean_rec.get("Report_Type") or "Telecalling Audit"
        clean_rec["Branch"] = branch_val
        clean_rec["Report_Type"] = report_type_val
        clean_rec["Uploaded_At"] = now_str

        db_rows.append(
            {
                "branch": branch_val,
                "report_type": report_type_val,
                "payload": clean_rec,
            }
        )

    endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}"
    batch_size = 200
    try:
        for i in range(0, len(db_rows), batch_size):
            chunk = db_rows[i : i + batch_size]
            resp = requests.post(endpoint, headers=_supabase_headers(), data=json.dumps(chunk), timeout=30)
            if resp.status_code not in (200, 201):
                return (
                    False,
                    f"Supabase Insert Error ({resp.status_code}): {resp.text} "
                    f"(ടേബിൾ '{SUPABASE_TABLE}' നിലവിലുണ്ടെന്നും RLS policy അനുവദിച്ചിട്ടുണ്ടെന്നും ഉറപ്പാക്കുക).",
                )
        return True, f"{len(db_rows)} റെക്കോർഡുകൾ Supabase-ൽ വിജയകരമായി സേവ് ചെയ്തു!"
    except Exception as exc:
        return False, f"Supabase Save Exception: {exc}"


# ==========================================
# 5. FUZZY AUTO-DETECTION FOR 4 BRANCHES
# ==========================================
def detect_branch_with_typos(raw_value: str, fallback_branch: str = "Auto") -> str:
    if not raw_value or str(raw_value).strip() in ("", "nan", "None", "null"):
        return fallback_branch if fallback_branch in BRANCHES else "Unassigned"

    text = re.sub(r"[^a-zA-Z0-9\s]", " ", str(raw_value).lower())
    text = re.sub(r"\s+", " ", text).strip()

    # 1. Exact / substring alias match (handles spelling mistakes & branch names)
    for canonical, aliases in BRANCH_ALIASES.items():
        if canonical.lower() in text:
            return canonical
        for alias in aliases:
            if alias in text:
                return canonical

    # 2. Word-level fuzzy similarity match (handles typos like 'karuvarknd', 'ayikkarapdi', etc.)
    tokens = text.split()
    candidates = tokens + ([text] if len(text) <= 25 else [])
    best_branch = None
    best_score = 0.0

    for token in candidates:
        if len(token) < 4:
            continue
        for canonical, aliases in BRANCH_ALIASES.items():
            for target in [canonical.lower()] + aliases:
                ratio = difflib.SequenceMatcher(None, token, target).ratio()
                if ratio > best_score:
                    best_score = ratio
                    best_branch = canonical

    if best_branch and best_score >= 0.72:
        return best_branch

    return fallback_branch if fallback_branch in BRANCHES else "Unassigned"


def auto_split_dataframe_by_branch(df: pd.DataFrame, default_branch_mode: str = "Auto-Detect (All 4 Branches)") -> pd.DataFrame:
    working = df.copy()
    branch_col_candidates = [
        c for c in working.columns if any(k in str(c).lower() for k in ["branch", "brnch", "location", "outlet", "store", "area"])
    ]

    fallback = None if default_branch_mode.startswith("Auto-Detect") else default_branch_mode

    detected_branches = []
    for _, row in working.iterrows():
        chosen = None
        if branch_col_candidates:
            for col in branch_col_candidates:
                val = str(row.get(col, "")).strip()
                res = detect_branch_with_typos(val, fallback_branch="Unassigned")
                if res in BRANCHES:
                    chosen = res
                    break
        if not chosen:
            row_blob = " ".join(str(v) for v in row.values if pd.notna(v))
            chosen = detect_branch_with_typos(row_blob, fallback_branch=fallback or "Unassigned")
        detected_branches.append(chosen)

    working["Branch"] = detected_branches
    return working


# ==========================================
# 6. DATA LOADING & REFRESH HELPERS
# ==========================================
def load_app_data(force_refresh: bool = False):
    if "cache_buster" not in st.session_state:
        st.session_state.cache_buster = 0
    if force_refresh:
        st.session_state.cache_buster += 1
        fetch_records_from_supabase.clear()

    if "local_records" not in st.session_state:
        st.session_state.local_records = []

    rows, err = fetch_records_from_supabase(st.session_state.cache_buster)
    if rows:
        st.session_state.local_records = rows
        return pd.DataFrame(rows), None
    return pd.DataFrame(st.session_state.local_records), err


def to_clean_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    hidden = {"_id"}
    cols = [c for c in df.columns if c not in hidden]
    return df[cols]


# ==========================================
# 7. MAIN APPLICATION
# ==========================================
inject_pwa_and_styles()
init_auth_state()

if not st.session_state.auth_user:
    render_login_screen()
    st.stop()

is_admin = st.session_state.auth_role == "ADMIN"
user_name = st.session_state.auth_user

# Top Header with Refresh & Logout
h_col1, h_col2, h_col3 = st.columns([5, 1.2, 1.2])
with h_col1:
    st.markdown(
        f"""
        <div class="brand-header" style="margin-bottom: 8px; padding: 12px 18px;">
            <p class="brand-title" style="font-size: 1.25rem;">TOPTAN FINISTORE — AUDIT & REPORTS</p>
            <p class="brand-sub">User: <b>{user_name}</b> • Role: <b>{st.session_state.auth_label}</b></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with h_col2:
    st.write("")
    if st.button("🔄 Refresh", use_container_width=True):
        load_app_data(force_refresh=True)
        st.rerun()
with h_col3:
    st.write("")
    if st.button("Logout", use_container_width=True):
        st.session_state.auth_user = None
        st.session_state.auth_role = None
        st.session_state.auth_label = None
        st.query_params.clear()
        st.rerun()

df_all, db_error = load_app_data(force_refresh=False)

# Sidebar Navigation
with st.sidebar:
    st.markdown("### MAIN MENU")
    menu_options = [
        "Dashboard",
        "Telecaller Audit",
        "Salesman & Excel Reports",
        "All Customer Data",
        "Branch Reports (Auto-Split)",
    ]
    if is_admin:
        menu_options.insert(1, "Excel Upload & Columns")

    page = st.radio("Navigate", menu_options, label_visibility="collapsed")

    st.divider()
    st.markdown("### 4 BRANCHES")
    selected_branch_filter = st.selectbox(
        "Filter by Branch",
        ["All Branches"] + BRANCHES + ["Unassigned"],
        index=0,
    )

    st.markdown("### REPORT CATEGORY")
    selected_report_filter = st.selectbox(
        "Filter by Report Type",
        ["All Reports"] + REPORT_TYPES,
        index=0,
    )

    st.divider()
    st.caption("📱 **Install as App:** Chrome / Safari മെനുവിൽ നിന്ന് **Add to Home Screen / Install App** ക്ലിക്ക് ചെയ്യുക.")
    if not supabase_configured():
        st.warning("Supabase Key ചേർത്തിട്ടില്ല (Local session active).")

# Apply Global Filters
filtered_df = df_all.copy() if not df_all.empty else pd.DataFrame()
if not filtered_df.empty:
    if selected_branch_filter != "All Branches" and "Branch" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Branch"] == selected_branch_filter]
    if selected_report_filter != "All Reports" and "Report_Type" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Report_Type"] == selected_report_filter]

# ==========================================
# PAGE 1: EXCEL UPLOAD & COLUMN MANAGEMENT (ADMIN ONLY)
# ==========================================
if page == "Excel Upload & Columns" and is_admin:
    st.header("📤 Excel Upload, Auto Branch Split & Column Management")
    st.caption("ഒറ്റ Excel ഷീറ്റിൽ 4 ബ്രാഞ്ചുകളുടെ ഡാറ്റ ഉണ്ടെങ്കിലും സ്പെല്ലിംഗ് മിസ്റ്റേക്കുകൾ സഹിതം തനിയെ വേർതിരിച്ച് (Auto-Split) സേവ് ചെയ്യും.")

    c1, c2 = st.columns(2)
    with c1:
        report_type = st.selectbox("1. Report Type തിരഞ്ഞെടുക്കുക", REPORT_TYPES, index=0)
    with c2:
        branch_mode = st.selectbox(
            "2. Branch Detection Mode",
            ["Auto-Detect (All 4 Branches)"] + BRANCHES,
            index=0,
        )

    uploaded_file = st.file_uploader("3. Excel (.xlsx / .xls) അല്ലെങ്കിൽ CSV ഫയൽ അപ്‌ലോഡ് ചെയ്യുക", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".csv"):
                raw_df = pd.read_csv(uploaded_file)
            else:
                raw_df = pd.read_excel(uploaded_file)

            processed_df = auto_split_dataframe_by_branch(raw_df, default_branch_mode=branch_mode)
            processed_df["Report_Type"] = report_type

            st.subheader("4. Columns ഒഴിവാക്കുക (Optional)")
            removable_cols = [c for c in processed_df.columns if c not in {"Branch", "Report_Type"}]
            cols_to_drop = st.multiselect("Delete ചെയ്യേണ്ട Columns തിരഞ്ഞെടുക്കുക", removable_cols)
            if cols_to_drop:
                processed_df = processed_df.drop(columns=cols_to_drop)

            st.markdown("#### Auto-Detected Branch Summary")
            b_counts = processed_df["Branch"].value_counts().reset_index()
            b_counts.columns = ["Branch", "Records Count"]
            st.dataframe(b_counts, use_container_width=True, hide_index=True)

            st.markdown("#### Data Preview")
            st.dataframe(processed_df.head(50), use_container_width=True)

            st.subheader("5. ഡാറ്റ Save ചെയ്യുക")
            s_col1, s_col2 = st.columns(2)
            records_payload = processed_df.to_dict(orient="records")

            with s_col1:
                if st.button("🔁 Replace All Data (App + Supabase)", type="primary", use_container_width=True):
                    st.session_state.local_records = records_payload
                    ok, msg = save_records_to_supabase(records_payload, mode="replace")
                    load_app_data(force_refresh=True)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

            with s_col2:
                if st.button("➕ Append to Existing Data (App + Supabase)", use_container_width=True):
                    existing = st.session_state.get("local_records", [])
                    combined = records_payload + existing
                    st.session_state.local_records = combined
                    ok, msg = save_records_to_supabase(records_payload, mode="append")
                    load_app_data(force_refresh=True)
                    if ok:
                        st.success(msg)
                    else:
                        st.warning(msg)

        except Exception as exc:
            st.error(f"ഫയൽ വായിക്കുന്നതിൽ പിശക്: {exc}")

    # Manage columns on existing dataset
    if not df_all.empty:
        st.divider()
        st.subheader("നിലവിലുള്ള ഡാറ്റയിലെ Columns Delete ചെയ്യുക")
        existing_cols = [c for c in df_all.columns if c not in {"_id", "Branch", "Report_Type", "Uploaded_At"}]
        del_existing = st.multiselect("നിലവിലുള്ള ടേബിളിൽ നിന്നും നീക്കേണ്ട Columns", existing_cols, key="del_existing_cols")
        if st.button("Delete Selected Columns From Active Data"):
            if del_existing:
                updated_df = df_all.drop(columns=del_existing)
                updated_records = updated_df.to_dict(orient="records")
                st.session_state.local_records = updated_records
                ok, msg = save_records_to_supabase(updated_records, mode="replace")
                load_app_data(force_refresh=True)
                if ok:
                    st.success("Columns നീക്കം ചെയ്ത് Supabase-ൽ അപ്ഡേറ്റ് ചെയ്തു!")
                else:
                    st.warning(f"Local-ൽ അപ്ഡേറ്റ് ആയി. Supabase: {msg}")

# ==========================================
# PAGE 2: DASHBOARD
# ==========================================
elif page == "Dashboard":
    st.header("📊 Operations Dashboard")
    if db_error and is_admin:
        st.caption(f"Note: {db_error}")

    if filtered_df.empty:
        st.info("ഡാറ്റ ലഭ്യമല്ല. Admin ലോഗിൻ ചെയ്ത് Excel Upload വഴി ഡാറ്റ ചേർക്കുക.")
    else:
        total_rows = len(filtered_df)
        branch_count = filtered_df["Branch"].nunique() if "Branch" in filtered_df.columns else 0
        report_count = filtered_df["Report_Type"].nunique() if "Report_Type" in filtered_df.columns else 0

        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Total Records</div><div class="kpi-value">{total_rows:,}</div></div>', unsafe_allow_html=True)
        with k2:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Active Branches</div><div class="kpi-value">{branch_count}</div></div>', unsafe_allow_html=True)
        with k3:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Report Categories</div><div class="kpi-value">{report_count}</div></div>', unsafe_allow_html=True)

        st.subheader("Branch-wise Breakdown")
        if "Branch" in filtered_df.columns:
            b_summary = filtered_df.groupby("Branch").size().reset_index(name="Records")
            st.bar_chart(b_summary.set_index("Branch"))
            st.dataframe(b_summary, use_container_width=True, hide_index=True)

# ==========================================
# PAGE 3: TELECALLER AUDIT
# ==========================================
elif page == "Telecaller Audit":
    st.header("📞 Telecaller Audit")
    if filtered_df.empty:
        st.info("Telecalling ഡാറ്റ ലഭ്യമല്ല.")
    else:
        tc_df = filtered_df.copy()
        if "Report_Type" in tc_df.columns and selected_report_filter == "All Reports":
            tele_only = tc_df[tc_df["Report_Type"] == "Telecalling Audit"]
            if not tele_only.empty:
                tc_df = tele_only

        search_q = st.text_input("Search Telecaller / Customer / Phone / Remarks", "")
        if search_q.strip():
            q = search_q.strip().lower()
            mask = tc_df.apply(lambda row: q in " ".join(str(v).lower() for v in row.values), axis=1)
            tc_df = tc_df[mask]

        st.dataframe(to_clean_display_df(tc_df), use_container_width=True)

# ==========================================
# PAGE 4: SALESMAN & EXCEL REPORTS
# ==========================================
elif page == "Salesman & Excel Reports":
    st.header("📑 Salesman & Excel Reports")
    if filtered_df.empty:
        st.info("Salesman / Excel റിപ്പോർട്ടുകൾ ലഭ്യമല്ല.")
    else:
        rep_df = filtered_df.copy()
        if "Report_Type" in rep_df.columns and selected_report_filter == "All Reports":
            sub_rep = rep_df[rep_df["Report_Type"].isin(["Salesman Report", "Excel Report"])]
            if not sub_rep.empty:
                rep_df = sub_rep

        st.dataframe(to_clean_display_df(rep_df), use_container_width=True)
        csv_bytes = to_clean_display_df(rep_df).to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Download Filtered Report (CSV)", data=csv_bytes, file_name="toptan_reports.csv", mime="text/csv")

# ==========================================
# PAGE 5: ALL CUSTOMER DATA
# ==========================================
elif page == "All Customer Data":
    st.header("🗂️ All Customer Data")
    if filtered_df.empty:
        st.info("കസ്റ്റമർ ഡാറ്റ ലഭ്യമല്ല.")
    else:
        q = st.text_input("Filter records (any keyword)", "")
        view_df = filtered_df
        if q.strip():
            ql = q.strip().lower()
            view_df = view_df[view_df.apply(lambda r: ql in " ".join(str(v).lower() for v in r.values), axis=1)]
        st.dataframe(to_clean_display_df(view_df), use_container_width=True)

# ==========================================
# PAGE 6: BRANCH REPORTS (AUTO-SPLIT)
# ==========================================
elif page == "Branch Reports (Auto-Split)":
    st.header("🏢 4 Branches Auto-Split Reports")
    if df_all.empty or "Branch" not in df_all.columns:
        st.info("ബ്രാഞ്ച് ഡാറ്റ ലഭ്യമല്ല.")
    else:
        tabs = st.tabs(BRANCHES + ["Unassigned"])
        for idx, b_name in enumerate(BRANCHES + ["Unassigned"]):
            with tabs[idx]:
                b_df = df_all[df_all["Branch"] == b_name]
                st.write(f"**{b_name}** — Total Records: **{len(b_df)}**")
                if not b_df.empty:
                    st.dataframe(to_clean_display_df(b_df), use_container_width=True)
                else:
                    st.caption("ഈ ബ്രാഞ്ചിൽ നിലവിൽ റെക്കോർഡുകൾ ഇല്ല.")
