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
# Maps Transaction string → (Module_Name, Sub_Module)

def classify_transaction(tx: str):
    """
    Returns (module_name, sub_module, subtype) for any transaction row.
    Priority: custom rules first, then generic SC-prefix extraction.
    """
    t = tx.strip()
    tu = t.upper()

    # ── 1. Login / URL module ──────────────────────────────────────────
    if re.match(r'^(Enter URL|Login|Logout)', t, re.IGNORECASE):
        subtype = re.split(r'\s*[-–]\s*|\s+', t)[0]   # Enter / Login / Logout
        return ('Login & URL', 'Login & URL', subtype)

    # ── 2. Print module — catch all Print rows anywhere ────────────────
    if re.search(r'\bPrint\b', t, re.IGNORECASE) and 'SC' not in t[:3]:
        return ('Print', 'Print', 'Print')

    # Only SC-prefixed rows below this point
    if not re.match(r'^SC\d+_', t):
        # Non-SC, non-login rows (e.g. plain Search/Open Advice-Counselling)
        if re.search(r'Advice.Counselling', t, re.IGNORECASE):
            sub = 'NSA' if 'NSA' in tu else 'Counselling'
            subtype = t.split()[0]
            return ('Advice', f'Advice — {sub}', subtype)
        return ('Other', 'Other', t.split()[0])

    parts = t.split('_')
    prefix = parts[0]   # e.g. SC19
    sc_num = int(re.search(r'\d+', prefix).group())

    # ── 3. Print inside SC rows ────────────────────────────────────────
    if re.search(r'\bPrint\b|\bFast.?Report\b', t, re.IGNORECASE):
        return ('Print', f'Print ({prefix})', 'Print')

    # ── 4. Special Investigation (SC13) ───────────────────────────────
    if sc_num == 13:
        raw3 = parts[2] if len(parts) > 2 else ''
        subtype = raw3.strip().split(' ')[0]
        return ('Special Investigation', 'Special Investigation', subtype)

    # ── 5. Speciality Workup (SC20) ───────────────────────────────────
    if sc_num == 20:
        raw3 = '_'.join(parts[2:]) if len(parts) > 2 else ''
        # Identify sub-workup type
        for kw, label in [
            ('Paediatric','Paediatric Workup'),('Neuro','Neuro Workup'),
            ('Physician','Physician Workup'),('Orbit','Orbit Workup'),
            ('Lacrimal','Orbit Workup'),('Oculoplasty','Orbit Workup'),
            ('Lasik','Lasik Workup'),('Cornea','Lasik Workup'),
            ('Speciality','Speciality Workup'),('Redirect','Lasik Workup'),
        ]:
            if kw.lower() in raw3.lower():
                subtype = raw3.strip().split(' ')[0]
                return ('Speciality Workup', f'Workup — {label}', subtype)
        subtype = raw3.strip().split(' ')[0] if raw3 else 'Other'
        return ('Speciality Workup', 'Speciality Workup', subtype)

    # ── 6. Advice module (SC19) — 6 sub-modules ───────────────────────
    if sc_num == 19:
        raw3 = '_'.join(parts[2:]) if len(parts) > 2 else ''
        subtype = parts[2].strip().split(' ')[0] if len(parts) > 2 else 'Other'

        # NSA sub-module
        if any(k in tu for k in ['_NSA','NSA -','NSA–','IHMS_NSA']):
            return ('Advice', 'Advice — NSA', subtype)
        # Surgery advice (includes IP, IHMS, Scheduling, Anaesthesia etc.)
        if any(k in raw3.upper() for k in ['SURGERY','IHMS','ADMISSION','IP PATIENT',
                                             'SCHEDULING','ANAESTHESIA','CHECKLIST',
                                             'SURGERY NOTES','OP POST','DISCHARGE',
                                             'PROGNOSIS','CONSENT','COUNSELLING-DETAIL']):
            return ('Advice', 'Advice — Surgery', subtype)
        # Drug
        if 'DRUG' in raw3.upper():
            return ('Advice', 'Advice — Drug', subtype)
        # Procedure
        if 'PROCEDURE' in raw3.upper():
            return ('Advice', 'Advice — Procedure', subtype)
        # Treatment
        if 'TREATMENT' in raw3.upper():
            return ('Advice', 'Advice — Treatment', subtype)
        # Refractive Correction + GP (first sub-module)
        if any(k in raw3.upper() for k in ['REFRACTIVE','REFRACT','_GP']):
            return ('Advice', 'Advice — Refraction & GP', subtype)
        # Search/Open/Park — shared, assign to main Advice
        if any(k in raw3.upper() for k in ['SEARCH','OPEN','PARK']):
            return ('Advice', 'Advice — Search/Open/Park', subtype)
        return ('Advice', 'Advice — Other', subtype)

    # ── 7. Generic SC module ───────────────────────────────────────────
    SC_MODULE_MAP = {
        2: 'Complaints', 3: 'Vision', 4: 'Nutri-Assess',
        5: 'Vulnerabilities', 6: 'History', 7: 'Refraction',
        8: 'Refraction Others', 9: 'Investigation',
        10: 'Anterior Segment', 11: 'Dilation', 12: 'Fundus Exam',
        14: 'General Anaesthesia', 15: 'Diagnosis',
        16: 'Opinion/Referral', 17: 'Special Remarks', 18: 'FollowUp',
    }
    mod = SC_MODULE_MAP.get(sc_num, f'{prefix}')
    raw3 = parts[2] if len(parts) > 2 else ''
    subtype = re.sub(r'^(Search|Open|Get|Create|Park|Update|Add|Edit|Delete)',
                     lambda m: m.group(0), raw3.strip().split(' ')[0], flags=re.IGNORECASE)
    return (mod, mod, subtype)


# ── Data helpers ─────────────────────────────────────────────────────────────

def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df[~df['Transaction'].str.upper().str.startswith('TOTAL')].copy()
    df = df[df['Transaction'].str.strip() != ''].copy()

    classified = df['Transaction'].apply(classify_transaction)
    df['Module_Name']       = classified.apply(lambda x: x[0])
    df['Sub_Module']        = classified.apply(lambda x: x[1])
    df['Transaction_Subtype'] = classified.apply(lambda x: x[2])
    df['Transaction_Group'] = df['Transaction'].str.extract(r'_(\d{2})$')
    df['Prefix']            = df['Transaction'].apply(
        lambda t: re.match(r'^(SC\d+)', t).group(1) if re.match(r'^SC\d+', t) else 'COMMON'
    )
    return df


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
df_view = df_all[df_all['Transaction_Group'].isin(selected_groups)].copy() if selected_groups else df_all.copy()

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

# Tabs = one per Sub_Module in view
display_submods = sorted(df_view['Sub_Module'].dropna().unique())
if not display_submods:
    st.warning("No data for selected filters.")
    st.stop()

tabs = st.tabs(display_submods)
for tab, submod in zip(tabs, display_submods):
    with tab:
        df_mod = df_view[df_view['Sub_Module'] == submod]
        groups = sorted(df_mod['Transaction_Group'].dropna().unique())

        st.pyplot(plot_bar(df_mod, lmap, groups, submod))
        st.markdown("<br>", unsafe_allow_html=True)

        if len(groups) > 1:
            st.pyplot(plot_line(df_mod, lmap, groups, submod))
        else:
            st.info("Select 2+ builds in the sidebar to see the trend line chart.")

        with st.expander("📋 Raw data"):
            st.dataframe(
                df_mod[['Transaction','Module_Name','Sub_Module','Transaction_Subtype',
                         'Transaction_Group','Response time(sec)','Error %']]
                .rename(columns={'Transaction_Group': 'Build Code',
                                 'Transaction_Subtype': 'Subtype',
                                 'Module_Name': 'Module',
                                 'Sub_Module': 'Sub Module'}),
                use_container_width=True
            )
