import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
import numpy as np
import io

st.set_page_config(
    page_title="Performance Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .main { background-color: #f8f9fb; }
    .block-container { padding-top: 2rem; }
    h1 { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        text-align: center;
    }
    .metric-label { font-size: 0.78rem; color: #888; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.9rem; font-weight: 700; color: #1a1a2e; }
    .chart-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        margin-bottom: 1.5rem;
    }
    .stSelectbox > div > div { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data(file) -> pd.DataFrame:
    return pd.read_csv(file)


def extract_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['Transaction_Subtype'] = (
        df['Transaction'].str.split('_').str[2]
        .str.strip().str.split(' ').str[0]
    )
    df['Transaction_Group'] = df['Transaction'].str.extract(r'(\d{2})$')
    df['Module'] = df['Transaction'].str.split('_').str[0]
    return df


def build_label_map(groups):
    sorted_g = sorted(groups)
    return {g: f'Build {i+1}' for i, g in enumerate(sorted_g)}


def plot_bar(df_mod, title):
    groups = sorted(df_mod['Transaction_Group'].dropna().unique())
    label_map = build_label_map(groups)
    df_mod = df_mod.copy()
    df_mod['Build_Label'] = df_mod['Transaction_Group'].map(label_map)
    build_order = [label_map[g] for g in groups]

    fig, ax = plt.subplots(figsize=(14, 6))
    sns.barplot(
        data=df_mod,
        x='Build_Label',
        y='Response time(sec)',
        hue='Transaction_Subtype',
        palette='tab10',
        order=build_order,
        ax=ax
    )
    for container, subtype in zip(ax.containers, ax.get_legend_handles_labels()[1]):
        for bar in container:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                        f'{h:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
                ax.text(bar.get_x() + bar.get_width() / 2, h / 2,
                        subtype, ha='center', va='center', fontsize=7,
                        color='white', fontweight='bold', rotation=90)

    ax.set_title(title, fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build Version', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.legend(title='Transaction Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.set_facecolor('#fafafa')
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


def plot_line(df_mod, title):
    groups = sorted(df_mod['Transaction_Group'].dropna().unique())
    label_map = build_label_map(groups)
    build_order = [label_map[g] for g in groups]
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

    ax.set_title(title, fontsize=13, fontweight='600', pad=12)
    ax.set_xlabel('Build Version', fontsize=11)
    ax.set_ylabel('Response Time (seconds)', fontsize=11)
    ax.set_xticks(range(len(build_order)))
    ax.set_xticklabels(build_order)
    ax.legend(title='Transaction Subtype', bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.set_facecolor('#fafafa')
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    return fig


# ── UI ──────────────────────────────────────────────────────────────────────

st.title("📊 Performance Response Time Dashboard")
st.caption("Upload your JMeter/load test CSV to explore response times across builds and modules.")

uploaded = st.file_uploader("Upload CSV file", type=["csv"], label_visibility="collapsed")

if uploaded:
    raw = load_data(uploaded)
    df = extract_fields(raw)

    modules = sorted(df['Module'].dropna().unique())
    all_option = "All Modules"

    col_filter, col_spacer = st.columns([2, 5])
    with col_filter:
        selected_module = st.selectbox(
            "Select Module",
            [all_option] + list(modules),
            help="Filter by module prefix (e.g. SC04)"
        )

    df_view = df if selected_module == all_option else df[df['Module'] == selected_module]

    # Metric cards
    groups_count = df_view['Transaction_Group'].nunique()
    subtypes_count = df_view['Transaction_Subtype'].nunique()
    avg_rt = df_view['Response time(sec)'].mean()
    max_rt = df_view['Response time(sec)'].max()
    min_rt = df_view['Response time(sec)'].min()

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, label, val in zip(
        [c1, c2, c3, c4, c5],
        ["Modules", "Builds", "Subtypes", "Avg RT (s)", "Max RT (s)"],
        [len(modules) if selected_module == all_option else 1,
         groups_count, subtypes_count,
         f"{avg_rt:.3f}", f"{max_rt:.3f}"]
    ):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{val}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts — if All Modules, show per-module tabs
    if selected_module == all_option and len(modules) > 1:
        tabs = st.tabs(modules)
        for tab, mod in zip(tabs, modules):
            with tab:
                df_mod = df[df['Module'] == mod]
                col1, col2 = st.columns(1), None

                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                fig_bar = plot_bar(df_mod, f"{mod} — Response time by build & subtype")
                st.pyplot(fig_bar)
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                fig_line = plot_line(df_mod, f"{mod} — Response time trend across builds")
                st.pyplot(fig_line)
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig_bar = plot_bar(df_view, f"{selected_module} — Response time by build & subtype")
        st.pyplot(fig_bar)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig_line = plot_line(df_view, f"{selected_module} — Response time trend across builds")
        st.pyplot(fig_line)
        st.markdown('</div>', unsafe_allow_html=True)

    # Raw data toggle
    with st.expander("View raw data"):
        st.dataframe(df_view[['Transaction', 'Transaction_Subtype', 'Transaction_Group',
                               'Response time(sec)', 'Error %']],
                     use_container_width=True)

else:
    st.info("⬆️ Upload a CSV file above to get started. Supports single or multi-module files.")
    st.markdown("""
    **Expected CSV columns:**
    - `Transaction` — e.g. `SC04_TC01_Search Nutri-Assess Patients_01`
    - `Response time(sec)`
    - `Error %`
    - `# No of Reqs` *(optional)*
    """)
