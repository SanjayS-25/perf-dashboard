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
    .admin-box {
        background: #f0f4ff;
        border-left: 4px solid #4e6ef2;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        font-size: 13px;
    }
    .stTabs [data-baseweb="tab"] { font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# ── Config file paths (persisted on disk) ──
CONFIG_PATH = "dashboard_config.json"
CSV_PATH = "uploaded_data.csv"


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"build_names": {}, "csv_uploaded": False}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f)


def extract_module_name(transaction: str) -> str:
    """Extract human-readable module name.
    SC04_TC01_Search Nutri-Assess Patients_01 → Nutri-Assess
    SC03_TC01_Search Vision Patients → Vision
    """
    parts = transaction.split('_')
    if len(parts) < 3:
        return transaction

    raw = parts[2].strip()
    # Remove build suffix like _01 at end
    raw = re.sub(r'_\d{2}$', '', raw).strip()
    # Remove trailing ' Patients', ' Patient', ' Users'
    raw = re.sub(r'\s+(Patients?|Users?|Records?|Patient)\s*$', '', raw, flags=re.IGNORECASE).strip()
    # Remove leading action word (Search, Open, Get, Create, Park, Update, Print, Redirect)
    raw = re.sub(r'^(Search|Open|Get|Create|Park|Update|Print|Redirect\s+To|Add|Edit|Delete|View|Save|Submit|List)\s*[-–]?\s*', '', raw, flags=re.IGNORECASE).strip()
    return raw if raw else parts[0]


def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Skip rows without proper SC prefix
    df = df[df['Transaction'].str.match(r'^SC\d+_', na=False)].copy()
    df = df[~df['Transaction'].str.upper().str.startswith('TOTAL')].copy()

    df['Transaction_Subtype'] = (
        df['Transaction'].str.split('_').str[2]
        .str.strip().str.split(' ').str[0]
    )
    df['Transaction_Group'] = df['Transaction'].str.extract(r'_(\d{2})$')
    df['Prefix'] = df['Transaction'].str.split('_').str[0]
    df['Module_Name'] = df['Transaction'].apply(extract_module_name)
    return df


def plot_bar(df_mod, build_name_map, module_title):
    groups = sorted(df_mod['Transaction_Group'].dropna().unique())
    label_map = {g: build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)}
    build_order = [label_map[g] for g in groups]

    df_plot = df_mod.copy()
    df_plot['Build_Label'] = df_plot['Transaction_Group'].map(label_map)

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


def plot_line(df_mod, build_name_map, module_title):
    groups = sorted(df_mod['Transaction_Group'].dropna().unique())
    label_map = {g: build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)}
    build_order = [label_map[g] for g in groups]
    subtypes = sorted(df_mod['Transaction_Subtype'].dropna().unique())

    colors = sns.color_palette('tab10', len(subtypes))
    markers = ['o', 's', 'D', '^', 'v', 'P', '*', 'X', 'h', '+']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, sub in enumerate(subtypes):
        agg = (
            df_mod[df_mod['Transaction_Subtype'] == sub]
            .assign(Build_Label=lambda d: d['Transaction_Group'].map(label_map))
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

    ax.set_title(f'{module_title} — Response Time Trend Across Builds', fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build / Sprint', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(build_order)))
    ax.set_xticklabels(build_order)
    ax.legend(title='Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


# ════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════

cfg = load_config()

# ── Sidebar ──
with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/combo-chart.png", width=40)
    st.title("Dashboard Settings")

    mode = st.radio("Mode", ["👁️ View Dashboard", "⚙️ Admin Setup"], index=0)

# ════════════════════════════════════════════════════════════
#  ADMIN SETUP MODE
# ════════════════════════════════════════════════════════════
if mode == "⚙️ Admin Setup":
    st.title("⚙️ Admin Setup")
    st.markdown('<div class="admin-box">Configure once → share URL → everyone sees the same data & names.</div>', unsafe_allow_html=True)

    # Step 1: Upload CSV
    st.subheader("Step 1 — Upload CSV")
    uploaded = st.file_uploader("Upload your combined CSV (all modules, all builds)", type=["csv"])

    if uploaded:
        raw = pd.read_csv(uploaded)
        df = extract_fields(raw)
        df.to_csv(CSV_PATH, index=False)
        cfg["csv_uploaded"] = True

        all_groups = sorted(df['Transaction_Group'].dropna().unique())
        cfg["all_groups"] = all_groups
        save_config(cfg)
        st.success(f"✅ CSV saved! Found {len(all_groups)} builds: {', '.join(all_groups)}")

    # Step 2: Name the builds
    if cfg.get("csv_uploaded") and cfg.get("all_groups"):
        st.subheader("Step 2 — Name Each Build / Sprint")
        st.caption("These names will show on charts for all viewers.")

        all_groups = cfg["all_groups"]
        build_names = cfg.get("build_names", {})
        new_names = {}
        cols = st.columns(min(len(all_groups), 4))
        for i, g in enumerate(all_groups):
            with cols[i % len(cols)]:
                default = build_names.get(g, f"Sprint {i+1}")
                new_names[g] = st.text_input(f"Build **{g}** label", value=default, key=f"bn_{g}")

        if st.button("💾 Save Build Names", type="primary"):
            cfg["build_names"] = new_names
            save_config(cfg)
            st.success("✅ Build names saved! Switch to View Dashboard to see the result.")
            st.balloons()

    if not cfg.get("csv_uploaded"):
        st.info("Upload a CSV above to continue.")

# ════════════════════════════════════════════════════════════
#  VIEW DASHBOARD MODE
# ════════════════════════════════════════════════════════════
else:
    if not cfg.get("csv_uploaded") or not os.path.exists(CSV_PATH):
        st.title("📊 Performance Response Time Dashboard")
        st.warning("⚠️ No data loaded yet. Ask the admin to upload the CSV via Admin Setup mode.")
        st.stop()

    df_all = pd.read_csv(CSV_PATH)
    build_name_map = cfg.get("build_names", {})

    # Build module list with readable names
    module_map = {}  # prefix → module name
    for prefix, grp in df_all.groupby('Prefix'):
        name = grp['Module_Name'].mode()[0]
        module_map[prefix] = name

    # Deduplicate: if two prefixes get same module name, append prefix
    name_counts = {}
    for p, n in module_map.items():
        name_counts[n] = name_counts.get(n, 0) + 1
    for p in module_map:
        if name_counts[module_map[p]] > 1:
            module_map[p] = f"{module_map[p]} ({p})"

    sorted_prefixes = sorted(module_map.keys())
    module_options = {module_map[p]: p for p in sorted_prefixes}

    # ── Sidebar filters ──
    with st.sidebar:
        st.divider()
        st.subheader("🔍 Filter")

        all_label = "All Modules"
        selected_module = st.selectbox(
            "Module",
            [all_label] + list(module_options.keys()),
            help="Filter by module"
        )

        # Build filter
        all_groups = sorted(df_all['Transaction_Group'].dropna().unique())
        build_labels = {g: build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(all_groups)}
        build_display = list(build_labels.values())
        selected_builds = st.multiselect(
            "Builds / Sprints",
            options=build_display,
            default=build_display,
            help="Select which builds to compare"
        )

        # Reverse map selected build labels → group codes
        label_to_group = {v: k for k, v in build_labels.items()}
        selected_groups = [label_to_group[b] for b in selected_builds if b in label_to_group]

    # Filter data
    df_view = df_all[df_all['Transaction_Group'].isin(selected_groups)].copy()
    if selected_module != all_label:
        sel_prefix = module_options[selected_module]
        df_view = df_view[df_view['Prefix'] == sel_prefix]
        view_prefixes = [sel_prefix]
    else:
        view_prefixes = sorted_prefixes

    st.title("📊 Performance Response Time Dashboard")
    if selected_builds:
        st.caption(f"Comparing: **{'  vs  '.join(selected_builds)}**")

    # ── Metric cards ──
    c1, c2, c3, c4, c5 = st.columns(5)
    metrics = [
        ("Modules", df_view['Prefix'].nunique()),
        ("Builds", df_view['Transaction_Group'].nunique()),
        ("Subtypes", df_view['Transaction_Subtype'].nunique()),
        ("Avg RT (s)", f"{df_view['Response time(sec)'].mean():.3f}"),
        ("Max RT (s)", f"{df_view['Response time(sec)'].max():.3f}"),
    ]
    for col, (label, val) in zip([c1, c2, c3, c4, c5], metrics):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts — tabs per module ──
    display_prefixes = [p for p in view_prefixes if p in [r for r in df_view['Prefix'].unique()]]

    if not display_prefixes:
        st.warning("No data for selected filters.")
        st.stop()

    tab_labels = [module_map[p] for p in display_prefixes]
    tabs = st.tabs(tab_labels)

    for tab, prefix in zip(tabs, display_prefixes):
        with tab:
            df_mod = df_view[df_view['Prefix'] == prefix]
            mod_title = module_map[prefix]

            if df_mod['Transaction_Group'].nunique() < 1:
                st.info("No data for selected builds.")
                continue

            st.pyplot(plot_bar(df_mod, build_name_map, mod_title))
            st.markdown("<br>", unsafe_allow_html=True)

            if df_mod['Transaction_Group'].nunique() > 1:
                st.pyplot(plot_line(df_mod, build_name_map, mod_title))
            else:
                st.info("Select more than 1 build to see trend line chart.")

            with st.expander("📋 Raw data"):
                st.dataframe(
                    df_mod[['Transaction', 'Module_Name', 'Transaction_Subtype',
                             'Transaction_Group', 'Response time(sec)', 'Error %']].rename(
                        columns={'Transaction_Group': 'Build Code',
                                 'Transaction_Subtype': 'Subtype',
                                 'Module_Name': 'Module'}
                    ),
                    use_container_width=True
                )
