import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re

st.set_page_config(
    page_title="Performance Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        text-align: center;
    }
    .metric-label { font-size: 0.75rem; color: #888; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.9rem; font-weight: 700; color: #1a1a2e; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data(file):
    return pd.read_csv(file)


def extract_module_name(transaction: str) -> str:
    """Extract human-readable module name from transaction string.
    e.g. SC04_TC01_Search Nutri-Assess Patients_01 → Nutri-Assess
    Tries to find the meaningful part after TCxx_
    """
    parts = transaction.split('_')
    if len(parts) >= 3:
        raw = parts[2].strip()
        # Remove trailing ' Patients', ' Patient', ' Users' etc.
        raw = re.sub(r'\s*(Patients?|Users?|Records?)$', '', raw, flags=re.IGNORECASE).strip()
        # Remove leading action words like Search, Open, Get, Create, Park etc.
        raw = re.sub(r'^(Search|Open|Get|Create|Park|Add|Edit|Delete|View|Save|Submit|List)\s*[-–]?\s*', '', raw, flags=re.IGNORECASE).strip()
        if raw:
            return raw
    return parts[0]  # fallback to prefix


def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['Transaction_Subtype'] = (
        df['Transaction'].str.split('_').str[2]
        .str.strip().str.split(' ').str[0]
    )
    df['Transaction_Group'] = df['Transaction'].str.extract(r'(\d{2})$')
    df['Prefix'] = df['Transaction'].str.split('_').str[0]

    # Extract module name dynamically
    df['Module_Name'] = df['Transaction'].apply(extract_module_name)

    return df


def plot_bar(df_mod, build_name_map, module_title):
    groups = sorted(df_mod['Transaction_Group'].dropna().unique())
    build_order = [build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)]

    df_plot = df_mod.copy()
    df_plot['Build_Label'] = df_plot['Transaction_Group'].map(
        {g: build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)}
    )

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.barplot(
        data=df_plot, x='Build_Label', y='Response time(sec)',
        hue='Transaction_Subtype', palette='tab10',
        order=build_order, ax=ax
    )
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
    build_order = [build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)]
    label_map = {g: build_name_map.get(g, f'Build {i+1}') for i, g in enumerate(groups)}
    subtypes = sorted(df_mod['Transaction_Subtype'].dropna().unique())

    colors = sns.color_palette('tab10', len(subtypes))
    markers = ['o', 's', 'D', '^', 'v', 'P', '*', 'X', 'h', '+']

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, sub in enumerate(subtypes):
        agg = (
            df_mod[df_mod['Transaction_Subtype'] == sub]
            .assign(Build_Label=lambda d: d['Transaction_Group'].map(label_map))
            .groupby('Build_Label')['Response time(sec)']
            .mean()
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


# ── UI ──────────────────────────────────────────────────────────────────────

st.title("📊 Performance Response Time Dashboard")
st.caption("Upload your load test CSV — charts auto-generate per module with your custom build/sprint names.")

uploaded = st.file_uploader("Upload CSV", type=["csv"], label_visibility="collapsed")

if uploaded:
    raw = load_data(uploaded)
    df = extract_fields(raw)

    # ── Detect unique groups (builds) ──
    all_groups = sorted(df['Transaction_Group'].dropna().unique())

    # ── Sidebar: custom build names + module selector ──
    with st.sidebar:
        st.header("⚙️ Settings")

        st.subheader("🏷️ Build / Sprint Names")
        st.caption("Rename each build to your sprint or release label")
        build_name_map = {}
        for i, g in enumerate(all_groups):
            default = f"Sprint {i+1}"
            name = st.text_input(f"Build {g} name", value=default, key=f"build_{g}")
            build_name_map[g] = name

        st.divider()

        # Module selector — using detected module names
        st.subheader("📦 Module")
        prefixes = sorted(df['Prefix'].dropna().unique())
        module_display = {}
        for p in prefixes:
            # Get the most common module name for this prefix
            name = df[df['Prefix'] == p]['Module_Name'].mode()[0]
            module_display[p] = f"{name} ({p})"

        all_label = "All Modules"
        options = [all_label] + list(module_display.values())
        selected = st.selectbox("Select module", options)

    # Filter data
    if selected == all_label:
        df_view = df
        view_title = "All Modules"
    else:
        sel_prefix = [p for p, label in module_display.items() if label == selected][0]
        df_view = df[df['Prefix'] == sel_prefix]
        view_title = selected

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

    # ── Charts ──
    if selected == all_label and len(prefixes) > 1:
        tabs = st.tabs([module_display[p] for p in prefixes])
        for tab, p in zip(tabs, prefixes):
            with tab:
                df_mod = df[df['Prefix'] == p]
                mod_title = module_display[p]
                st.pyplot(plot_bar(df_mod, build_name_map, mod_title))
                st.markdown("<br>", unsafe_allow_html=True)
                st.pyplot(plot_line(df_mod, build_name_map, mod_title))
    else:
        st.pyplot(plot_bar(df_view, build_name_map, view_title))
        st.markdown("<br>", unsafe_allow_html=True)
        st.pyplot(plot_line(df_view, build_name_map, view_title))

    with st.expander("📋 View raw data"):
        st.dataframe(
            df_view[['Transaction', 'Module_Name', 'Transaction_Subtype',
                     'Transaction_Group', 'Response time(sec)', 'Error %']],
            use_container_width=True
        )

else:
    st.info("⬆️ Upload a CSV file to get started. Supports single or combined multi-module files.")
    st.markdown("""
    **Expected CSV columns:**
    - `Transaction` — e.g. `SC04_TC01_Search Nutri-Assess Patients_01`
    - `Response time(sec)`
    - `Error %`
    - `# No of Reqs` *(optional)*

    **Features:**
    - 🏷️ Set custom Sprint/Release names in the sidebar
    - 📦 Module auto-detected from transaction name
    - 📊 Bar chart + Line chart per module
    """)
