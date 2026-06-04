import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import io
import os

st.set_page_config(
    page_title="Performance Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-card {
        background: white; border-radius: 12px;
        padding: 1.1rem 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        text-align: center; margin-bottom: 0.5rem;
    }
    .metric-label { font-size: 0.72rem; color: #888; margin-bottom: 4px;
                    text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.7rem; font-weight: 700; color: #1a1a2e; }
</style>
""", unsafe_allow_html=True)

ADMIN_PASSWORD = "admin123"   # ← change this

# ── Streamlit secrets-backed config ──────────────────────────────────────────
# Build names are stored in .streamlit/secrets.toml on Streamlit Cloud
# Locally they fall back to a JSON file.

LOCAL_CFG = "dashboard_config.json"
DATA_KEY   = "perf_data"   # key inside st.session_state for merged dataframe


def get_build_names() -> dict:
    """Read build names from secrets if available, else local file."""
    try:
        raw = st.secrets.get("build_names", {})
        return dict(raw) if raw else _local_cfg().get("build_names", {})
    except Exception:
        return _local_cfg().get("build_names", {})


def _local_cfg() -> dict:
    if os.path.exists(LOCAL_CFG):
        with open(LOCAL_CFG) as f:
            return json.load(f)
    return {"build_names": {}}


def save_build_names_local(names: dict):
    cfg = _local_cfg()
    cfg["build_names"] = names
    with open(LOCAL_CFG, "w") as f:
        json.dump(cfg, f)


# ── Module classification rules ──────────────────────────────────────────────
#
# STRATEGY:
#  Each row gets (Module_Name, Sub_Module, subtype, modules_list)
#  modules_list = list of Module_Names this row belongs to (for shared rows)
#  Login/Logout/URL rows are shared across relevant modules.
#
# The dashboard shows:
#  - Module tab → all transactions for that module (incl Login/Logout)
#  - Sub-module tab → specific TC subset + shared rows (Search/Open/Park/Login)
#
# SHARED ROWS that appear in EVERY module:
#   Enter URL - EMR, Login - EMR, Logout - EMR
# ADVICE-ONLY shared:
#   Enter URL - EMR_Couns, Login - EMR_Couns (Surgery + Counselling flows)
#   Enter URL - EMR_Couns-NSA, Login - EMR_Couns-NSA (NSA flow)
#   Enter URL - IHMS, Login IHMS (Surgery + NSA)
#   Search/Open Advice-Counselling Patients (Surgery sub)
#   Search/Open Advice-Counselling Patients_NSA (NSA sub)

# SC19 TC → sub-module mapping (exact TC numbers from spec)
SC19_TC_SUBMODULE = {
    # Shared across all Advice sub-modules
    'TC01': ['Refraction & GP', 'Drug', 'Procedure', 'Treatment', 'Surgery', 'NSA'],
    'TC02': ['Refraction & GP', 'Drug', 'Procedure', 'Treatment', 'Surgery', 'NSA'],
    'TC42': ['Refraction & GP', 'Drug', 'Procedure', 'Treatment', 'Surgery', 'NSA'],  # Park
    # Refraction & GP
    'TC03': ['Refraction & GP'],
    'TC04': ['Refraction & GP'],
    # Drug
    'TC06': ['Drug'],
    'TC07': ['Drug'],
    'TC08': ['Drug'],   # Print Drug
    # Procedure
    'TC09': ['Procedure'],
    'TC10': ['Procedure'],
    # Treatment
    'TC11': ['Treatment'],
    'TC12': ['Treatment'],
    # Surgery
    'TC13': ['Surgery'],
    'TC14': ['Surgery'],
    'TC15': ['Surgery'],
    'TC16': ['Surgery'],
    'TC17': ['Surgery'],
    'TC18': ['Surgery'],  # Print Prognosis
    'TC19': ['Surgery'],  # Print Consent
    'TC20': ['Surgery'],  # Print Counselling Card
    'TC20_1': ['Surgery'],  # Search Counselling
    'TC20_2': ['Surgery'],  # Open Counselling
    'TC21': ['Surgery'],   # IHMS (non-NSA)
    'TC22': ['Surgery'],   # IHMS (non-NSA)
    'TC24': ['Surgery'],   # Search IP
    'TC25': ['Surgery'],   # Open IP
    'TC26': ['Surgery'],
    'TC27': ['Surgery'],
    'TC28': ['Surgery'],
    'TC29': ['Surgery'],
    'TC30': ['Surgery'],
    'TC31': ['Surgery'],
    'TC32': ['Surgery'],  # Print Sx-Notes
    'TC34': ['Surgery'],
    'TC36_discharge': ['Surgery', 'NSA'],  # Discharge IHMS
    # NSA
    'TC21_NSA': ['NSA'],
    'TC22_NSA': ['NSA'],
    'TC24_NSA': ['NSA'],
    'TC25_NSA': ['NSA'],
    'TC35': ['NSA'],
    'TC36_NSA': ['NSA'],   # Create NSA
    'TC37': ['NSA'],
    'TC38': ['NSA'],
    'TC38_1': ['NSA'],   # Search Counselling NSA
    'TC38_2': ['NSA'],   # Open Counselling NSA
    'TC39': ['NSA'],
    'TC40': ['NSA'],
    'TC41': ['NSA'],
    'TC42_discharge': ['NSA'],  # Create Discharge Rounds
}

# SC20 TC → sub-module mapping
SC20_TC_SUBMODULE = {
    # Search/Open/Park shared across all Workup sub-modules
    'TC01_search': ['Paediatric', 'Neuro', 'Physician', 'Orbit', 'Lasik'],
    'TC02_open':   ['Paediatric', 'Neuro', 'Physician', 'Orbit', 'Lasik'],
    'TC30':        ['Paediatric', 'Neuro', 'Physician', 'Orbit', 'Lasik'],
    # Paediatric
    'TC01_paed': ['Paediatric'],
    'TC02_paed': ['Paediatric'],
    # Neuro + Physician (Neuro includes Physician rows per spec)
    'TC03': ['Neuro'],
    'TC04': ['Neuro'],
    'TC05': ['Neuro', 'Physician'],
    'TC06': ['Neuro', 'Physician'],
    'TC06_1': ['Neuro', 'Physician'],
    'TC07': ['Neuro', 'Physician'],
    'TC07_1': ['Neuro', 'Physician'],
    'TC08': ['Neuro', 'Physician'],
    'TC08_1': ['Neuro', 'Physician'],
    # Orbit
    'TC09': ['Orbit'],
    'TC10': ['Orbit'],
    'TC11': ['Orbit'],
    'TC12': ['Orbit'],
    'TC13': ['Orbit'],
    'TC14': ['Orbit'],
    'TC15': ['Orbit'],
    'TC16': ['Orbit'],
    'TC17': ['Orbit'],
    'TC18': ['Orbit'],
    'TC19': ['Orbit'],
    'TC20': ['Orbit'],
    'TC21': ['Orbit'],
    'TC22': ['Orbit'],
    'TC23': ['Orbit'],
    'TC24': ['Orbit'],
    # Lasik
    'TC25': ['Lasik'],
    'TC26': ['Lasik'],
    'TC27': ['Lasik'],
    'TC28': ['Lasik'],
    'TC29': ['Lasik'],
}

# Modules that include Enter URL-EMR / Login-EMR / Logout-EMR
ALL_MODULES = [
    'Complaints', 'Vision', 'Nutri-Assess', 'Vulnerabilities', 'History',
    'Refraction', 'Refraction Others', 'Investigation', 'Anterior Segment',
    'Dilation', 'Fundus Exam', 'Special Investigation', 'General Anaesthesia',
    'Diagnosis', 'Opinion/Referral', 'Special Remarks', 'FollowUp',
    'Advice', 'Speciality Workup',
]

SC_MODULE_MAP = {
    2: 'Complaints', 3: 'Vision', 4: 'Nutri-Assess',
    5: 'Vulnerabilities', 6: 'History', 7: 'Refraction',
    8: 'Refraction Others', 9: 'Investigation',
    10: 'Anterior Segment', 11: 'Dilation', 12: 'Fundus Exam',
    13: 'Special Investigation', 14: 'General Anaesthesia',
    15: 'Diagnosis', 16: 'Opinion/Referral', 17: 'Special Remarks',
    18: 'FollowUp', 19: 'Advice', 20: 'Speciality Workup',
}

ADVICE_SUBMODULES_ALL = [
    'Advice — Refraction & GP', 'Advice — Drug', 'Advice — Procedure',
    'Advice — Treatment', 'Advice — Surgery', 'Advice — NSA',
]
WORKUP_SUBMODULES_ALL = [
    'Workup — Paediatric', 'Workup — Neuro', 'Workup — Physician',
    'Workup — Orbit', 'Workup — Lasik',
]


def get_tc_key(tx: str) -> str:
    """Extract TC key like TC01, TC06-1, etc from transaction string."""
    m = re.search(r'_(TC[\d]+(?:[_-]\d+)?)', tx, re.IGNORECASE)
    return m.group(1).upper() if m else ''


def get_print_label(tx: str) -> str:
    """Extract a meaningful short label for a Print transaction."""
    t = tx.strip()
    # Remove SC prefix like SC19_TC05_
    t2 = re.sub(r'^SC\d+_TC[\d_-]+_', '', t, flags=re.IGNORECASE).strip()
    # Remove trailing _01, _02 etc
    t2 = re.sub(r'_\d{2}$', '', t2).strip()
    # Remove "Fast Report" / "FastReport" suffix
    t2 = re.sub(r'\s*[-–]?\s*Fast.?Report', '', t2, flags=re.IGNORECASE).strip()
    # Remove leading "Print " word to get the subject
    label = re.sub(r'^Print[_\s]*', '', t2, flags=re.IGNORECASE).strip()
    # Clean up trailing dashes/underscores
    label = re.sub(r'[-_]+$', '', label).strip()
    return label if label else 'Print'
''


def classify_transaction(tx: str):
    """
    Returns list of (module_name, sub_module, subtype) tuples.
    A single row can belong to multiple modules/sub-modules.
    """
    t  = tx.strip()
    tu = t.upper()
    results = []

    # ── Login / URL / Logout rows → shared across ALL modules ──────────
    if re.match(r'^(Enter URL|Login|Logout)', t, re.IGNORECASE):
        subtype = t.split()[0]
        # Determine which modules this login row belongs to
        if 'COUNS-NSA' in tu or 'COUNS_NSA' in tu:
            # NSA counselling login → Advice (NSA sub)
            results.append(('Advice', 'Advice — NSA', subtype))
        elif 'COUNS' in tu:
            # Counselling login → Advice (Surgery sub — per spec)
            results.append(('Advice', 'Advice — Surgery', subtype))
        elif 'IHMS' in tu:
            # IHMS login → Advice Surgery + NSA
            results.append(('Advice', 'Advice — Surgery', subtype))
            results.append(('Advice', 'Advice — NSA', subtype))
        else:
            # Generic EMR Login/URL/Logout → ALL modules
            for mod in ALL_MODULES:
                results.append((mod, mod, subtype))
        return results

    # ── Plain Search/Open Advice-Counselling (non-SC rows) ──────────────
    if re.search(r'Advice.Counselling', t, re.IGNORECASE) and not t.startswith('SC'):
        subtype = t.split()[0]
        if 'NSA' in tu:
            results.append(('Advice', 'Advice — NSA', subtype))
        else:
            results.append(('Advice', 'Advice — Surgery', subtype))
        return results

    # ── Skip TOTAL or blank ─────────────────────────────────────────────
    if tu.startswith('TOTAL') or not t:
        return [('_skip', '_skip', '_skip')]

    # ── Non-SC rows not caught above → Other ────────────────────────────
    if not re.match(r'^SC\d+_', t):
        return [('Other', 'Other', t.split()[0])]

    # ── SC-prefixed rows ─────────────────────────────────────────────────
    parts  = t.split('_')
    prefix = parts[0]
    sc_num = int(re.search(r'\d+', prefix).group())
    mod    = SC_MODULE_MAP.get(sc_num, prefix)

    # Subtype = first word of 3rd part (TC part)
    raw3   = parts[2].strip() if len(parts) > 2 else ''
    subtype = raw3.split(' ')[0] if raw3 else 'Other'

    # ── SC13 Special Investigation ──────────────────────────────────────
    if sc_num == 13:
        results.append(('Special Investigation', 'Special Investigation', subtype))
        # Print rows also go to Print module
        if re.search(r'\bPrint\b|FastReport|Fast.Report', t, re.IGNORECASE):
            results.append(('Print', 'Print', get_print_label(t)))
        return results

    # ── SC19 Advice ─────────────────────────────────────────────────────
    if sc_num == 19:
        raw_up = '_'.join(parts).upper()
        # Determine which sub-modules this TC row belongs to
        subs = set()

        # TC01, TC02, TC42 Park → shared (all sub-modules + parent)
        tc_part = get_tc_key(t)
        if re.search(r'_TC01_', t, re.IGNORECASE) and 'SEARCH' in raw_up:
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        elif re.search(r'_TC02_', t, re.IGNORECASE) and 'OPEN' in raw_up:
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        elif re.search(r'_TC42_PARK', raw_up):
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        # NSA-specific rows
        elif '_NSA' in raw_up or 'IHMS_NSA' in raw_up:
            subs = {'NSA'}
        # Surgery rows
        elif any(k in raw_up for k in ['SURGERY','IHMS','ADMISSION','IP_PATIENT',
                                        'SCHEDULING','ANAESTHESIA','CHECKLIST',
                                        'SURGERY_NOTES','OP_POST','DISCHARGE',
                                        'PROGNOSIS','CONSENT','COUNSELLING-DETAIL',
                                        'COUNSELLING_DETAIL','TC32','TC34','TC26',
                                        'TC27','TC28','TC29','TC30','TC31']):
            subs = {'Surgery'}
        elif re.search(r'_TC(13|14|15|16|17|18|19|20|21|22|24|25|26|27|28|29|30|31|32|34|36_DISCHARGE)_', raw_up):
            subs = {'Surgery'}
        # Drug
        elif 'DRUG' in raw_up:
            subs = {'Drug'}
        # Procedure
        elif 'PROCEDURE' in raw_up:
            subs = {'Procedure'}
        # Treatment
        elif 'TREATMENT' in raw_up:
            subs = {'Treatment'}
        # Refraction/GP
        elif 'REFRACTIVE' in raw_up or 'REFRACT' in raw_up or '_GP' in raw_up:
            subs = {'Refraction & GP'}
        # NSA operations
        elif re.search(r'_TC(35|36|37|38|39|40|41|42_CREATE)', raw_up):
            subs = {'NSA'}
        else:
            subs = {'Refraction & GP'}  # fallback

        # Always add to parent Advice module
        results.append(('Advice', 'Advice', subtype))
        for s in subs:
            results.append(('Advice', f'Advice — {s}', subtype))
        # Print rows also go to Print module
        if re.search(r'\bPrint\b|FastReport|Fast.Report', t, re.IGNORECASE):
            results.append(('Print', 'Print', get_print_label(t)))
        return results

    # ── SC20 Speciality Workup ───────────────────────────────────────────
    if sc_num == 20:
        raw_up = '_'.join(parts).upper()
        subs   = set()

        # Search/Open/Park shared across all workup sub-modules
        if re.search(r'SEARCH.*SPECIALITY|SEARCH.*WORKUP', raw_up):
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        elif re.search(r'OPEN.*SPECIALITY|OPEN.*WORKUP', raw_up):
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        elif 'PARK.*SPECIALITY' in raw_up or 'PARK.*WOKUP' in raw_up or 'PARK.*WORKUP' in raw_up:
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        # Paediatric
        elif 'PAEDIATRIC' in raw_up:
            subs = {'Paediatric'}
        # Neuro — includes Physician rows per spec
        elif 'NEURO' in raw_up:
            subs = {'Neuro'}
        # Physician — also in Neuro sub
        elif 'PHYSICIAN' in raw_up:
            subs = {'Neuro', 'Physician'}
        # Orbit — all orbit/lacrimal/oculoplasty rows
        elif any(k in raw_up for k in ['ORBIT','LACRIMAL','OCULOPLASTY','SOCKET','GENERAL_PHYSICAL','GENERAL PHYSICAL']):
            subs = {'Orbit'}
        # Lasik / Cornea
        elif any(k in raw_up for k in ['LASIK','CORNEA','REDIRECT']):
            subs = {'Lasik'}
        else:
            subs = {'Paediatric'}

        results.append(('Speciality Workup', 'Speciality Workup', subtype))
        for s in subs:
            results.append(('Speciality Workup', f'Workup — {s}', subtype))
        return results

    # ── Generic SC module ─────────────────────────────────────────────────
    results.append((mod, mod, subtype))
    return results


# ── Data helpers ─────────────────────────────────────────────────────────────

def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expands rows that belong to multiple modules/sub-modules.
    Each physical CSV row may become multiple logical rows.
    """
    df = df.copy()
    df = df[~df['Transaction'].str.upper().str.startswith('TOTAL')].copy()
    df = df[df['Transaction'].str.strip() != ''].copy()

    expanded = []
    for _, row in df.iterrows():
        classifications = classify_transaction(row['Transaction'])
        for (mod, sub, subtype) in classifications:
            if mod == '_skip':
                continue
            new_row = row.copy()
            new_row['Module_Name']         = mod
            new_row['Sub_Module']          = sub
            new_row['Transaction_Subtype'] = subtype
            expanded.append(new_row)

    result = pd.DataFrame(expanded).reset_index(drop=True)

    # Extract build group from end of transaction string _01, _02 etc.
    result['Transaction_Group'] = result['Transaction'].str.extract(r'_(\d{2})$')
    # For login/URL rows without group suffix, set group as None
    # (they'll show in all builds — we fill NaN with a sentinel)
    result['Prefix'] = result['Transaction'].apply(
        lambda t: re.match(r'^(SC\d+)', t).group(1) if re.match(r'^SC\d+', t) else 'COMMON'
    )
    return result


def build_label_map(all_groups, build_name_map):
    return {g: build_name_map.get(str(g), f'Build {i+1}')
            for i, g in enumerate(sorted(all_groups))}


# ── Chart helpers ─────────────────────────────────────────────────────────────

def plot_bar(df_mod, lmap, groups, module_title):
    # Use group code as x-axis key to avoid duplicate label issue
    df_plot = df_mod.copy()
    df_plot['Build_Code'] = df_plot['Transaction_Group']
    code_order  = list(groups)
    # Two-line tick: "Build 01 / Pg_Bouncer" only shown once via set_xticklabels
    tick_labels = [f"Build {g}\n{lmap.get(g, g)}" for g in groups]

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.barplot(data=df_plot, x='Build_Code', y='Response time(sec)',
                hue='Transaction_Subtype', palette='tab10',
                order=code_order, ax=ax)

    for container, subtype in zip(ax.containers, ax.get_legend_handles_labels()[1]):
        for bar in container:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                        f'{h:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
                ax.text(bar.get_x() + bar.get_width() / 2, h / 2,
                        subtype, ha='center', va='center',
                        fontsize=7, color='white', fontweight='bold', rotation=90)

    ax.set_title(f'{module_title} — Response Time by Build & Subtype',
                 fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(code_order)))
    ax.set_xticklabels(tick_labels, fontsize=10, ha='center')
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


def plot_line(df_mod, lmap, groups, module_title):
    # Use group codes as x-axis positions, custom names only in tick labels
    tick_labels = [f"Build {g}\n{lmap.get(g, g)}" for g in groups]
    subtypes    = sorted(df_mod['Transaction_Subtype'].dropna().unique())
    colors      = sns.color_palette('tab10', len(subtypes))
    markers     = ['o', 's', 'D', '^', 'v', 'P', '*', 'X', 'h', '+']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, sub in enumerate(subtypes):
        agg = (
            df_mod[df_mod['Transaction_Subtype'] == sub]
            .groupby('Transaction_Group')['Response time(sec)'].mean()
            .reindex(list(groups))
        )
        ax.plot(range(len(groups)), agg.values, label=sub,
                color=colors[i], marker=markers[i % len(markers)],
                markersize=9, linewidth=2)
        for xi, val in enumerate(agg.values):
            if pd.notna(val):
                ax.text(xi, val + 0.015, f'{val:.2f}',
                        ha='center', va='bottom', fontsize=8,
                        fontweight='bold', color=colors[i])

    ax.set_title(f'{module_title} — Response Time Trend',
                 fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(tick_labels, fontsize=10, ha='center')
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


# ── Session state init ────────────────────────────────────────────────────────
if 'admin_unlocked' not in st.session_state:
    st.session_state.admin_unlocked = False
if DATA_KEY not in st.session_state:
    st.session_state[DATA_KEY] = None
if 'build_names' not in st.session_state:
    st.session_state.build_names = get_build_names()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/combo-chart.png", width=36)
    st.markdown("### 📊 Performance Dashboard")
    st.divider()

    with st.expander("🔒 Admin", expanded=False):
        pw = st.text_input("Password", type="password", key="pw_input")
        if st.button("Unlock"):
            if pw == ADMIN_PASSWORD:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Wrong password")
        if st.session_state.admin_unlocked:
            st.success("✅ Admin active")
            if st.button("Lock"):
                st.session_state.admin_unlocked = False
                st.rerun()

    st.divider()

    df_side = st.session_state.get(DATA_KEY)
    if df_side is not None and not df_side.empty:
        st.subheader("🔍 Filter")
        all_groups  = sorted(df_side['Transaction_Group'].dropna().unique())
        lmap_side   = build_label_map(all_groups, st.session_state.build_names)

        # Module filter — use Module_Name directly (not prefix)
        all_module_names = sorted(df_side['Module_Name'].dropna().unique())
        selected_module  = st.selectbox("Module", ["All Modules"] + list(all_module_names))

        st.divider()
        st.markdown("**🔀 Compare Builds**")
        st.caption("Tick the builds you want on the chart")

        selected_groups = []
        for g in all_groups:
            label = lmap_side.get(g, f"Build {g}")
            checked = st.checkbox(
                f"Build {g}  —  {label}",
                value=True,
                key=f"chk_{g}"
            )
            if checked:
                selected_groups.append(g)
    else:
        selected_module = "All Modules"
        selected_groups = []
        module_options  = {}


# ══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════
if st.session_state.admin_unlocked:
    st.title("⚙️ Admin Setup")
    st.info("Upload CSV(s) and name your builds. Data stays in your browser session — to make it permanent, follow the instructions below.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Step 1 — Upload CSV(s)")
        st.caption("Select one or multiple CSV files — merged automatically.")
        uploaded_files = st.file_uploader(
            "Upload CSV files", type=["csv"], accept_multiple_files=True
        )
        if uploaded_files:
            frames, names = [], []
            for f in uploaded_files:
                try:
                    frames.append(pd.read_csv(f))
                    names.append(f.name)
                except Exception as e:
                    st.warning(f"Could not read {f.name}: {e}")
            if frames:
                combined = pd.concat(frames, ignore_index=True).drop_duplicates()
                df_proc  = extract_fields(combined)
                st.session_state[DATA_KEY] = df_proc

                all_groups_new = sorted(df_proc['Transaction_Group'].dropna().unique())
                existing = st.session_state.build_names.copy()
                for i, g in enumerate(all_groups_new):
                    if str(g) not in existing:
                        existing[str(g)] = f"Build {i+1}"
                st.session_state.build_names = existing

                st.success(
                    f"✅ {len(uploaded_files)} file(s) merged | "
                    f"{len(df_proc)} rows | "
                    f"{df_proc['Prefix'].nunique()} modules | "
                    f"Builds: {', '.join(all_groups_new)}"
                )
                with st.expander("Files loaded"):
                    for n in names:
                        st.write(f"• {n}")

        # Permanent storage instructions
        with st.expander("📌 Make data permanent (survive redeploy)"):
            st.markdown("""
**Problem:** Streamlit Cloud resets files on every redeploy.

**Solution — commit CSV to GitHub:**
1. In your `perf-dashboard` GitHub repo, click **Add file → Upload files**
2. Upload your CSV as `data.csv`
3. The app will auto-load it on startup permanently

**Solution — store build names permanently:**
1. In Streamlit Cloud → **Manage app → Secrets**
2. Add your build names like this:
```toml
[build_names]
"01" = "Pg_Bouncer"
"02" = "Memory Optimization"
"03" = "Physician"
```
3. Click Save — done, survives all redeploys
""")

    with col2:
        st.subheader("Step 2 — Name Each Build / Sprint")
        df_admin = st.session_state.get(DATA_KEY)
        if df_admin is not None:
            all_groups    = sorted(df_admin['Transaction_Group'].dropna().unique())
            current_names = st.session_state.build_names

            st.caption(f"Builds detected from CSV: **{', '.join(['Build ' + g for g in all_groups])}**")
            st.markdown("Give each build a meaningful name. These show on chart axes and filters.")
            st.divider()

            new_names = {}
            # Render 2 per row for cleaner layout
            pairs = [all_groups[i:i+2] for i in range(0, len(all_groups), 2)]
            for pair in pairs:
                cols = st.columns(2)
                for col, g in zip(cols, pair):
                    with col:
                        st.markdown(f"**Build {g}**")
                        new_names[str(g)] = st.text_input(
                            f"Name for Build {g}",
                            value=current_names.get(str(g), f"Build {g}"),
                            key=f"admin_bn_{g}",
                            label_visibility="collapsed",
                            placeholder=f"e.g. Sprint 46, Pg_Bouncer..."
                        )

            st.divider()
            # Live preview table
            preview_rows = "  |  ".join([f"`Build {g}` → **{v}**" for g, v in new_names.items() if v])
            st.markdown("**Preview:** " + preview_rows)

            if st.button("💾 Apply Build Names", type="primary", use_container_width=True):
                st.session_state.build_names = {str(g): str(v) for g, v in new_names.items()}
                save_build_names_local(st.session_state.build_names)
                st.success("✅ Applied! Charts will now show: " + " → ".join(new_names.values()))
                st.rerun()

            # Secrets instructions compactly
            with st.expander("📌 Make build names permanent (survive redeploy)"):
                secrets_text = "[build_names]\n" + "\n".join([f'"{g}" = "{v}"' for g, v in new_names.items() if v])
                st.code(secrets_text, language="toml")
                st.caption("Copy above → Streamlit Cloud → Manage app → Secrets → paste → Save")
        else:
            st.info("Upload CSV in Step 1 first.")

    st.divider()
    st.stop()


# ══════════════════════════════════════════════════════════════
#  AUTO-LOAD data.csv from repo if no session data
# ══════════════════════════════════════════════════════════════
if st.session_state.get(DATA_KEY) is None:
    if os.path.exists("data.csv"):
        try:
            df_loaded = pd.read_csv("data.csv")
            st.session_state[DATA_KEY] = extract_fields(df_loaded)
            all_g = sorted(st.session_state[DATA_KEY]['Transaction_Group'].dropna().unique())
            existing = st.session_state.build_names.copy()
            for i, g in enumerate(all_g):
                if str(g) not in existing:
                    existing[str(g)] = f"Build {i+1}"
            st.session_state.build_names = existing
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  VIEW DASHBOARD
# ══════════════════════════════════════════════════════════════
st.title("📊 Performance Response Time Dashboard")

df_all = st.session_state.get(DATA_KEY)
if df_all is None or df_all.empty:
    st.warning("No data loaded yet.")
    st.info("""
**To load data permanently**, commit your CSV as `data.csv` to the GitHub repo root.

**Or**, ask the admin to upload via the 🔒 Admin panel in the sidebar.
""")
    st.stop()

all_groups  = sorted(df_all['Transaction_Group'].dropna().unique())
lmap        = build_label_map(all_groups, st.session_state.build_names)

# ── Build sub-module list for tabs ───────────────────────────────────────────
# Tab structure: Module_Name → [Sub_Module, ...]
all_modules     = sorted(df_all['Module_Name'].dropna().unique())
all_submodules  = sorted(df_all['Sub_Module'].dropna().unique())

# Apply build filter
# Login/URL rows have no _01 suffix → Transaction_Group is NaN → include them always
if selected_groups:
    df_view = df_all[
        df_all['Transaction_Group'].isin(selected_groups) |
        df_all['Transaction_Group'].isna()
    ].copy()
else:
    df_view = df_all.copy()

# Apply module filter
if selected_module != "All Modules":
    df_view = df_view[df_view['Module_Name'] == selected_module]

if selected_groups:
    build_labels_used = [lmap[g] for g in selected_groups if g in lmap]
    st.caption(f"Comparing: **{'  vs  '.join(build_labels_used)}**")

# Metric cards
c1, c2, c3, c4, c5 = st.columns(5)
for col, (label, val) in zip([c1, c2, c3, c4, c5], [
    ("Modules",    df_view['Module_Name'].nunique()),
    ("Builds",     df_view['Transaction_Group'].nunique()),
    ("Sub-Modules",df_view['Sub_Module'].nunique()),
    ("Avg RT (s)", f"{df_view['Response time(sec)'].mean():.3f}"),
    ("Max RT (s)", f"{df_view['Response time(sec)'].max():.3f}"),
]):
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{val}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Tab ordering: parent module first, then sub-modules in defined order ──
SUBMOD_ORDER = {
    # Print
    'Print':                      0,
    # Advice
    'Advice':                     0,
    'Advice — Refraction & GP':   1,
    'Advice — Drug':              2,
    'Advice — Procedure':         3,
    'Advice — Treatment':         4,
    'Advice — Surgery':           5,
    'Advice — NSA':               6,
    # Speciality Workup
    'Speciality Workup':          0,
    'Workup — Paediatric':        1,
    'Workup — Neuro':             2,
    'Workup — Physician':         3,
    'Workup — Orbit':             4,
    'Workup — Lasik':             5,
}

available_submods = df_view['Sub_Module'].dropna().unique().tolist()
display_submods   = sorted(available_submods, key=lambda s: (SUBMOD_ORDER.get(s, 99), s))

if not display_submods:
    st.warning("No data for selected filters.")
    st.stop()

tabs = st.tabs(display_submods)
for tab, submod in zip(tabs, display_submods):
    with tab:
        df_mod = df_view[df_view['Sub_Module'] == submod].copy()
        # For charts: only rows that have a build group (exclude Login/URL for grouping)
        df_chart = df_mod[df_mod['Transaction_Group'].notna()]
        groups   = sorted(df_chart['Transaction_Group'].dropna().unique())

        if groups:
            st.pyplot(plot_bar(df_chart, lmap, groups, submod))
            st.markdown("<br>", unsafe_allow_html=True)
            if len(groups) > 1:
                st.pyplot(plot_line(df_chart, lmap, groups, submod))
            else:
                st.info("Select 2+ builds in the sidebar to see the trend line chart.")
        else:
            st.info("No build-specific data for this sub-module.")

        with st.expander("📋 All transactions (including Login/URL/Logout)"):
            st.dataframe(
                df_mod[['Transaction','Module_Name','Sub_Module','Transaction_Subtype',
                         'Transaction_Group','Response time(sec)','Error %']]
                .rename(columns={'Transaction_Group': 'Build Code',
                                 'Transaction_Subtype': 'Subtype',
                                 'Module_Name': 'Module',
                                 'Sub_Module': 'Sub Module'}),
                use_container_width=True
            )
