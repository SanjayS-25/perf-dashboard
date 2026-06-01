import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
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
        background: white;
        border-radius: 12px;
        padding: 1.1rem 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .metric-label { font-size: 0.72rem; color: #888; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.7rem; font-weight: 700; color: #1a1a2e; }
</style>
""", unsafe_allow_html=True)

# ── File paths ──
CONFIG_PATH = "dashboard_config.json"
CSV_PATH    = "uploaded_data.csv"

# ── IMPORTANT: set your admin password here ──
ADMIN_PASSWORD = "admin123"


# ════════════════════════════════════
#  Helpers
# ════════════════════════════════════

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"build_names": {}, "csv_uploaded": False, "all_groups": []}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f)


def extract_module_name(transaction: str) -> str:
    parts = transaction.split('_')
    if len(parts) < 3:
        return transaction
    raw = parts[2].strip()
    raw = re.sub(r'_\d{2}$', '', raw).strip()
    raw = re.sub(r'\s+(Patients?|Users?|Records?|Patient)\s*$', '', raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r'^(Search|Open|Get|Create|Park|Update|Print|Redirect\s+To|Add|Edit|Delete|View|Save|Submit|List)\s*[-–]?\s*', '', raw, flags=re.IGNORECASE).strip()
    return raw if raw else parts[0]


def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df[df['Transaction'].str.match(r'^SC\d+_', na=False)].copy()
    df = df[~df['Transaction'].str.upper().str.startswith('TOTAL')].copy()
    df['Transaction_Subtype'] = (
        df['Transaction'].str.split('_').str[2]
        .str.strip().str.split(' ').str[0]
    )
    df['Transaction_Group'] = df['Transaction'].str.extract(r'_(\d{2})$')
    df['Prefix']      = df['Transaction'].str.split('_').str[0]
    df['Module_Name'] = df['Transaction'].apply(extract_module_name)
    return df


def build_label_map(all_groups, build_name_map):
    """
    Maps raw group codes (e.g. '01','02','03') → custom names (e.g. 'Pg_Bouncer').
    Falls back to 'Build 1', 'Build 2' etc. if no custom name set.
    Always reloads from disk so saved names are picked up immediately.
    """
    fresh = load_config().get("build_names", {})
    # merge: fresh config wins over passed-in map
    merged = {**build_name_map, **fresh}
    return {g: merged.get(g, f'Build {i+1}') for i, g in enumerate(sorted(all_groups))}


def plot_bar(df_mod, lmap, module_title):
    groups      = sorted(df_mod['Transaction_Group'].dropna().unique())
    build_order = [lmap.get(g, g) for g in groups]
    df_plot     = df_mod.copy()
    df_plot['Build_Label'] = df_plot['Transaction_Group'].map(lmap)

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.barplot(data=df_plot, x='Build_Label', y='Response time(sec)',
                hue='Transaction_Subtype', palette='tab10',
                order=build_order, ax=ax)

    for container, subtype in zip(ax.containers, ax.get_legend_handles_labels()[1]):
        for bar in container:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                        f'{h:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
                ax.text(bar.get_x() + bar.get_width() / 2, h / 2,
                        subtype, ha='center', va='center',
                        fontsize=7, color='white', fontweight='bold', rotation=90)

    ax.set_title(f'{module_title} — Response Time by Build & Subtype', fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


def plot_line(df_mod, lmap, module_title):
    groups      = sorted(df_mod['Transaction_Group'].dropna().unique())
    build_order = [lmap.get(g, g) for g in groups]
    subtypes    = sorted(df_mod['Transaction_Subtype'].dropna().unique())
    colors      = sns.color_palette('tab10', len(subtypes))
    markers     = ['o', 's', 'D', '^', 'v', 'P', '*', 'X', 'h', '+']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, sub in enumerate(subtypes):
        agg = (
            df_mod[df_mod['Transaction_Subtype'] == sub]
            .assign(Build_Label=lambda d: d['Transaction_Group'].map(lmap))
            .groupby('Build_Label')['Response time(sec)'].mean()
            .reindex(build_order)
        )
        ax.plot(agg.index, agg.values, label=sub,
                color=colors[i], marker=markers[i % len(markers)],
                markersize=9, linewidth=2)
        for xi, (bl, val) in enumerate(agg.items()):
            if pd.notna(val):
                ax.text(xi, val + 0.015, f'{val:.2f}',
                        ha='center', va='bottom', fontsize=8,
                        fontweight='bold', color=colors[i])

    ax.set_title(f'{module_title} — Response Time Trend', fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(build_order)))
    ax.set_xticklabels(build_order)
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


# ════════════════════════════════════
#  SESSION STATE
# ════════════════════════════════════
if 'admin_unlocked' not in st.session_state:
    st.session_state.admin_unlocked = False

cfg = load_config()

# ════════════════════════════════════
#  SIDEBAR  — viewers only see filters
# ════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/combo-chart.png", width=36)
    st.markdown("### 📊 Performance Dashboard")
    st.divider()

    # Admin unlock (hidden at bottom, no label hinting)
    with st.expander("🔒 Admin", expanded=False):
        pw = st.text_input("Password", type="password", key="pw_input")
        if st.button("Unlock"):
            if pw == ADMIN_PASSWORD:
                st.session_state.admin_unlocked = True
                st.success("Admin unlocked!")
                st.rerun()
            else:
                st.error("Wrong password")
        if st.session_state.admin_unlocked:
            st.success("✅ Admin active")
            if st.button("Lock"):
                st.session_state.admin_unlocked = False
                st.rerun()

    st.divider()

    # Filters — always visible to everyone
    if cfg.get("csv_uploaded") and os.path.exists(CSV_PATH):
        st.subheader("🔍 Filter")

        df_all_temp = pd.read_csv(CSV_PATH)
        all_groups  = sorted(df_all_temp['Transaction_Group'].dropna().unique())
        lmap_temp   = build_label_map(all_groups, cfg.get("build_names", {}))

        # Module filter
        module_map_temp = {}
        for prefix, grp in df_all_temp.groupby('Prefix'):
            module_map_temp[prefix] = grp['Module_Name'].mode()[0]
        name_counts = {}
        for p, n in module_map_temp.items():
            name_counts[n] = name_counts.get(n, 0) + 1
        for p in module_map_temp:
            if name_counts[module_map_temp[p]] > 1:
                module_map_temp[p] = f"{module_map_temp[p]} ({p})"

        sorted_prefixes = sorted(module_map_temp.keys())
        module_options  = {module_map_temp[p]: p for p in sorted_prefixes}

        selected_module = st.selectbox("Module", ["All Modules"] + list(module_options.keys()))

        # Build filter
        build_display   = [lmap_temp[g] for g in all_groups]
        selected_builds = st.multiselect("Builds / Sprints", options=build_display, default=build_display)
        label_to_group  = {v: k for k, v in lmap_temp.items()}
        selected_groups = [label_to_group[b] for b in selected_builds if b in label_to_group]


# ════════════════════════════════════
#  ADMIN PANEL  (only if unlocked)
# ════════════════════════════════════
if st.session_state.admin_unlocked:
    st.title("⚙️ Admin Setup")
    st.info("Configure once — all viewers will see the updated data and build names automatically.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Step 1 — Upload CSV(s)")
        st.caption("Upload one or multiple CSV files — they will be merged automatically.")
        uploaded_files = st.file_uploader(
            "Upload CSV files (one per module or one combined)",
            type=["csv"],
            accept_multiple_files=True
        )
        if uploaded_files:
            frames = []
            file_names = []
            for f in uploaded_files:
                try:
                    raw = pd.read_csv(f)
                    frames.append(raw)
                    file_names.append(f.name)
                except Exception as e:
                    st.warning(f"⚠️ Could not read {f.name}: {e}")

            if frames:
                combined = pd.concat(frames, ignore_index=True)
                combined = combined.drop_duplicates()
                df = extract_fields(combined)
                df.to_csv(CSV_PATH, index=False)
                all_groups_new      = sorted(df["Transaction_Group"].dropna().unique())
                cfg["csv_uploaded"] = True
                cfg["all_groups"]   = all_groups_new
                existing = cfg.get("build_names", {})
                for i, g in enumerate(all_groups_new):
                    if g not in existing:
                        existing[g] = f"Build {i+1}"
                cfg["build_names"] = existing
                save_config(cfg)
                st.success(
                    f"✅ {len(uploaded_files)} file(s) merged!  "
                    f"{len(df)} total rows  |  "
                    f"{df['Prefix'].nunique()} modules  |  "
                    f"{len(all_groups_new)} builds detected: {', '.join(all_groups_new)}"
                )
                with st.expander("Files loaded"):
                    for name in file_names:
                        st.write(f"• {name}")
                st.rerun()

    with col2:
        st.subheader("Step 2 — Name Each Build / Sprint")
        if cfg.get("all_groups"):
            all_groups   = cfg["all_groups"]
            build_names  = cfg.get("build_names", {})
            new_names    = {}
            bcols        = st.columns(min(len(all_groups), 4))
            for i, g in enumerate(all_groups):
                with bcols[i % len(bcols)]:
                    new_names[g] = st.text_input(
                        f"Build **{g}**",
                        value=build_names.get(g, f"Build {i+1}"),
                        key=f"admin_bn_{g}"
                    )
            # Preview mapping before saving
            st.markdown("**Preview mapping:**  " + "  |  ".join([f" → **{v}**" for g, v in new_names.items()]))

            if st.button("💾 Save Build Names", type="primary"):
                # Store as string keys to match CSV values exactly
                cfg["build_names"] = {str(g): str(v) for g, v in new_names.items()}
                save_config(cfg)
                st.success("✅ Saved! Build names: " + ", ".join(new_names.values()))
                st.balloons()
                st.rerun()
        else:
            st.info("Upload a CSV in Step 1 first.")

    st.divider()
    st.caption("Switch to View mode to preview the dashboard as your team sees it.")
    st.stop()


# ════════════════════════════════════
#  VIEW DASHBOARD  (default for all)
# ════════════════════════════════════
st.title("📊 Performance Response Time Dashboard")

if not cfg.get("csv_uploaded") or not os.path.exists(CSV_PATH):
    st.warning("Dashboard not set up yet. Please contact your admin.")
    st.stop()

df_all      = pd.read_csv(CSV_PATH)
all_groups  = sorted(df_all['Transaction_Group'].dropna().unique())
lmap        = build_label_map(all_groups, cfg.get("build_names", {}))

# Module map
module_map = {}
for prefix, grp in df_all.groupby('Prefix'):
    module_map[prefix] = grp['Module_Name'].mode()[0]
name_counts = {}
for p, n in module_map.items():
    name_counts[n] = name_counts.get(n, 0) + 1
for p in module_map:
    if name_counts[module_map[p]] > 1:
        module_map[p] = f"{module_map[p]} ({p})"

sorted_prefixes = sorted(module_map.keys())
module_options  = {module_map[p]: p for p in sorted_prefixes}

# Apply sidebar filters
df_view = df_all[df_all['Transaction_Group'].isin(selected_groups)].copy()
if selected_module != "All Modules":
    sel_prefix  = module_options[selected_module]
    df_view     = df_view[df_view['Prefix'] == sel_prefix]
    view_prefixes = [sel_prefix]
else:
    view_prefixes = sorted_prefixes

# Build names caption
if selected_builds:
    st.caption(f"Comparing: **{'  vs  '.join(selected_builds)}**")

# Metric cards
c1, c2, c3, c4, c5 = st.columns(5)
for col, (label, val) in zip([c1,c2,c3,c4,c5], [
    ("Modules",   df_view['Prefix'].nunique()),
    ("Builds",    df_view['Transaction_Group'].nunique()),
    ("Subtypes",  df_view['Transaction_Subtype'].nunique()),
    ("Avg RT (s)", f"{df_view['Response time(sec)'].mean():.3f}"),
    ("Max RT (s)", f"{df_view['Response time(sec)'].max():.3f}"),
]):
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{val}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Module tabs + charts
display_prefixes = [p for p in view_prefixes if p in df_view['Prefix'].unique()]
if not display_prefixes:
    st.warning("No data for selected filters.")
    st.stop()

tabs = st.tabs([module_map[p] for p in display_prefixes])
for tab, prefix in zip(tabs, display_prefixes):
    with tab:
        df_mod    = df_view[df_view['Prefix'] == prefix]
        mod_title = module_map[prefix]

        st.pyplot(plot_bar(df_mod, lmap, mod_title))
        st.markdown("<br>", unsafe_allow_html=True)

        if df_mod['Transaction_Group'].nunique() > 1:
            st.pyplot(plot_line(df_mod, lmap, mod_title))
        else:
            st.info("Select 2+ builds in the sidebar to see the trend line chart.")

        with st.expander("📋 Raw data"):
            st.dataframe(
                df_mod[['Transaction','Module_Name','Transaction_Subtype',
                         'Transaction_Group','Response time(sec)','Error %']]
                .rename(columns={'Transaction_Group':'Build Code',
                                 'Transaction_Subtype':'Subtype',
                                 'Module_Name':'Module'}),
                use_container_width=True
            )
