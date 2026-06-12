import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import os

st.set_page_config(page_title="Performance Dashboard", page_icon="📊", layout="wide")

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

ADMIN_PASSWORD = "admin123"
LOCAL_CFG      = "dashboard_config.json"
DATA_KEY       = "perf_data"
CSV_PATH       = "data.csv"

# ── Config helpers ─────────────────────────────────────────────────────────────
def get_build_names() -> dict:
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

# ── Classification constants ───────────────────────────────────────────────────
SC_MODULE_MAP = {
    2: 'Complaints', 3: 'Vision', 4: 'Nutri-Assess',
    5: 'Vulnerabilities', 6: 'History', 7: 'Refraction',
    8: 'Refraction Others', 9: 'Investigation',
    10: 'Anterior Segment', 11: 'Dilation', 12: 'Fundus Exam',
    13: 'Special Investigation', 14: 'General Anaesthesia',
    15: 'Diagnosis', 16: 'Opinion/Referral', 17: 'Special Remarks',
    18: 'FollowUp', 19: 'Advice', 20: 'Speciality Workup',
}

ALL_MODULES = list(SC_MODULE_MAP.values())

SUBMOD_ORDER = {
    'Print': -1,
    'Advice': 0,
    'Advice — Refraction & GP': 1, 'Advice — Drug': 2,
    'Advice — Procedure': 3, 'Advice — Treatment': 4,
    'Advice — Surgery': 5, 'Advice — NSA': 6,
    'Speciality Workup': 0,
    'Workup — Paediatric': 1, 'Workup — Neuro': 2,
    'Workup — Physician': 3, 'Workup — Orbit': 4, 'Workup — Lasik': 5,
}

# ── Label helpers ──────────────────────────────────────────────────────────────
def get_print_label(tx: str) -> str:
    t2 = re.sub(r'^SC\d+_TC[\d_-]+_', '', tx.strip(), flags=re.IGNORECASE).strip()
    t2 = re.sub(r'_\d{2}$', '', t2).strip()
    t2 = re.sub(r'\s*[-–]?\s*Fast.?Report', '', t2, flags=re.IGNORECASE).strip()
    label = re.sub(r'^Print[_\s]*', '', t2, flags=re.IGNORECASE).strip()
    return re.sub(r'[-_]+$', '', label).strip() or 'Print'

# ── Main classifier ────────────────────────────────────────────────────────────
def classify_transaction(tx: str):
    """Returns list of (Module_Name, Sub_Module, Subtype) tuples."""
    t  = tx.strip()
    tu = t.upper()
    results = []

    # ── TOTAL / blank → skip ───────────────────────────────────────────────
    if tu.startswith('TOTAL') or not t or t.lower() == 'transaction':
        return [('_skip', '_skip', '_skip')]

    # ── Login / URL / Logout rows ──────────────────────────────────────────
    if re.match(r'^(Enter URL|Login|Logout)', t, re.IGNORECASE):
        subtype = t.split()[0]
        if 'COUNS-NSA' in tu or 'COUNS_NSA' in tu:
            # NSA counselling → Advice parent + NSA sub
            results.append(('Advice', 'Advice', subtype))
            results.append(('Advice', 'Advice — NSA', subtype))
        elif 'COUNS' in tu:
            # Counselling EMR → Advice parent + Surgery sub
            results.append(('Advice', 'Advice', subtype))
            results.append(('Advice', 'Advice — Surgery', subtype))
        elif 'IHMS' in tu:
            # IHMS → Advice parent + Surgery + NSA subs
            results.append(('Advice', 'Advice', subtype))
            results.append(('Advice', 'Advice — Surgery', subtype))
            results.append(('Advice', 'Advice — NSA', subtype))
        else:
            # Generic EMR Login/URL/Logout → ALL modules (as shared row)
            for mod in ALL_MODULES:
                results.append((mod, mod, subtype))
        return results

    # ── Plain Search/Open Advice-Counselling (non-SC prefix) ──────────────
    if re.search(r'Advice.Counselling', t, re.IGNORECASE) and not t.startswith('SC'):
        subtype = t.split()[0]
        if 'NSA' in tu:
            results.append(('Advice', 'Advice', subtype))
            results.append(('Advice', 'Advice — NSA', subtype))
        else:
            results.append(('Advice', 'Advice', subtype))
            results.append(('Advice', 'Advice — Surgery', subtype))
        return results

    # ── Non-SC rows not caught above ───────────────────────────────────────
    if not re.match(r'^SC\d+_', t):
        return [('Other', 'Other', t.split()[0])]

    # ── SC-prefixed rows ───────────────────────────────────────────────────
    parts   = t.split('_')
    prefix  = parts[0]
    sc_num  = int(re.search(r'\d+', prefix).group())
    mod     = SC_MODULE_MAP.get(sc_num, prefix)
    raw3    = parts[2].strip() if len(parts) > 2 else ''
    subtype = raw3.split(' ')[0] if raw3 else 'Other'

    # ── SC13 Special Investigation ─────────────────────────────────────────
    if sc_num == 13:
        results.append(('Special Investigation', 'Special Investigation', subtype))
        if re.search(r'\bPrint\b|FastReport|Fast.Report', t, re.IGNORECASE):
            results.append(('Print', 'Print', get_print_label(t)))
        return results

    # ── SC19 Advice ────────────────────────────────────────────────────────
    if sc_num == 19:
        raw_up = '_'.join(parts).upper()
        subs   = set()

        if re.search(r'_TC01_', t, re.IGNORECASE) and 'SEARCH' in raw_up:
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        elif re.search(r'_TC02_', t, re.IGNORECASE) and 'OPEN' in raw_up:
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        elif re.search(r'_TC42_PARK', raw_up):
            subs = {'Refraction & GP','Drug','Procedure','Treatment','Surgery','NSA'}
        elif '_NSA' in raw_up or 'IHMS_NSA' in raw_up:
            subs = {'NSA'}
        elif any(k in raw_up for k in ['SURGERY','IHMS','ADMISSION','SCHEDULING',
                                        'ANAESTHESIA','CHECKLIST','SURGERY_NOTES',
                                        'OP_POST','DISCHARGE','PROGNOSIS','CONSENT',
                                        'COUNSELLING-DETAIL','COUNSELLING_DETAIL',
                                        'TC32','TC34','TC26','TC27','TC28','TC29',
                                        'TC30','TC31']):
            subs = {'Surgery'}
        elif re.search(r'_TC(13|14|15|16|17|18|19|20|21|22|24|25)_', raw_up):
            subs = {'Surgery'}
        elif 'DRUG' in raw_up:
            subs = {'Drug'}
        elif 'PROCEDURE' in raw_up:
            subs = {'Procedure'}
        elif 'TREATMENT' in raw_up:
            subs = {'Treatment'}
        elif 'REFRACTIVE' in raw_up or '_GP' in raw_up:
            subs = {'Refraction & GP'}
        elif re.search(r'_TC(35|36|37|38|39|40|41)', raw_up):
            subs = {'NSA'}
        else:
            subs = {'Refraction & GP'}

        results.append(('Advice', 'Advice', subtype))
        for s in subs:
            results.append(('Advice', f'Advice — {s}', subtype))
        if re.search(r'\bPrint\b|FastReport|Fast.Report', t, re.IGNORECASE):
            results.append(('Print', 'Print', get_print_label(t)))
        return results

    # ── SC20 Speciality Workup ─────────────────────────────────────────────
    if sc_num == 20:
        raw_up = '_'.join(parts).upper()
        subs   = set()

        if re.search(r'SEARCH.*SPECIALITY|SEARCH.*WORKUP', raw_up):
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        elif re.search(r'OPEN.*SPECIALITY|OPEN.*WORKUP', raw_up):
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        elif re.search(r'PARK.*SPECIALITY|PARK.*WOKUP|PARK.*WORKUP', raw_up):
            subs = {'Paediatric','Neuro','Physician','Orbit','Lasik'}
        elif 'PAEDIATRIC' in raw_up:
            subs = {'Paediatric'}
        elif 'NEURO' in raw_up:
            subs = {'Neuro'}
        elif 'PHYSICIAN' in raw_up:
            subs = {'Neuro','Physician'}
        elif any(k in raw_up for k in ['ORBIT','LACRIMAL','OCULOPLASTY','SOCKET',
                                        'GENERAL_PHYSICAL','GENERAL PHYSICAL']):
            subs = {'Orbit'}
        elif any(k in raw_up for k in ['LASIK','CORNEA','REDIRECT']):
            subs = {'Lasik'}
        else:
            subs = {'Paediatric'}

        results.append(('Speciality Workup', 'Speciality Workup', subtype))
        for s in subs:
            results.append(('Speciality Workup', f'Workup — {s}', subtype))
        return results

    # ── Generic SC module ──────────────────────────────────────────────────
    results.append((mod, mod, subtype))
    return results

# ── Data processing ────────────────────────────────────────────────────────────
def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df[~df['Transaction'].str.upper().str.startswith('TOTAL')].copy()
    df = df[df['Transaction'].str.strip() != ''].copy()
    df = df[df['Transaction'].str.lower() != 'transaction'].copy()

    expanded = []
    for _, row in df.iterrows():
        for (mod, sub, subtype) in classify_transaction(row['Transaction']):
            if mod == '_skip':
                continue
            nr = row.copy()
            nr['Module_Name']         = mod
            nr['Sub_Module']          = sub
            nr['Transaction_Subtype'] = subtype
            expanded.append(nr)

    result = pd.DataFrame(expanded).reset_index(drop=True)
    result['Transaction_Group'] = result['Transaction'].str.extract(r'_(\d{2})$').astype(str).replace('nan', pd.NA)
    result['Prefix'] = result['Transaction'].apply(
        lambda t: re.match(r'^(SC\d+)', t).group(1) if re.match(r'^SC\d+', t) else 'COMMON'
    )
    return result

def build_label_map(all_groups, build_name_map):
    fresh  = _local_cfg().get("build_names", {})
    merged = {**build_name_map, **fresh}
    return {g: merged.get(str(g), f'Build {i+1}') for i, g in enumerate(sorted(all_groups))}

# ── Charts ─────────────────────────────────────────────────────────────────────
def plot_bar(df_mod, lmap, groups, title):
    build_order  = [lmap.get(g, g) for g in groups]
    tick_labels  = [f"Build {g}\n{lmap.get(g, g)}" for g in groups]
    df_plot      = df_mod.copy()
    df_plot['Build_Label'] = df_plot['Transaction_Group'].map(lmap)

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.barplot(data=df_plot, x='Build_Code' if 'Build_Code' in df_plot else 'Transaction_Group',
                y='Response time(sec)', hue='Transaction_Subtype',
                palette='tab10', order=groups, ax=ax)

    # Use group codes on x so seaborn doesn't duplicate
    df_plot['_grp'] = df_plot['Transaction_Group']
    ax.cla()
    sns.barplot(data=df_plot, x='_grp', y='Response time(sec)',
                hue='Transaction_Subtype', palette='tab10', order=groups, ax=ax)

    for container, sub in zip(ax.containers, ax.get_legend_handles_labels()[1]):
        for bar in container:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width()/2, h + 0.01,
                        f'{h:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
                ax.text(bar.get_x() + bar.get_width()/2, h/2,
                        sub, ha='center', va='center',
                        fontsize=7, color='white', fontweight='bold', rotation=90)

    ax.set_title(f'{title} — Response Time by Build & Subtype', fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(tick_labels, fontsize=10, ha='center')
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig

def plot_line(df_mod, lmap, groups, title):
    tick_labels = [f"Build {g}\n{lmap.get(g, g)}" for g in groups]
    subtypes    = sorted(df_mod['Transaction_Subtype'].dropna().unique())
    colors      = sns.color_palette('tab10', len(subtypes))
    markers     = ['o','s','D','^','v','P','*','X','h','+']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, sub in enumerate(subtypes):
        agg = (df_mod[df_mod['Transaction_Subtype'] == sub]
               .groupby('Transaction_Group')['Response time(sec)'].mean()
               .reindex(list(groups)))
        ax.plot(range(len(groups)), agg.values, label=sub,
                color=colors[i], marker=markers[i % len(markers)],
                markersize=9, linewidth=2)
        for xi, val in enumerate(agg.values):
            if pd.notna(val):
                ax.text(xi, val + 0.015, f'{val:.2f}',
                        ha='center', va='bottom', fontsize=8,
                        fontweight='bold', color=colors[i])

    ax.set_title(f'{title} — Response Time Trend', fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(tick_labels, fontsize=10, ha='center')
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig

# ── Session state ──────────────────────────────────────────────────────────────
if 'admin_unlocked' not in st.session_state:
    st.session_state.admin_unlocked = False
if DATA_KEY not in st.session_state:
    st.session_state[DATA_KEY] = None
if 'build_names' not in st.session_state:
    st.session_state.build_names = get_build_names()

# ── Sidebar ────────────────────────────────────────────────────────────────────
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

        all_groups    = sorted([str(g) for g in df_side['Transaction_Group'].dropna().unique()])
        lmap_side     = build_label_map(all_groups, st.session_state.build_names)
        all_mod_names = sorted(df_side['Module_Name'].dropna().unique())

        selected_module = st.selectbox("Module", ["All Modules"] + list(all_mod_names))

        st.markdown("**Compare Builds**")
        st.caption("Tick the builds to include")
        selected_groups = []
        for g in all_groups:
            label = lmap_side.get(str(g), f"Build {g}")
            if st.checkbox(f"Build {g}  —  {label}", value=True, key=f"chk_{g}"):
                selected_groups.append(str(g))
    else:
        selected_module = "All Modules"
        selected_groups = []

# ══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════
if st.session_state.admin_unlocked:
    st.title("⚙️ Admin Setup")
    st.info("Upload CSV(s) once — all viewers see the same data.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Step 1 — Upload CSV(s)")
        st.caption("Select one or multiple CSV files — merged automatically.")
        uploaded_files = st.file_uploader("Upload CSV files", type=["csv"],
                                           accept_multiple_files=True)
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
                df_proc.to_csv(CSV_PATH, index=False)

                all_groups_new = sorted(df_proc['Transaction_Group'].dropna().unique())
                existing = st.session_state.build_names.copy()
                for i, g in enumerate(all_groups_new):
                    if str(g) not in existing:
                        existing[str(g)] = f"Build {i+1}"
                st.session_state.build_names = existing

                st.success(
                    f"✅ {len(uploaded_files)} file(s) merged | "
                    f"{len(combined)} rows | "
                    f"{df_proc['Module_Name'].nunique()} modules | "
                    f"Builds: {', '.join(all_groups_new)}"
                )
                with st.expander("Files loaded"):
                    for n in names:
                        st.write(f"• {n}")
                st.rerun()

    with col2:
        st.subheader("Step 2 — Name Each Build / Sprint")
        df_admin = st.session_state.get(DATA_KEY)
        if df_admin is not None:
            all_groups    = sorted([str(g) for g in df_admin['Transaction_Group'].dropna().unique()])
            current_names = st.session_state.build_names
            new_names     = {}
            st.caption(f"Detected builds: **{', '.join(['Build ' + str(g) for g in all_groups])}**")
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
                            placeholder=f"e.g. Sprint 46..."
                        )

            st.divider()
            st.markdown("**Preview:** " + "  |  ".join(
                [f"`Build {g}` → **{v}**" for g, v in new_names.items() if v]
            ))

            if st.button("💾 Apply Build Names", type="primary", use_container_width=True):
                st.session_state.build_names = {str(g): str(v) for g, v in new_names.items()}
                save_build_names_local(st.session_state.build_names)
                st.success("✅ Applied! " + " | ".join(new_names.values()))
                st.rerun()

            with st.expander("📌 Make permanent (Streamlit Secrets)"):
                secrets_text = "[build_names]\n" + "\n".join(
                    [f'"{g}" = "{v}"' for g, v in new_names.items() if v])
                st.code(secrets_text, language="toml")
                st.caption("Copy → Streamlit Cloud → Manage app → Secrets → paste → Save")
        else:
            st.info("Upload CSV in Step 1 first.")

    st.divider()
    st.stop()

# ══════════════════════════════════════════════════════════════
#  AUTO-LOAD data.csv from repo
# ══════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Loading data...")
def load_processed_csv(path):
    df = pd.read_csv(path)
    if 'Module_Name' not in df.columns:
        df = extract_fields(df)
    return df

if st.session_state.get(DATA_KEY) is None and os.path.exists(CSV_PATH):
    try:
        df_loaded = load_processed_csv(CSV_PATH)
        st.session_state[DATA_KEY] = df_loaded
        all_g = sorted([str(g) for g in df_loaded['Transaction_Group'].dropna().unique()])
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
st.title("📊 Eyenotes Performance Dashboard")

df_all = st.session_state.get(DATA_KEY)
if df_all is None or df_all.empty:
    st.warning("No data loaded yet.")
    st.info("""
**Option 1** — Commit your CSV as `data.csv` to the GitHub repo root (permanent).
**Option 2** — Ask admin to upload via the 🔒 Admin panel in the sidebar.
""")
    st.stop()

all_groups = sorted([str(g) for g in df_all['Transaction_Group'].dropna().unique()])
lmap       = build_label_map(all_groups, st.session_state.build_names)

# Apply filters
if selected_groups:
    df_view = df_all[
        df_all['Transaction_Group'].isin(selected_groups) |
        df_all['Transaction_Group'].isna()
    ].copy()
else:
    df_view = df_all.copy()

if selected_module != "All Modules":
    df_view = df_view[df_view['Module_Name'] == selected_module]

# Comparing caption
if selected_groups:
    labels_used = [lmap[g] for g in selected_groups if g in lmap]
    st.caption(f"Comparing: **{'  vs  '.join(labels_used)}**")

# ── Dashboard pages ─────────────────────────────────────────────
page = st.radio(
    "View",
    ["📊 Overview", "🔍 Module Detail", "⚖️ Build Comparison", "🚨 Error & Risk", "📋 Transaction Detail"],
    horizontal=True, label_visibility="collapsed"
)
st.divider()

# Helper: RT color
def rt_color(val):
    if val >= 5:   return "🔴"
    if val >= 2:   return "🟡"
    return "🟢"

def color_rt(val):
    if val >= 5:   return "background-color: #ffcccc"
    if val >= 2:   return "background-color: #fff3cc"
    return "background-color: #ccffcc"

def color_err(val):
    try:
        v = float(str(val).replace('%',''))
        if v > 0: return "background-color: #ffcccc"
    except: pass
    return "background-color: #ccffcc"

# ══ PAGE 1: OVERVIEW ══════════════════════════════════════════
if page == "📊 Overview":
    # Metric cards
    sc_df = df_view[df_view['Transaction_Group'].notna()]
    c1,c2,c3,c4,c5 = st.columns(5)
    for col,(label,val) in zip([c1,c2,c3,c4,c5],[
        ("Modules",    df_view['Module_Name'].nunique()),
        ("Builds",     df_view['Transaction_Group'].nunique()),
        ("Avg RT (s)", f"{sc_df['Response time(sec)'].mean():.3f}"),
        ("Max RT (s)", f"{sc_df['Response time(sec)'].max():.3f}"),
        ("Error Txns", int((sc_df['Error %'].astype(str).str.replace('%','').astype(float) > 0).sum())),
    ]):
        col.markdown(f"""<div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Bar chart — avg RT per module per build
    sc_df2 = sc_df[~sc_df['Module_Name'].isin(['Other','All Modules','Print'])]
    agg = (sc_df2.groupby(['Module_Name','Transaction_Group'])['Response time(sec)']
           .mean().reset_index())
    agg['Build_Label'] = agg['Transaction_Group'].map(lmap)

    groups = sorted(agg['Transaction_Group'].dropna().unique())
    modules = sorted(agg['Module_Name'].unique())
    colors  = sns.color_palette('tab10', len(groups))

    fig, ax = plt.subplots(figsize=(14, 7))
    x     = range(len(modules))
    width = 0.8 / max(len(groups), 1)
    for i, g in enumerate(groups):
        vals = [agg[(agg['Module_Name']==m)&(agg['Transaction_Group']==g)]['Response time(sec)'].values
                for m in modules]
        vals = [v[0] if len(v) else 0 for v in vals]
        offset = (i - len(groups)/2 + 0.5) * width
        bars = ax.bar([xi + offset for xi in x], vals, width*0.9,
                      label=lmap.get(g,g), color=colors[i])
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.05,
                        f'{v:.2f}', ha='center', va='bottom', fontsize=7, fontweight='bold')

    ax.set_xticks(list(x))
    ax.set_xticklabels(modules, rotation=45, ha='right', fontsize=9)
    ax.set_title('Average Response Time by Module & Build', fontsize=13, fontweight='600', pad=12)
    ax.set_ylabel('Avg Response Time (s)', fontsize=11)
    ax.legend(title='Build', bbox_to_anchor=(1.02,1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.axhline(y=2, color='orange', linestyle='--', alpha=0.7, label='2s threshold')
    ax.axhline(y=5, color='red',    linestyle='--', alpha=0.7, label='5s threshold')
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    st.pyplot(fig)
    plt.close()

# ══ PAGE 2: MODULE DETAIL ═════════════════════════════════════
elif page == "🔍 Module Detail":
    c1,c2,c3,c4,c5 = st.columns(5)
    sc_df = df_view[df_view['Transaction_Group'].notna()]
    for col,(label,val) in zip([c1,c2,c3,c4,c5],[
        ("Modules",     df_view['Module_Name'].nunique()),
        ("Builds",      df_view['Transaction_Group'].nunique()),
        ("Sub-Modules", df_view['Sub_Module'].nunique()),
        ("Avg RT (s)",  f"{sc_df['Response time(sec)'].mean():.3f}"),
        ("Max RT (s)",  f"{sc_df['Response time(sec)'].max():.3f}"),
    ]):
        col.markdown(f"""<div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    available    = df_view['Sub_Module'].dropna().unique().tolist()
    display_subs = sorted(available, key=lambda s: (SUBMOD_ORDER.get(s, 99), s))

    if not display_subs:
        st.warning("No data for selected filters.")
        st.stop()

    tabs = st.tabs(display_subs)
    for tab, submod in zip(tabs, display_subs):
        with tab:
            df_mod   = df_view[df_view['Sub_Module'] == submod].copy()
            df_chart = df_mod[df_mod['Transaction_Group'].notna()]
            groups   = sorted(df_chart['Transaction_Group'].dropna().unique())

            if groups:
                st.pyplot(plot_bar(df_chart, lmap, groups, submod))
                st.markdown("<br>", unsafe_allow_html=True)
                if len(groups) > 1:
                    st.pyplot(plot_line(df_chart, lmap, groups, submod))
                else:
                    st.info("Select 2+ builds to see trend chart.")
            else:
                st.info("No build-specific data for this sub-module.")

            with st.expander("📋 All transactions"):
                display_df = df_mod[['Transaction','Module_Name','Sub_Module',
                             'Transaction_Subtype','Transaction_Group',
                             'Response time(sec)','Error %']].rename(
                    columns={'Transaction_Group':'Build','Transaction_Subtype':'Subtype',
                             'Module_Name':'Module','Sub_Module':'Sub Module'})
                st.dataframe(display_df.style.map(
                    color_rt, subset=['Response time(sec)']),
                    use_container_width=True)

# ══ PAGE 3: BUILD COMPARISON ══════════════════════════════════
elif page == "⚖️ Build Comparison":
    sc_df = df_view[df_view['Transaction_Group'].notna()]
    sc_df = sc_df[~sc_df['Module_Name'].isin(['Other','All Modules'])]

    st.subheader("Module × Build — Avg Response Time (seconds)")

    pivot = (sc_df.groupby(['Module_Name','Transaction_Group'])['Response time(sec)']
             .mean().unstack(fill_value=0))
    pivot.columns = [lmap.get(str(c), str(c)) for c in pivot.columns]
    pivot = pivot.round(3)

    # Color the pivot table
    def highlight_pivot(val):
        try:
            v = float(val)
            if v >= 5:  return 'background-color:#ffcccc; font-weight:bold'
            if v >= 2:  return 'background-color:#fff3cc'
            if v > 0:   return 'background-color:#ccffcc'
        except: pass
        return ''

    st.dataframe(pivot.style.map(highlight_pivot), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("Side-by-side Bar Chart — All Modules")

    groups  = sorted(sc_df['Transaction_Group'].dropna().unique())
    modules = sorted(sc_df['Module_Name'].unique())
    colors  = sns.color_palette('Set2', len(groups))

    fig, ax = plt.subplots(figsize=(16, 7))
    x     = range(len(modules))
    width = 0.8 / max(len(groups), 1)
    for i, g in enumerate(groups):
        vals = []
        for m in modules:
            v = sc_df[(sc_df['Module_Name']==m)&(sc_df['Transaction_Group']==g)]['Response time(sec)'].mean()
            vals.append(v if pd.notna(v) else 0)
        offset = (i - len(groups)/2 + 0.5) * width
        bars = ax.bar([xi+offset for xi in x], vals, width*0.9,
                      label=lmap.get(g,g), color=colors[i])
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.02,
                        f'{v:.2f}', ha='center', va='bottom', fontsize=6, fontweight='bold')

    ax.set_xticks(list(x))
    ax.set_xticklabels(modules, rotation=45, ha='right', fontsize=9)
    ax.set_title('Build Comparison — Avg RT per Module', fontsize=13, fontweight='600', pad=12)
    ax.set_ylabel('Avg Response Time (s)', fontsize=11)
    ax.legend(title='Build', bbox_to_anchor=(1.02,1), loc='upper left')
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.axhline(y=2, color='orange', linestyle='--', alpha=0.6)
    ax.axhline(y=5, color='red',    linestyle='--', alpha=0.6)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    st.pyplot(fig)
    plt.close()

# ══ PAGE 4: ERROR & RISK ══════════════════════════════════════
elif page == "🚨 Error & Risk":
    sc_df = df_view[df_view['Transaction_Group'].notna()].copy()
    try:
        sc_df['Error_Num'] = sc_df['Error %'].astype(str).str.replace('%','').astype(float)
    except:
        sc_df['Error_Num'] = 0

    col1, col2, col3, col4 = st.columns(4)
    slow5  = (sc_df['Response time(sec)'] >= 5).sum()
    slow2  = ((sc_df['Response time(sec)'] >= 2) & (sc_df['Response time(sec)'] < 5)).sum()
    errors = (sc_df['Error_Num'] > 0).sum()
    ok     = (sc_df['Response time(sec)'] < 2).sum()

    for col,(label,val,color) in zip([col1,col2,col3,col4],[
        ("🔴 Critical (≥5s)", slow5,  "#ffcccc"),
        ("🟡 Warning (2-5s)", slow2,  "#fff3cc"),
        ("🔴 Has Errors",     errors, "#ffcccc"),
        ("🟢 OK (<2s)",       ok,     "#ccffcc"),
    ]):
        col.markdown(f"""<div class="metric-card" style="background:{color}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔴 Top 15 Slowest Transactions")
        slow_df = (sc_df.nlargest(15, 'Response time(sec)')
                   [['Transaction','Module_Name','Transaction_Group','Response time(sec)','Error %']]
                   .rename(columns={'Module_Name':'Module','Transaction_Group':'Build',
                                    'Response time(sec)':'RT (s)'}))
        st.dataframe(slow_df.style.map(color_rt, subset=['RT (s)'])
                                   .map(color_err, subset=['Error %']),
                     use_container_width=True)

    with c2:
        st.subheader("⚠️ Transactions with Errors")
        err_df = sc_df[sc_df['Error_Num'] > 0][
            ['Transaction','Module_Name','Transaction_Group','Response time(sec)','Error %']
        ].sort_values('Error_Num', ascending=False).rename(
            columns={'Module_Name':'Module','Transaction_Group':'Build','Response time(sec)':'RT (s)'})
        if err_df.empty:
            st.success("✅ No error transactions found!")
        else:
            st.dataframe(err_df.style.map(color_rt,  subset=['RT (s)'])
                                      .map(color_err, subset=['Error %']),
                         use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("Error % by Module")
    err_mod = (sc_df[sc_df['Error_Num']>0]
               .groupby('Module_Name')['Error_Num'].mean()
               .sort_values(ascending=False).reset_index())
    if not err_mod.empty:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.barh(err_mod['Module_Name'], err_mod['Error_Num'], color='#ff6b6b')
        for i, v in enumerate(err_mod['Error_Num']):
            ax.text(v+0.01, i, f'{v:.2f}%', va='center', fontsize=9)
        ax.set_xlabel('Avg Error %')
        ax.set_title('Error % by Module', fontsize=13, fontweight='600')
        ax.grid(axis='x', linestyle='--', alpha=0.4)
        fig.patch.set_facecolor('white')
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

# ══ PAGE 5: TRANSACTION DETAIL ════════════════════════════════
elif page == "📋 Transaction Detail":
    sc_df = df_view[df_view['Transaction_Group'].notna()].copy()
    try:
        sc_df['Error_Num'] = sc_df['Error %'].astype(str).str.replace('%','').astype(float)
    except:
        sc_df['Error_Num'] = 0

    # Quick filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        show_slow  = st.checkbox("🔴 Show only slow (≥2s)", value=False)
    with fc2:
        show_error = st.checkbox("⚠️ Show only errors", value=False)
    with fc3:
        sort_by    = st.selectbox("Sort by", ["Response time(sec) ↓", "Error % ↓", "Module", "Build"])

    filtered = sc_df.copy()
    if show_slow:
        filtered = filtered[filtered['Response time(sec)'] >= 2]
    if show_error:
        filtered = filtered[filtered['Error_Num'] > 0]

    sort_map = {
        "Response time(sec) ↓": ("Response time(sec)", False),
        "Error % ↓":            ("Error_Num", False),
        "Module":               ("Module_Name", True),
        "Build":                ("Transaction_Group", True),
    }
    scol, sasc = sort_map[sort_by]
    filtered = filtered.sort_values(scol, ascending=sasc)

    # RT status column
    filtered['Status'] = filtered['Response time(sec)'].apply(rt_color)

    display = filtered[['Status','Transaction','Module_Name','Sub_Module',
                         'Transaction_Subtype','Transaction_Group',
                         'Response time(sec)','Error %','# No of Reqs']].rename(
        columns={'Module_Name':'Module','Sub_Module':'Sub Module',
                 'Transaction_Subtype':'Subtype','Transaction_Group':'Build',
                 'Response time(sec)':'RT (s)','# No of Reqs':'Requests'})

    st.caption(f"Showing **{len(display)}** transactions")
    st.dataframe(
        display.style
            .map(color_rt,  subset=['RT (s)'])
            .map(color_err, subset=['Error %']),
        use_container_width=True,
        height=500
    )

    # Summary stats
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("RT Distribution")
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(filtered['Response time(sec)'], bins=30, color='#378ADD', edgecolor='white')
        ax.axvline(x=2, color='orange', linestyle='--', label='2s')
        ax.axvline(x=5, color='red',    linestyle='--', label='5s')
        ax.set_xlabel('Response Time (s)')
        ax.set_ylabel('Count')
        ax.set_title('Response Time Distribution')
        ax.legend()
        ax.grid(alpha=0.3)
        fig.patch.set_facecolor('white')
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
    with c2:
        st.subheader("Avg RT by Subtype")
        sub_agg = (filtered.groupby('Transaction_Subtype')['Response time(sec)']
                   .mean().sort_values(ascending=False))
        fig, ax = plt.subplots(figsize=(7, 4))
        colors_sub = ['#ff6b6b' if v>=5 else '#ffd93d' if v>=2 else '#6bcb77'
                      for v in sub_agg.values]
        ax.barh(sub_agg.index, sub_agg.values, color=colors_sub)
        for i, v in enumerate(sub_agg.values):
            ax.text(v+0.01, i, f'{v:.2f}s', va='center', fontsize=9)
        ax.set_xlabel('Avg Response Time (s)')
        ax.set_title('Avg RT by Subtype')
        ax.grid(axis='x', alpha=0.3)
        fig.patch.set_facecolor('white')
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
