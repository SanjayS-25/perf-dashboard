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


# ── Data helpers ─────────────────────────────────────────────────────────────

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
    df['Transaction_Subtype'] = df['Transaction'].str.split('_').str[2].str.strip().str.split(' ').str[0]
    df['Transaction_Group']   = df['Transaction'].str.extract(r'_(\d{2})$')
    df['Prefix']              = df['Transaction'].str.split('_').str[0]
    df['Module_Name']         = df['Transaction'].apply(extract_module_name)
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

        module_map_side = {}
        for prefix, grp in df_side.groupby('Prefix'):
            module_map_side[prefix] = grp['Module_Name'].mode()[0]
        name_counts = {}
        for p, n in module_map_side.items():
            name_counts[n] = name_counts.get(n, 0) + 1
        for p in module_map_side:
            if name_counts[module_map_side[p]] > 1:
                module_map_side[p] = f"{module_map_side[p]} ({p})"

        sorted_prefixes = sorted(module_map_side.keys())
        module_options  = {module_map_side[p]: p for p in sorted_prefixes}

        selected_module = st.selectbox("Module", ["All Modules"] + list(module_options.keys()))

        st.markdown("**Compare Builds**")
        st.caption("Select 1 to view single, 2+ to compare side by side")
        # Show as "Build 01 — Pg_Bouncer" for clarity
        build_display  = [f"Build {g}  —  {lmap_side[g]}" for g in all_groups]
        build_display_map = {f"Build {g}  —  {lmap_side[g]}": g for g in all_groups}

        selected_build_labels = st.multiselect(
            "Builds / Sprints",
            options=build_display,
            default=build_display,
            label_visibility="collapsed"
        )
        selected_groups = [build_display_map[b] for b in selected_build_labels if b in build_display_map]
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
            all_groups   = sorted(df_admin['Transaction_Group'].dropna().unique())
            current_names = st.session_state.build_names
            new_names     = {}
            bcols = st.columns(min(len(all_groups), 4))
            for i, g in enumerate(all_groups):
                with bcols[i % len(bcols)]:
                    new_names[str(g)] = st.text_input(
                        f"Build **{g}**",
                        value=current_names.get(str(g), f"Build {i+1}"),
                        key=f"admin_bn_{g}"
                    )

            st.markdown("**Preview:** " + "  |  ".join(
                [f"`{g}` → **{v}**" for g, v in new_names.items()]
            ))

            if st.button("💾 Apply Build Names", type="primary"):
                st.session_state.build_names = new_names
                save_build_names_local(new_names)
                st.success("✅ Applied! " + " | ".join(new_names.values()))
                st.rerun()
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

# Apply filters
df_view = df_all[df_all['Transaction_Group'].isin(selected_groups)].copy() if selected_groups else df_all.copy()
if selected_module != "All Modules" and selected_module in module_options:
    sel_prefix    = module_options[selected_module]
    df_view       = df_view[df_view['Prefix'] == sel_prefix]
    view_prefixes = [sel_prefix]
else:
    view_prefixes = sorted_prefixes

if selected_groups:
    build_labels_used = [lmap[g] for g in selected_groups if g in lmap]
    st.caption(f"Comparing: **{'  vs  '.join(build_labels_used)}**")

# Metric cards
c1, c2, c3, c4, c5 = st.columns(5)
for col, (label, val) in zip([c1, c2, c3, c4, c5], [
    ("Modules",    df_view['Prefix'].nunique()),
    ("Builds",     df_view['Transaction_Group'].nunique()),
    ("Subtypes",   df_view['Transaction_Subtype'].nunique()),
    ("Avg RT (s)", f"{df_view['Response time(sec)'].mean():.3f}"),
    ("Max RT (s)", f"{df_view['Response time(sec)'].max():.3f}"),
]):
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{val}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

display_prefixes = [p for p in view_prefixes if p in df_view['Prefix'].unique()]
if not display_prefixes:
    st.warning("No data for selected filters.")
    st.stop()

tabs = st.tabs([module_map[p] for p in display_prefixes])
for tab, prefix in zip(tabs, display_prefixes):
    with tab:
        df_mod    = df_view[df_view['Prefix'] == prefix]
        mod_title = module_map[prefix]
        groups    = sorted(df_mod['Transaction_Group'].dropna().unique())

        st.pyplot(plot_bar(df_mod, lmap, groups, mod_title))
        st.markdown("<br>", unsafe_allow_html=True)

        if len(groups) > 1:
            st.pyplot(plot_line(df_mod, lmap, groups, mod_title))
        else:
            st.info("Select 2+ builds in the sidebar to see the trend line chart.")

        with st.expander("📋 Raw data"):
            st.dataframe(
                df_mod[['Transaction','Module_Name','Transaction_Subtype',
                         'Transaction_Group','Response time(sec)','Error %']]
                .rename(columns={'Transaction_Group': 'Build Code',
                                 'Transaction_Subtype': 'Subtype',
                                 'Module_Name': 'Module'}),
                use_container_width=True
            )
