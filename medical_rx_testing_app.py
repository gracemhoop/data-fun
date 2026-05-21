import streamlit as st
import pandas as pd
import numpy as np
import re
import io
from datetime import date

st.set_page_config(page_title="Medical & Rx Claims Testing", layout="wide", page_icon="🏥")
st.title("Medical & Rx Claims Testing Tool")

def drilldown(summary_df, key, caption="Click a row to see matching records."):
    """Render a selectable summary table and return the selected row as a Series, or None."""
    st.caption(caption)
    sel = st.dataframe(
        summary_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"_dd_{key}",
    )
    rows = sel.selection.rows if sel.selection else []
    return summary_df.iloc[rows[0]] if rows else None

# ── FILE UPLOAD ───────────────────────────────────────────────────────────────
st.header("Upload File")
c1, c2, c3 = st.columns(3)
delim_label = c1.selectbox("Delimiter", [
    "Comma (,)", "Pipe (|)", "Tab (\\t)",
    "Tilde (~)", "Semicolon (;)", "Colon (:)",
    'Double quote (")', "Single quote (')",
])
skip_space  = c2.checkbox("Skip initial space")
no_quote    = c3.checkbox("Disable quoting")
DELIM = {
    "Comma (,)": ",", "Pipe (|)": "|", "Tab (\\t)": "\t",
    "Tilde (~)": "~", "Semicolon (;)": ";", "Colon (:)": ":",
    'Double quote (")': '"', "Single quote (')": "'",
}

uploaded = st.file_uploader("Upload CSV or TXT file", type=["csv", "txt"])
if uploaded is None:
    st.info("Upload a file above to begin.")
    st.stop()

# Clear stale session state whenever a new file is loaded
_file_id = f"{uploaded.name}_{uploaded.size}"
if st.session_state.get("_loaded_file_id") != _file_id:
    for _k in ["req_results", "dup_counts", "dup_key_cols", "dup_sel_idx",
                "proc_cats", "proc_series", "proc_col_saved",
                "dummy_hits", "filler_hits", "pop_results",
                "ev_hits", "pev_hits", "ct_dist", "gender_dist",
                "hdr_bad", "neg_paid", "zero_breakdown",
                "rb_result", "rb_demo_desc", "rb_field_desc",
                "adj_group_summary", "adj_base_cols",
                "ndc_summary", "ndc_wrong_mask", "ndc_blank_mask", "ndc_col_saved",
                "dv_ord_results", "dv_ord_date_cols"]:
        st.session_state.pop(_k, None)
    st.session_state["_loaded_file_id"] = _file_id

@st.cache_data
def load_file(data, sep, skip, nq):
    kw = {"dtype": str, "keep_default_na": False, "na_values": [], "skipinitialspace": skip, "sep": sep}
    if nq:
        kw["quoting"] = 3
    return pd.read_csv(io.BytesIO(data), **kw)

try:
    raw = uploaded.read()
    df  = load_file(raw, DELIM[delim_label], skip_space, no_quote)
except Exception as e:
    st.error(f"Could not load file: {e}")
    st.stop()

st.success(f"Loaded **{df.shape[0]:,} rows × {df.shape[1]} columns**")
with st.expander("Quick preview (first 20 rows)"):
    st.dataframe(df.head(20), use_container_width=True)

cols      = df.columns.tolist()
total_rows = len(df)
st.divider()

# ── TABS ──────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "🔍 Data Explorer",
    "🗂 File Structure",
    "👤 Member Identification",
    "⚖️ Adjudication",
    "✅ Field Accuracy",
    "📅 Date Validations",
    "📊 Plan & Benefit",
    "💰 Financial",
    "🏥 Service Classification",
    "📈 Volume & Distribution",
    "🔐 SSN Validation",
    "🏷 NPI Validation",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 0 — Data Explorer
# ════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Data Explorer")
    st.caption("Select columns to display, then add column filters — works like Excel AutoFilter.")

    vis_cols = st.multiselect("Columns to display", cols, default=cols, key="vis_cols")

    if not vis_cols:
        st.warning("Select at least one column.")
    else:
        with st.expander("Column Filters", expanded=True):
            filter_on = st.multiselect("Add filters for columns", vis_cols, key="filter_on")
            filters = {}
            if filter_on:
                grid = st.columns(min(len(filter_on), 4))
                for i, fc in enumerate(filter_on):
                    v = grid[i % 4].text_input(fc, key=f"fv_{fc}", placeholder="type to filter…")
                    if v.strip():
                        filters[fc] = v.strip()

        view = df[vis_cols].copy()
        for fc, fv in filters.items():
            view = view[view[fc].astype(str).str.contains(re.escape(fv), case=False, na=False)]

        st.caption(f"Showing **{len(view):,}** of **{total_rows:,}** rows")
        st.dataframe(view, use_container_width=True, height=560)
        st.download_button(
            "Download filtered data as CSV",
            data=view.to_csv(index=False).encode(),
            file_name=f"filtered_{uploaded.name.rsplit('.',1)[0]}.csv",
            mime="text/csv",
        )

    st.divider()

    # ── Unique record key recommendation ────────────────────────────────────
    st.markdown("#### Unique Record Key Recommendation")
    st.caption(
        "Columns where every row has a distinct value are strong candidates for a unique record key. "
        "Columns with very high cardinality (close to 100%) are listed first."
    )
    if st.button("Analyze columns", key="btn_uniq_rec"):
        uniq_stats = []
        for col in cols:
            n_uniq = df[col].nunique(dropna=False)
            pct    = n_uniq / total_rows * 100
            uniq_stats.append({"Column": col, "Unique Values": n_uniq,
                                "% Unique": round(pct, 2), "All Unique?": "✅ YES" if n_uniq == total_rows else ""})
        uniq_df = pd.DataFrame(uniq_stats).sort_values("% Unique", ascending=False)
        st.dataframe(uniq_df, use_container_width=True, height=400)

        perfect = [r["Column"] for _, r in uniq_df.iterrows() if r["All Unique?"] == "✅ YES"]
        near    = [r["Column"] for _, r in uniq_df.iterrows() if r["% Unique"] >= 90 and r["All Unique?"] != "✅ YES"]

        if perfect:
            st.success(f"**Perfect unique key candidates** (100% distinct): `{'`, `'.join(perfect)}`")
        if near:
            st.info(f"**Near-unique columns** (≥ 90% distinct, may work in combination): `{'`, `'.join(near)}`")
        if not perfect and not near:
            st.warning("No single column is highly unique. Try combining 2–3 columns as a composite key.")

    st.divider()

    # ── Unique values per column ─────────────────────────────────────────────
    st.markdown("#### Unique Values by Column")
    st.caption("Select columns to inspect all distinct values they contain.")
    uv_cols = st.multiselect("Columns to inspect", cols, key="uv_cols")
    excl_kw = st.text_input(
        "Exclude columns whose name contains these keywords (comma-separated, case-insensitive)",
        value="SSN, social",
        key="uv_excl_kw",
    )
    if st.button("Show unique values", key="btn_uv") and uv_cols:
        excl_terms = [t.strip().lower() for t in excl_kw.split(",") if t.strip()]
        for col in uv_cols:
            if any(t in col.lower() for t in excl_terms):
                st.markdown(f"**{col}** — *skipped (excluded keyword)*")
                continue
            uvals = df[col].dropna().unique().tolist()
            counts = df[col].value_counts(dropna=False).reset_index()
            counts.columns = ["Value", "Count"]
            counts["%"] = (counts["Count"] / total_rows * 100).round(2)
            with st.expander(f"**{col}** — {len(uvals):,} unique values", expanded=len(uv_cols) == 1):
                st.dataframe(counts, use_container_width=True, height=min(400, 38 + len(counts) * 35))

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — File Structure / Schema
# ════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("File Structure & Schema")

    # Filename
    fname = uploaded.name
    has_year = bool(re.search(r'\b(19|20)\d{2}\b', fname))
    st.write(f"**Filename:** `{fname}`")
    st.write(f"{'✅' if has_year else '❌'} 4-digit year in filename")
    st.write(f"**{len(cols)} columns detected:** `{'`, `'.join(cols[:20])}{'…' if len(cols)>20 else ''}`")

    # Dummy/test value scan
    st.markdown("---")
    st.markdown("**Dummy / Test Value Scan**")
    dummy_input = st.text_input(
        "Values to scan for (comma-separated, case-insensitive word match)",
        value="test,9999,123456,dummy,fake,sample",
        key="dummy_input",
    )
    if st.button("Scan", key="btn_dummy"):
        dvals = [v.strip() for v in dummy_input.split(",") if v.strip()]
        hits = []
        for col in cols:
            s = df[col].astype(str)
            for dv in dvals:
                cnt = s.str.contains(rf'\b{re.escape(dv)}\b', case=False, na=False).sum()
                if cnt:
                    hits.append({"Column": col, "Dummy Value": dv, "Count": int(cnt)})
        if hits:
            st.warning(f"Potential dummy values in {len({h['Column'] for h in hits})} column(s).")
            st.session_state["dummy_hits"] = pd.DataFrame(hits)
        else:
            st.success("No dummy/test values found.")
            st.session_state.pop("dummy_hits", None)

    if "dummy_hits" in st.session_state:
        row = drilldown(st.session_state["dummy_hits"], "dummy",
                        "Click a row to see all records containing that dummy value.")
        if row is not None:
            mask = df[row["Column"]].astype(str).str.contains(
                rf'\b{re.escape(str(row["Dummy Value"]))}\b', case=False, na=False)
            res = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{row['Column']}` containing `{row['Dummy Value']}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # Company code
    st.markdown("---")
    st.markdown("**Company / Client Code in Data**")
    co_col = st.selectbox("Column to inspect for company identifier", cols, key="co_col")
    if st.button("Show unique values", key="btn_co"):
        uvals = df[co_col].dropna().unique().tolist()
        st.write(f"**{len(uvals)} unique value(s)** in `{co_col}`:")
        st.write(sorted(uvals)[:50])

    # Duplicates
    st.markdown("---")
    st.markdown("**Duplicate Records**")
    fs_dup_cols = st.multiselect("Columns defining a unique record", cols, key="fs_dup_cols")
    if st.button("Check duplicates", key="btn_fs_dup") and fs_dup_cols:
        dup_mask = df.duplicated(subset=fs_dup_cols, keep=False)
        n_dup = int(dup_mask.sum())
        st.metric("Duplicate rows", f"{n_dup:,}")
        if n_dup:
            counts = (
                df[fs_dup_cols]
                .value_counts()
                .reset_index(name="count")
                .query("count > 1")
                .reset_index(drop=True)
            )
            st.session_state["dup_counts"]   = counts
            st.session_state["dup_key_cols"] = fs_dup_cols
            st.session_state["dup_sel_idx"]  = None
        else:
            st.success("No duplicate records found.")
            st.session_state.pop("dup_counts", None)

    # Show counts table + drill-down (persists after button press)
    if "dup_counts" in st.session_state and st.session_state["dup_counts"] is not None:
        counts      = st.session_state["dup_counts"]
        key_cols    = st.session_state["dup_key_cols"]

        st.caption("Click a row to see all duplicate records for that key combination.")
        sel = st.dataframe(
            counts,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="dup_sel_table",
        )

        selected_rows = sel.selection.rows if sel.selection else []
        if selected_rows:
            idx = selected_rows[0]
            row = counts.iloc[idx]

            # Build filter mask for the selected key
            mask = pd.Series([True] * len(df), index=df.index)
            for col in key_cols:
                mask &= df[col].astype(str) == str(row[col])
            matching = df[mask].reset_index(drop=True)

            st.markdown(f"#### All {len(matching)} duplicate rows for selected key")

            # Highlight columns that vary across duplicates — those are candidates to add
            varying = [c for c in df.columns if c not in key_cols and matching[c].nunique() > 1]
            constant = [c for c in df.columns if c not in key_cols and matching[c].nunique() <= 1]

            if varying:
                st.success(
                    f"**Columns that differ across these duplicates** (good candidates to add to your key): "
                    f"`{'`, `'.join(varying)}`"
                )
            if constant:
                st.info(
                    f"**Columns that are identical across all duplicates** (won't help distinguish): "
                    f"`{'`, `'.join(constant)}`"
                )

            st.dataframe(matching, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Member Identification
# ════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Member Identification & Eligibility Mapping")

    # Member ID uniqueness
    st.markdown("**Member ID → One Member Only**")
    mem_id_cols  = st.multiselect("Member ID column(s)", cols, key="mem_id")
    mem_bio_cols = st.multiselect("Member identity columns (Name, DOB, SSN…)", cols, key="mem_bio")
    if st.button("Check", key="btn_mem_uniq") and mem_id_cols and mem_bio_cols:
        tmp = df.copy()
        for c in mem_id_cols + mem_bio_cols:
            tmp[c] = tmp[c].astype(str).str.strip().str.upper()
        tmp["_ID"]   = list(zip(*(tmp[c] for c in mem_id_cols)))
        tmp["_DEMO"] = list(zip(*(tmp[c] for c in mem_bio_cols)))
        check = tmp.groupby("_ID")["_DEMO"].nunique().reset_index(name="distinct_identities")
        bad = check[check["distinct_identities"] > 1]
        st.metric("ID combos linked to multiple identities", f"{len(bad):,}")
        if not bad.empty:
            sample = bad["_ID"].head(10).tolist()
            st.dataframe(
                tmp[tmp["_ID"].isin(sample)][mem_id_cols + mem_bio_cols].drop_duplicates(),
                use_container_width=True,
            )
        else:
            st.success("✅ All member IDs map to exactly one member.")

    # Dependent age
    st.markdown("---")
    st.markdown("**Dependent Age Check** — Non-spouse dependents ≥ 26 should be < 2% of dependents")
    dob_col_mi   = st.selectbox("Date of Birth column", cols, key="mi_dob")
    rel_col_mi   = st.selectbox("Relationship / dependent code column", cols, key="mi_rel")
    dob_fmt_mi   = st.text_input("DOB format", value="%Y-%m-%d", key="mi_dob_fmt")
    spouse_kw_mi = st.text_input("Spouse codes (comma-separated)", value="spouse,01,S,SP", key="mi_spouse")
    emp_kw_mi    = st.text_input("Employee/self codes (comma-separated)", value="employee,self,EE,00,E", key="mi_emp")
    if st.button("Run", key="btn_dep_age"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_mi].astype(str).str.strip(), format=dob_fmt_mi, errors="coerce")
            tmp["_AGE"] = ((pd.Timestamp(date.today()) - tmp["_DOB"]).dt.days / 365.25).round(1)
            spouse_kws = {k.strip().lower() for k in spouse_kw_mi.split(",") if k.strip()}
            emp_kws    = {k.strip().lower() for k in emp_kw_mi.split(",") if k.strip()}
            tmp["_REL"]  = tmp[rel_col_mi].astype(str).str.strip().str.lower()
            is_emp       = tmp["_REL"].isin(emp_kws)
            is_spouse    = tmp["_REL"].isin(spouse_kws)
            is_dep       = ~is_emp
            problem_mask = is_dep & ~is_spouse & (tmp["_AGE"] >= 26)
            total_dep    = int(is_dep.sum())
            n_prob       = int(problem_mask.sum())
            pct          = n_prob / total_dep * 100 if total_dep else 0
            ma, mb, mc = st.columns(3)
            ma.metric("Total Dependents", f"{total_dep:,}")
            mb.metric("Non-Spouse ≥ 26", f"{n_prob:,}")
            mc.metric("% of Dependents", f"{pct:.2f}%",
                      delta="⚠️ > 2%" if pct > 2 else "✅ OK", delta_color="inverse")
            if n_prob:
                st.dataframe(tmp[problem_mask][[dob_col_mi, rel_col_mi, "_AGE"]].head(20), use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # Gender distribution
    st.markdown("---")
    st.markdown("**Gender / Sex at Birth Distribution**")
    gender_col = st.selectbox("Gender column", cols, key="gender_col")
    if st.button("Show", key="btn_gender"):
        dist = df[gender_col].value_counts(dropna=False).reset_index()
        dist.columns = ["Value", "Count"]
        dist["%"] = (dist["Count"] / total_rows * 100).round(2)
        st.session_state["gender_dist"]     = dist
        st.session_state["gender_col_saved"] = gender_col

    if "gender_dist" in st.session_state:
        row = drilldown(st.session_state["gender_dist"], "gender",
                        "Click a row to see all records with that gender value.")
        if row is not None:
            gcol = st.session_state["gender_col_saved"]
            val  = row["Value"]
            mask = df[gcol].astype(str) == str(val) if pd.notna(val) else df[gcol].isnull()
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{gcol}` = `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # Global data
    st.markdown("---")
    st.markdown("**Global Data Check** — Confirm no non-US records")
    addr_col = st.selectbox("Country / State / Address column", cols, key="addr_col")
    if st.button("Show unique values", key="btn_global"):
        uv = sorted(df[addr_col].dropna().astype(str).unique().tolist())
        st.write(f"**{len(uv)} unique values** in `{addr_col}`:")
        st.write(uv[:100])

    # ── DEMOGRAPHIC ALIGNMENT CHECKS ─────────────────────────────────────────
    st.divider()
    st.markdown("### Demographic Alignment Checks")
    st.caption(
        "Verify that member demographics make sense relative to their associated services, "
        "statuses, and relationships. Examples: toddlers should not be employees; newborns "
        "should not be receiving adult treatments; 95-year-olds should not have been recently hired."
    )

    # Shared config for all checks below
    dob_col_da  = st.selectbox("Date of Birth column", cols, key="da_dob")
    svc_col_da  = st.selectbox("Service / claim date column", cols, key="da_svc")
    dob_fmt_da  = st.text_input("Date format for DOB and service date", value="%Y-%m-%d", key="da_fmt")
    rel_col_da  = st.selectbox("Relationship / subscriber code column", cols, key="da_rel")
    emp_kw_da   = st.text_input(
        "Employee / subscriber codes (comma-separated)",
        value="employee,self,EE,00,E,18",
        key="da_emp_kw",
    )

    st.markdown("---")

    # ── 1. Age at service date (impossible / extreme ages) ───────────────────
    st.markdown("**1. Impossible or Extreme Age at Service Date**")
    st.caption("Flags records where the member's calculated age at time of service is negative, zero, or unusually high.")
    max_age_da = st.number_input("Flag members older than (years)", min_value=90, max_value=130, value=110, key="da_max_age")

    if st.button("Run", key="btn_da_age"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_SVC"] = pd.to_datetime(tmp[svc_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE_AT_SVC"] = ((tmp["_SVC"] - tmp["_DOB"]).dt.days / 365.25)

            neg_mask  = tmp["_AGE_AT_SVC"] < 0
            zero_mask = (tmp["_AGE_AT_SVC"] >= 0) & (tmp["_AGE_AT_SVC"] < (1/12))
            high_mask = tmp["_AGE_AT_SVC"] > max_age_da

            ma, mb, mc = st.columns(3)
            ma.metric("Service before birth (negative age)", f"{int(neg_mask.sum()):,}")
            mb.metric("Service within 1 month of birth", f"{int(zero_mask.sum()):,}")
            mc.metric(f"Age > {max_age_da} at service", f"{int(high_mask.sum()):,}")

            for label, mask in [
                ("Service before birth", neg_mask),
                (f"Age > {max_age_da} at service", high_mask),
            ]:
                if mask.any():
                    with st.expander(f"Sample rows — {label}"):
                        show = tmp[mask][[dob_col_da, svc_col_da, "_AGE_AT_SVC"]].head(20)
                        show = show.rename(columns={"_AGE_AT_SVC": "Age at Service (yrs)"})
                        st.dataframe(show.round(1), use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ── 2. Minors coded as employees ─────────────────────────────────────────
    st.markdown("**2. Minors Coded as Employees / Subscribers**")
    st.caption("Children below minimum working age should not appear as the employee/subscriber on a claim.")
    min_work_age = st.number_input("Minimum employee age", min_value=14, max_value=25, value=16, key="da_min_work")

    if st.button("Run", key="btn_da_minor_emp"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE"] = ((pd.Timestamp(date.today()) - tmp["_DOB"]).dt.days / 365.25)
            emp_kws = {k.strip().lower() for k in emp_kw_da.split(",") if k.strip()}
            tmp["_REL"] = tmp[rel_col_da].astype(str).str.strip().str.lower()
            mask = tmp["_REL"].isin(emp_kws) & (tmp["_AGE"] < min_work_age) & tmp["_AGE"].notna()
            st.metric(f"Members < {min_work_age} coded as employee/subscriber", f"{int(mask.sum()):,}")
            if mask.any():
                show = tmp[mask][[dob_col_da, rel_col_da, "_AGE"]].rename(columns={"_AGE": "Age (yrs)"})
                st.dataframe(show.head(20).round(1), use_container_width=True)
            else:
                st.success(f"✅ No members under {min_work_age} coded as employees.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ── 3. Elderly active employees ──────────────────────────────────────────
    st.markdown("**3. Unusually Old Active Employees**")
    st.caption(
        "Members coded as active employees above a certain age warrant review — "
        "e.g., a 95-year-old active employee is likely a data error."
    )
    max_emp_age = st.number_input("Flag employees older than (years)", min_value=70, max_value=110, value=85, key="da_max_emp_age")

    if st.button("Run", key="btn_da_old_emp"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE"] = ((pd.Timestamp(date.today()) - tmp["_DOB"]).dt.days / 365.25)
            emp_kws = {k.strip().lower() for k in emp_kw_da.split(",") if k.strip()}
            tmp["_REL"] = tmp[rel_col_da].astype(str).str.strip().str.lower()
            mask = tmp["_REL"].isin(emp_kws) & (tmp["_AGE"] > max_emp_age) & tmp["_AGE"].notna()
            st.metric(f"Employees older than {max_emp_age}", f"{int(mask.sum()):,}")
            if mask.any():
                show = tmp[mask][[dob_col_da, rel_col_da, "_AGE"]].rename(columns={"_AGE": "Age (yrs)"})
                st.dataframe(show.drop_duplicates().head(20).round(1), use_container_width=True)
            else:
                st.success(f"✅ No employees found over age {max_emp_age}.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ── 4. Gender vs. gender-specific procedure codes ────────────────────────
    st.markdown("**4. Gender vs. Gender-Specific Procedure Codes**")
    st.caption(
        "Flags records where a member receives a procedure that is specific to the opposite sex. "
        "Examples: prostate or vasectomy procedures on females; hysterectomy or mammogram on males."
    )

    proc_col_da   = st.selectbox("Procedure code column", cols, key="da_proc_col")
    gender_col_da = st.selectbox("Gender column", cols, key="da_gender_col")

    gc1, gc2 = st.columns(2)
    male_codes_input   = gc1.text_input(
        "Male member code values (comma-separated)",
        value="M,Male,MALE,1,m",
        key="da_male_vals",
    )
    female_codes_input = gc2.text_input(
        "Female member code values (comma-separated)",
        value="F,Female,FEMALE,2,f",
        key="da_female_vals",
    )
    pc1, pc2 = st.columns(2)
    male_only_procs = pc1.text_area(
        "Male-only procedure codes (one per line)",
        value="55250\n55700\n55801\n55866\n54520\n54150\n54161\n54400\n54410",
        key="da_male_procs",
        height=130,
        help="Examples: vasectomy (55250), prostate biopsy (55700), orchiectomy (54520)",
    )
    female_only_procs = pc2.text_area(
        "Female-only procedure codes (one per line)",
        value="58150\n58260\n58550\n59400\n59510\n77067\n76856\n58661\n58353\n58600",
        key="da_female_procs",
        height=130,
        help="Examples: hysterectomy (58150/58260), OB delivery (59400), mammogram (77067), tubal ligation (58600)",
    )

    if st.button("Run", key="btn_da_gender_proc"):
        try:
            tmp = df.copy()
            tmp["_GENDER"] = tmp[gender_col_da].astype(str).str.strip()
            tmp["_PROC"]   = tmp[proc_col_da].astype(str).str.strip()

            male_vals   = {v.strip() for v in male_codes_input.split(",") if v.strip()}
            female_vals = {v.strip() for v in female_codes_input.split(",") if v.strip()}
            male_procs  = {v.strip() for v in male_only_procs.splitlines() if v.strip()}
            fem_procs   = {v.strip() for v in female_only_procs.splitlines() if v.strip()}

            is_male   = tmp["_GENDER"].isin(male_vals)
            is_female = tmp["_GENDER"].isin(female_vals)

            # Female getting male-only procedure
            fem_with_male_proc = is_female & tmp["_PROC"].isin(male_procs)
            # Male getting female-only procedure
            male_with_fem_proc = is_male & tmp["_PROC"].isin(fem_procs)

            ma, mb = st.columns(2)
            ma.metric("Female members with male-only procedure", f"{int(fem_with_male_proc.sum()):,}")
            mb.metric("Male members with female-only procedure", f"{int(male_with_fem_proc.sum()):,}")

            for label, mask in [
                ("Female with male-only procedure", fem_with_male_proc),
                ("Male with female-only procedure", male_with_fem_proc),
            ]:
                if mask.any():
                    with st.expander(f"Sample rows — {label}"):
                        st.dataframe(tmp[mask][[gender_col_da, proc_col_da]].head(20), use_container_width=True)

            if not fem_with_male_proc.any() and not male_with_fem_proc.any():
                st.success("✅ No gender-procedure mismatches found.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ── 5. Infants / newborns with adult procedures ──────────────────────────
    st.markdown("**5. Infants or Young Children with Adult Procedures**")
    st.caption(
        "Newborns and toddlers should not be receiving adult treatments such as IVF, "
        "colonoscopy, mammogram, or cardiac stent placement."
    )

    infant_age_thresh = st.number_input(
        "Flag members younger than (years) receiving adult procedures",
        min_value=1, max_value=10, value=2, key="da_infant_thresh"
    )
    adult_procs_input = st.text_area(
        "Adult-only procedure codes to flag (one per line)",
        value="58970\n58974\n58976\n45378\n45380\n77067\n36221\n33533\n55250\n55700\n58150\n59400",
        key="da_adult_procs",
        height=130,
        help="Examples: IVF (58970-58976), colonoscopy (45378), mammogram (77067), cardiac bypass (33533)",
    )
    proc_col_infant = st.selectbox("Procedure code column", cols, key="da_proc_infant")

    if st.button("Run", key="btn_da_infant"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_SVC"] = pd.to_datetime(tmp[svc_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE_AT_SVC"] = ((tmp["_SVC"] - tmp["_DOB"]).dt.days / 365.25)
            tmp["_PROC"] = tmp[proc_col_infant].astype(str).str.strip()
            adult_procs = {v.strip() for v in adult_procs_input.splitlines() if v.strip()}

            mask = (tmp["_AGE_AT_SVC"] < infant_age_thresh) & tmp["_PROC"].isin(adult_procs) & tmp["_AGE_AT_SVC"].notna()
            st.metric(f"Members under {infant_age_thresh} with adult procedure codes", f"{int(mask.sum()):,}")
            if mask.any():
                show = tmp[mask][[dob_col_da, svc_col_da, proc_col_infant, "_AGE_AT_SVC"]].rename(
                    columns={"_AGE_AT_SVC": "Age at Service (yrs)"}
                )
                st.dataframe(show.head(20).round(2), use_container_width=True)
            else:
                st.success(f"✅ No members under {infant_age_thresh} found with adult procedure codes.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ── 6. Pediatric age vs. diagnosis / procedure plausibility ─────────────
    st.markdown("**6. Age Bracket vs. Procedure Plausibility (Custom)**")
    st.caption(
        "Define an age range and a set of procedure codes that should never appear for members "
        "in that range. Useful for flagging things like retirement diagnoses in 20-year-olds, "
        "pediatric codes on adults, or OB codes on members over 60."
    )

    ab1, ab2 = st.columns(2)
    age_lo = ab1.number_input("Age range — minimum", min_value=0,   max_value=130, value=0,  key="da_age_lo")
    age_hi = ab2.number_input("Age range — maximum", min_value=0,   max_value=130, value=17, key="da_age_hi")
    flag_procs_input = st.text_area(
        "Procedure codes that should NOT appear in this age range (one per line)",
        key="da_flag_procs",
        height=100,
        placeholder="e.g. 99381 (newborn preventive) should not appear on a 45-year-old",
    )
    proc_col_age = st.selectbox("Procedure code column", cols, key="da_proc_age_col")

    if st.button("Run", key="btn_da_age_proc") and flag_procs_input.strip():
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_SVC"] = pd.to_datetime(tmp[svc_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE_AT_SVC"] = ((tmp["_SVC"] - tmp["_DOB"]).dt.days / 365.25)
            tmp["_PROC"] = tmp[proc_col_age].astype(str).str.strip()
            flag_procs = {v.strip() for v in flag_procs_input.splitlines() if v.strip()}

            in_range = (tmp["_AGE_AT_SVC"] >= age_lo) & (tmp["_AGE_AT_SVC"] <= age_hi)
            has_flag = tmp["_PROC"].isin(flag_procs)
            mask = in_range & has_flag & tmp["_AGE_AT_SVC"].notna()

            st.metric(
                f"Members aged {age_lo}–{age_hi} with flagged procedure codes",
                f"{int(mask.sum()):,}"
            )
            if mask.any():
                show = tmp[mask][[dob_col_da, svc_col_da, proc_col_age, "_AGE_AT_SVC"]].rename(
                    columns={"_AGE_AT_SVC": "Age at Service (yrs)"}
                )
                st.dataframe(show.head(30).round(1), use_container_width=True)
            else:
                st.success(f"✅ No flagged procedure codes found for members aged {age_lo}–{age_hi}.")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── 7. Custom Demographic Rule Builder ───────────────────────────────────
    st.markdown("---")
    st.markdown("### Custom Demographic Rule Builder")
    st.caption(
        "Define a member group by age (and optionally gender), then add field conditions to find "
        "suspicious combinations — e.g. 'members under age 2 WHERE relationship = EE' or "
        "'members over 85 WHERE hire date is within the last 3 years'."
    )

    st.markdown("#### Step 1 — Define the member group")
    rb_dob_col = st.selectbox("Date of Birth column", cols, key="rb_dob")
    rb_ref_col = st.selectbox("Reference date (age measured at)", ["Today"] + cols, key="rb_ref")
    rb_fmt     = st.text_input("Date format", value="%Y-%m-%d", key="rb_fmt")

    rb_c1, rb_c2 = st.columns(2)
    rb_age_lo = rb_c1.number_input("Minimum age (inclusive)", min_value=0,   max_value=130, value=0,  key="rb_age_lo")
    rb_age_hi = rb_c2.number_input("Maximum age (inclusive)", min_value=0,   max_value=130, value=2,  key="rb_age_hi")

    rb_gender_on  = st.checkbox("Also filter by gender", key="rb_gender_on")
    if rb_gender_on:
        rb_gc1, rb_gc2 = st.columns(2)
        rb_gender_col  = rb_gc1.selectbox("Gender column", cols, key="rb_gender_col")
        rb_gender_vals = rb_gc2.text_input("Gender values to include (comma-separated)", value="M,Male,MALE", key="rb_gender_vals")

    st.markdown("#### Step 2 — Add suspicious field conditions")
    st.caption("All conditions below are combined with AND. Every condition must be true for a row to be flagged.")

    OPERATORS = ["=", "≠", "contains", "does not contain", "in list", "not in list",
                 ">", "<", "≥", "≤", "is blank", "is not blank",
                 "date within X days of another column"]

    n_conds = int(st.number_input("Number of conditions", min_value=1, max_value=8, value=1, key="rb_n_conds"))

    conditions = []
    for i in range(n_conds):
        st.markdown(f"**Condition {i+1}**")
        cc1, cc2, cc3 = st.columns([2, 1.5, 2])
        cond_col = cc1.selectbox("Column", cols, key=f"rb_ccol_{i}")
        cond_op  = cc2.selectbox("Operator", OPERATORS, key=f"rb_cop_{i}")

        if cond_op == "date within X days of another column":
            cc3a, cc3b = st.columns(2)
            cond_days  = cc3a.number_input("Days", min_value=1, value=365, key=f"rb_days_{i}")
            cond_other = cc3b.selectbox("Other date column", cols, key=f"rb_other_{i}")
            conditions.append((cond_col, cond_op, (cond_days, cond_other)))
        elif cond_op in ("is blank", "is not blank"):
            conditions.append((cond_col, cond_op, None))
        else:
            cond_val = cc3.text_input("Value", key=f"rb_cval_{i}",
                                      placeholder="For 'in list', separate values with commas")
            conditions.append((cond_col, cond_op, cond_val))

    st.markdown("#### Step 3 — Run")
    if st.button("Find suspicious records", key="btn_rb"):
        try:
            tmp = df.copy()

            # Parse DOB and compute age
            tmp["_DOB"] = pd.to_datetime(tmp[rb_dob_col].astype(str).str.strip(), format=rb_fmt, errors="coerce")
            if rb_ref_col == "Today":
                ref_ts = pd.Timestamp(date.today())
                tmp["_AGE"] = ((ref_ts - tmp["_DOB"]).dt.days / 365.25)
            else:
                tmp["_REF"] = pd.to_datetime(tmp[rb_ref_col].astype(str).str.strip(), format=rb_fmt, errors="coerce")
                tmp["_AGE"] = ((tmp["_REF"] - tmp["_DOB"]).dt.days / 365.25)

            # Age filter
            age_mask = (tmp["_AGE"] >= rb_age_lo) & (tmp["_AGE"] <= rb_age_hi) & tmp["_AGE"].notna()

            # Optional gender filter
            if rb_gender_on:
                gvals = {v.strip() for v in rb_gender_vals.split(",") if v.strip()}
                age_mask &= tmp[rb_gender_col].astype(str).str.strip().isin(gvals)

            # Apply each condition
            cond_mask = pd.Series([True] * len(tmp), index=tmp.index)
            cond_descriptions = []
            for (c_col, c_op, c_val) in conditions:
                s = tmp[c_col].astype(str).str.strip()

                if c_op == "=":
                    m = s == str(c_val)
                    cond_descriptions.append(f"`{c_col}` = `{c_val}`")
                elif c_op == "≠":
                    m = s != str(c_val)
                    cond_descriptions.append(f"`{c_col}` ≠ `{c_val}`")
                elif c_op == "contains":
                    m = s.str.contains(re.escape(str(c_val)), case=False, na=False)
                    cond_descriptions.append(f"`{c_col}` contains `{c_val}`")
                elif c_op == "does not contain":
                    m = ~s.str.contains(re.escape(str(c_val)), case=False, na=False)
                    cond_descriptions.append(f"`{c_col}` does not contain `{c_val}`")
                elif c_op == "in list":
                    vals = {v.strip() for v in str(c_val).split(",") if v.strip()}
                    m = s.isin(vals)
                    cond_descriptions.append(f"`{c_col}` in [{c_val}]")
                elif c_op == "not in list":
                    vals = {v.strip() for v in str(c_val).split(",") if v.strip()}
                    m = ~s.isin(vals)
                    cond_descriptions.append(f"`{c_col}` not in [{c_val}]")
                elif c_op == ">":
                    m = pd.to_numeric(tmp[c_col], errors="coerce") > float(c_val)
                    cond_descriptions.append(f"`{c_col}` > {c_val}")
                elif c_op == "<":
                    m = pd.to_numeric(tmp[c_col], errors="coerce") < float(c_val)
                    cond_descriptions.append(f"`{c_col}` < {c_val}")
                elif c_op == "≥":
                    m = pd.to_numeric(tmp[c_col], errors="coerce") >= float(c_val)
                    cond_descriptions.append(f"`{c_col}` ≥ {c_val}")
                elif c_op == "≤":
                    m = pd.to_numeric(tmp[c_col], errors="coerce") <= float(c_val)
                    cond_descriptions.append(f"`{c_col}` ≤ {c_val}")
                elif c_op == "is blank":
                    m = tmp[c_col].isnull() | (s == "")
                    cond_descriptions.append(f"`{c_col}` is blank")
                elif c_op == "is not blank":
                    m = ~(tmp[c_col].isnull() | (s == ""))
                    cond_descriptions.append(f"`{c_col}` is not blank")
                elif c_op == "date within X days of another column":
                    n_days, other_col = c_val
                    d_a = pd.to_datetime(tmp[c_col].astype(str).str.strip(), format=rb_fmt, errors="coerce")
                    d_b = pd.to_datetime(tmp[other_col].astype(str).str.strip(), format=rb_fmt, errors="coerce")
                    m = ((d_a - d_b).dt.days.abs() <= n_days) & d_a.notna() & d_b.notna()
                    cond_descriptions.append(f"`{c_col}` within {n_days} days of `{other_col}`")
                else:
                    m = pd.Series([True] * len(tmp), index=tmp.index)

                cond_mask &= m

            final_mask = age_mask & cond_mask
            result = df[final_mask.values].copy()
            result.insert(0, "Age (yrs)", tmp.loc[final_mask, "_AGE"].round(1).values)

            # Build readable description
            gender_desc = ""
            if rb_gender_on:
                gender_desc = f", gender in [{rb_gender_vals}]"
            demo_desc  = f"Age {rb_age_lo}–{rb_age_hi}{gender_desc}"
            field_desc = " AND ".join(cond_descriptions) if cond_descriptions else "(no field conditions)"

            st.session_state["rb_result"]      = result
            st.session_state["rb_demo_desc"]   = demo_desc
            st.session_state["rb_field_desc"]  = field_desc

        except Exception as e:
            st.error(f"Error: {e}")

    if "rb_result" in st.session_state:
        result     = st.session_state["rb_result"]
        demo_desc  = st.session_state["rb_demo_desc"]
        field_desc = st.session_state["rb_field_desc"]

        st.metric(f"Flagged records — {demo_desc} WHERE {field_desc}", f"{len(result):,}")

        if not result.empty:
            # Show breakdown by any categorical column the user picks
            breakdown_col = st.selectbox(
                "Break down results by column (optional)",
                ["(none)"] + [c for c in cols if result[c].nunique() <= 50],
                key="rb_breakdown",
            )
            if breakdown_col != "(none)":
                bk = result[breakdown_col].value_counts().reset_index()
                bk.columns = [breakdown_col, "Count"]
                bk["%"] = (bk["Count"] / len(result) * 100).round(2)
                st.dataframe(bk, use_container_width=True)

            st.markdown(f"#### All {len(result):,} flagged rows")
            st.dataframe(result, use_container_width=True)
            st.download_button(
                "Download flagged rows as CSV",
                data=result.to_csv(index=False).encode(),
                file_name="demographic_alignment_flags.csv",
                mime="text/csv",
            )
        else:
            st.success("✅ No records match this combination — looks clean.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Adjudication
# ════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Adjudication")

    # Claim line uniqueness
    st.markdown("**Claim Line Uniqueness**")
    cl_id_cols = st.multiselect("Fields that uniquely identify a claim line", cols, key="cl_id")
    if st.button("Check", key="btn_cl_uniq") and cl_id_cols:
        n_dup = int(df.duplicated(subset=cl_id_cols, keep=False).sum())
        st.metric("Non-unique claim lines", f"{n_dup:,}")
        if n_dup:
            counts = df[cl_id_cols].value_counts().reset_index(name="count").query("count > 1")
            st.dataframe(counts.head(30), use_container_width=True)
        else:
            st.success("✅ All claim lines are uniquely identifiable.")

    # Claim Grouping & Reversal/Adjustment Validation
    st.markdown("---")
    st.markdown("**Claim Grouping & Reversal / Adjustment Validation**")
    st.caption(
        "Validates that reprocessed, adjusted, or reversed claims can be grouped and traced. "
        "Works with or without an original transaction ID column — you can use claim sequence "
        "numbers, adjustment counters, or status/type codes instead."
    )

    adj_method = st.radio(
        "How are adjustments / reversals identified in this data?",
        [
            "Original Transaction ID column (links reversal to original)",
            "Sequence / adjustment number (claims with same base ID, sequence > 1 are adjustments)",
            "Status / type code (a column flags reversals, adjustments, voids, etc.)",
        ],
        key="adj_method",
    )

    st.markdown("##### Base claim identifier")
    base_id_cols = st.multiselect(
        "Column(s) that form the base claim ID (e.g. Claim Number, or Claim Number + Line Number)",
        cols, key="adj_base_id",
    )

    # ── Method A: Original Transaction ID ────────────────────────────────────
    if adj_method.startswith("Original"):
        orig_col_adj = st.selectbox("Original Transaction ID column", cols, key="adj_orig")
        null_vals    = st.text_input(
            "Values that mean 'no original' (blank, zero, etc.) — comma-separated",
            value="0,,nan,NULL,N/A", key="adj_null_vals",
        )
        if st.button("Run", key="btn_rev"):
            null_set = {v.strip() for v in null_vals.split(",")}
            tx_s   = df[base_id_cols[0]].astype(str).str.strip() if base_id_cols else pd.Series(dtype=str)
            orig_s = df[orig_col_adj].astype(str).str.strip()
            non_null = orig_s[~orig_s.isin(null_set)]
            unmatched_ids = set(non_null) - set(tx_s)

            st.metric("Reversal / adjustment rows (non-null orig ID)", f"{len(non_null):,}")
            st.metric("Unmatched original IDs (no corresponding claim)", f"{len(unmatched_ids):,}")

            if unmatched_ids:
                unmatched_rows = df[orig_s.isin(unmatched_ids)].reset_index(drop=True)
                st.warning(f"⚠️ {len(unmatched_rows):,} rows reference an original claim that doesn't exist in this file.")
                with st.expander("Show unmatched rows"):
                    st.dataframe(unmatched_rows, use_container_width=True)
            else:
                st.success("✅ All reversals/adjustments have a matching original claim in this file.")

            if base_id_cols:
                st.markdown("##### Claim groups (base ID → all related rows)")
                st.caption("Click a row to see all claims in that group.")
                group_summary = (
                    df.assign(_ORIG=orig_s)
                    .groupby(base_id_cols)
                    .agg(
                        Total_Rows=("_ORIG", "count"),
                        Has_Reversal=("_ORIG", lambda x: (~x.isin(null_set)).any()),
                    )
                    .reset_index()
                    .sort_values("Total_Rows", ascending=False)
                )
                st.session_state["adj_group_summary"] = group_summary
                st.session_state["adj_base_cols"]     = base_id_cols

    # ── Method B: Sequence / Adjustment Number ────────────────────────────────
    elif adj_method.startswith("Sequence"):
        seq_col = st.selectbox("Sequence / adjustment number column", cols, key="adj_seq_col")
        seq_orig_val = st.text_input(
            "Value(s) that represent the ORIGINAL claim (comma-separated)",
            value="1,0,01", key="adj_seq_orig",
        )
        if st.button("Run", key="btn_rev"):
            if not base_id_cols:
                st.warning("Select at least one base claim ID column above.")
            else:
                orig_vals = {v.strip() for v in seq_orig_val.split(",") if v.strip()}
                tmp = df.copy()
                tmp["_SEQ"] = tmp[seq_col].astype(str).str.strip()
                tmp["_IS_ADJ"] = ~tmp["_SEQ"].isin(orig_vals)

                # For each adjusted claim, check there is at least one original in the same group
                merged = tmp.merge(
                    tmp[~tmp["_IS_ADJ"]][base_id_cols].drop_duplicates().assign(_HAS_ORIG=True),
                    on=base_id_cols, how="left",
                )
                adj_rows   = merged[merged["_IS_ADJ"]]
                no_orig    = adj_rows[adj_rows["_HAS_ORIG"].isna()]

                st.metric("Adjusted / reprocessed rows (seq ≠ original value)", f"{len(adj_rows):,}")
                st.metric("Adjusted rows with NO matching original in file", f"{len(no_orig):,}")

                if not no_orig.empty:
                    st.warning(f"⚠️ {len(no_orig):,} adjustment rows have no original claim in this file.")
                    with st.expander("Show orphaned adjustments"):
                        st.dataframe(no_orig.drop(columns=["_SEQ","_IS_ADJ","_HAS_ORIG"]), use_container_width=True)
                else:
                    st.success("✅ Every adjusted/reprocessed claim has a matching original in this file.")

                # Group summary
                group_summary = (
                    tmp.groupby(base_id_cols)
                    .agg(
                        Total_Rows=("_SEQ", "count"),
                        Sequences=("_SEQ", lambda x: sorted(x.unique().tolist())),
                        Adjustment_Rows=("_IS_ADJ", "sum"),
                    )
                    .reset_index()
                    .sort_values("Total_Rows", ascending=False)
                )
                st.session_state["adj_group_summary"] = group_summary
                st.session_state["adj_base_cols"]     = base_id_cols

    # ── Method C: Status / Type Code ─────────────────────────────────────────
    elif adj_method.startswith("Status"):
        status_col_adj = st.selectbox("Status / type column", cols, key="adj_status_col")
        reversal_vals  = st.text_input(
            "Values that indicate a reversal or adjustment (comma-separated, case-insensitive)",
            value="R,REV,Reversal,VOID,ADJ,Adjustment,Corrected", key="adj_rev_vals",
        )
        original_vals  = st.text_input(
            "Values that indicate the original paid claim (comma-separated)",
            value="P,Paid,Approved,A,Original", key="adj_orig_vals",
        )
        if st.button("Run", key="btn_rev"):
            if not base_id_cols:
                st.warning("Select at least one base claim ID column above.")
            else:
                rev_set  = {v.strip().lower() for v in reversal_vals.split(",") if v.strip()}
                orig_set = {v.strip().lower() for v in original_vals.split(",") if v.strip()}

                tmp = df.copy()
                tmp["_STATUS_N"] = tmp[status_col_adj].astype(str).str.strip().str.lower()
                tmp["_IS_REV"]   = tmp["_STATUS_N"].isin(rev_set)
                tmp["_IS_ORIG"]  = tmp["_STATUS_N"].isin(orig_set)

                rev_rows  = tmp[tmp["_IS_REV"]]
                orig_rows = tmp[tmp["_IS_ORIG"]]

                st.metric("Reversal / adjustment rows", f"{len(rev_rows):,}")
                st.metric("Original / paid rows", f"{len(orig_rows):,}")

                # Find reversals whose base ID has no matching original
                orig_groups = set(map(tuple, orig_rows[base_id_cols].astype(str).values.tolist()))
                rev_rows["_KEY"] = list(map(tuple, rev_rows[base_id_cols].astype(str).values.tolist()))
                orphaned = rev_rows[~rev_rows["_KEY"].isin(orig_groups)]

                st.metric("Reversals with no matching original claim in file", f"{len(orphaned):,}")
                if not orphaned.empty:
                    st.warning(f"⚠️ {len(orphaned):,} reversal rows have no corresponding original in this file.")
                    with st.expander("Show orphaned reversals"):
                        st.dataframe(orphaned.drop(columns=["_STATUS_N","_IS_REV","_IS_ORIG","_KEY"]),
                                     use_container_width=True)
                else:
                    st.success("✅ Every reversal has a matching original claim in this file.")

                # Distribution of status values
                st.markdown("##### Status value distribution")
                dist = df[status_col_adj].value_counts(dropna=False).reset_index()
                dist.columns = ["Status", "Count"]
                dist["%"] = (dist["Count"] / total_rows * 100).round(2)

                row = drilldown(dist, "adj_status", "Click a status to see all rows with that value.")
                if row is not None:
                    mask = df[status_col_adj].astype(str).str.strip() == str(row["Status"])
                    res  = df[mask].reset_index(drop=True)
                    st.markdown(f"#### Status `{row['Status']}` — {len(res):,} rows")
                    st.dataframe(res, use_container_width=True)

                group_summary = (
                    tmp.groupby(base_id_cols)
                    .agg(
                        Total_Rows=("_STATUS_N", "count"),
                        Statuses=("_STATUS_N", lambda x: sorted(x.unique().tolist())),
                        Reversal_Rows=("_IS_REV", "sum"),
                        Original_Rows=("_IS_ORIG", "sum"),
                    )
                    .reset_index()
                    .sort_values("Total_Rows", ascending=False)
                )
                st.session_state["adj_group_summary"] = group_summary
                st.session_state["adj_base_cols"]     = base_id_cols

    # ── Shared: group drill-down ──────────────────────────────────────────────
    if "adj_group_summary" in st.session_state and base_id_cols:
        st.markdown("##### Claim group summary")
        grp_row = drilldown(
            st.session_state["adj_group_summary"], "adj_group",
            "Click a claim group to see all rows belonging to it."
        )
        if grp_row is not None:
            bc   = st.session_state["adj_base_cols"]
            mask = pd.Series([True] * len(df), index=df.index)
            for c in bc:
                mask &= df[c].astype(str) == str(grp_row[c])
            res = df[mask].reset_index(drop=True)
            label = " | ".join(str(grp_row[c]) for c in bc)
            st.markdown(f"#### Claim group `{label}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # One member per claim header
    st.markdown("---")
    st.markdown("**One Member Per Claim Header**")
    hdr_col   = st.selectbox("Claim header / number column", cols, key="hdr_col")
    mbr_col_a = st.selectbox("Member ID column", cols, key="mbr_col_a")
    if st.button("Run", key="btn_hdr"):
        per_claim = df.groupby(hdr_col)[mbr_col_a].nunique()
        bad = per_claim[per_claim > 1].reset_index()
        bad.columns = [hdr_col, "Distinct Members"]
        st.metric("Claims with > 1 member", f"{len(bad):,}")
        if not bad.empty:
            st.session_state["hdr_bad"]       = bad
            st.session_state["hdr_col_saved"] = hdr_col
        else:
            st.success("✅ Each claim header maps to exactly one member.")
            st.session_state.pop("hdr_bad", None)

    if "hdr_bad" in st.session_state:
        row = drilldown(st.session_state["hdr_bad"], "hdr_bad",
                        "Click a row to see all records for that claim header.")
        if row is not None:
            hc   = st.session_state["hdr_col_saved"]
            res  = df[df[hc].astype(str) == str(row[hc])].reset_index(drop=True)
            st.markdown(f"#### Claim `{row[hc]}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # Final paid >= $0
    st.markdown("---")
    st.markdown("**Final Paid ≥ $0 per Claim**")
    grp_col  = st.selectbox("Claim grouping column", cols, key="grp_col")
    paid_col = st.selectbox("Paid amount column", cols, key="paid_col_adj")
    if st.button("Run", key="btn_final_paid"):
        tmp = df.copy()
        tmp["_PAID"] = pd.to_numeric(tmp[paid_col], errors="coerce")
        group_sum = tmp.groupby(grp_col)["_PAID"].sum().round(2).reset_index(name="Total Paid")
        neg = group_sum[group_sum["Total Paid"] < 0]
        st.metric("Claims with negative final paid", f"{len(neg):,}")
        if not neg.empty:
            st.session_state["neg_paid"]       = neg.reset_index(drop=True)
            st.session_state["neg_grp_saved"]  = grp_col
        else:
            st.success("✅ All claims have final paid ≥ $0.")
            st.session_state.pop("neg_paid", None)

    if "neg_paid" in st.session_state:
        row = drilldown(st.session_state["neg_paid"], "neg_paid",
                        "Click a row to see all records for that claim group.")
        if row is not None:
            gc  = st.session_state["neg_grp_saved"]
            res = df[df[gc].astype(str) == str(row[gc])].reset_index(drop=True)
            st.markdown(f"#### Claim group `{row[gc]}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Field Accuracy & Completion
# ════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Field Accuracy & Completion")

    # Population overview
    st.markdown("**Full Field Population Overview**")
    if st.button("Run", key="btn_pop"):
        rows_out = []
        for col in cols:
            s = df[col]
            null_n  = int(s.isnull().sum())
            blank_n = int((s.astype(str).str.strip() == "").sum())
            empty_n = null_n + blank_n
            filled  = total_rows - empty_n
            n_uniq  = int(s.nunique(dropna=True))
            rows_out.append({
                "Column": col,
                "Filled": filled,
                "Empty": empty_n,
                "Fill %": round(filled / total_rows * 100, 2),
                "Unique Values": n_uniq,
                "⚠️ Constant": "YES" if n_uniq <= 1 and filled > 0 else "",
                "⚠️ 100% Null": "YES" if filled == 0 else "",
            })
        st.session_state["pop_results"] = pd.DataFrame(rows_out).sort_values("Fill %")

    if "pop_results" in st.session_state:
        row = drilldown(st.session_state["pop_results"], "pop",
                        "Click a row to see records where that field is empty.", )
        if row is not None:
            col_name  = row["Column"]
            empty_mask = df[col_name].isnull() | (df[col_name].astype(str).str.strip() == "")
            res = df[empty_mask].reset_index(drop=True)
            if not res.empty:
                st.markdown(f"#### `{col_name}` — {len(res):,} empty rows")
                st.dataframe(res, use_container_width=True)
            else:
                st.success(f"✅ `{col_name}` has no empty rows.")

    # Required fields
    st.markdown("---")
    st.markdown("**Required Fields — Must Be 100% Populated**")
    req_cols = st.multiselect("Select required fields", cols, key="req_cols")
    if st.button("Check", key="btn_req") and req_cols:
        req_rows = []
        for col in req_cols:
            s = df[col]
            empty_n = int(s.isnull().sum()) + int((s.astype(str).str.strip() == "").sum())
            fill_pct = (total_rows - empty_n) / total_rows * 100
            req_rows.append({
                "Column": col,
                "Filled": total_rows - empty_n,
                "Empty": empty_n,
                "Fill %": round(fill_pct, 2),
                "Status": "✅ Pass" if empty_n == 0 else f"❌ FAIL — {empty_n:,} empty",
            })
        st.session_state["req_results"] = pd.DataFrame(req_rows)

    if "req_results" in st.session_state:
        req_df = st.session_state["req_results"]
        st.caption("Click a failing row to see example records where that field is empty.")
        sel_req = st.dataframe(
            req_df,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="req_sel_table",
        )
        selected = sel_req.selection.rows if sel_req.selection else []
        if selected:
            chosen_col = req_df.iloc[selected[0]]["Column"]
            empty_mask = df[chosen_col].isnull() | (df[chosen_col].astype(str).str.strip() == "")
            example_rows = df[empty_mask].reset_index(drop=True)
            if not example_rows.empty:
                st.markdown(f"#### Rows where `{chosen_col}` is empty ({len(example_rows):,} total)")
                st.dataframe(example_rows, use_container_width=True)
            else:
                st.success(f"✅ No empty rows found for `{chosen_col}`.")

    # Default / filler values
    st.markdown("---")
    st.markdown("**Default / Filler Value Detection**")
    filler_input = st.text_input(
        "Filler values to scan (comma-separated, exact match)",
        value="999999999,1753-01-01,0000000000,000000000,99999,UNKNOWN,N/A,NULL,NONE,DEFAULT,0",
        key="filler_input",
    )
    if st.button("Scan", key="btn_filler"):
        fvals = [v.strip() for v in filler_input.split(",") if v.strip()]
        hits = []
        for col in cols:
            s = df[col].astype(str).str.strip()
            for fv in fvals:
                cnt = int((s == fv).sum())
                if cnt:
                    hits.append({"Column": col, "Filler Value": fv, "Count": cnt,
                                 "%": round(cnt / total_rows * 100, 2)})
        if hits:
            st.warning(f"Filler values found in {len({h['Column'] for h in hits})} column(s).")
            st.session_state["filler_hits"] = pd.DataFrame(hits)
        else:
            st.success("No filler values found.")
            st.session_state.pop("filler_hits", None)

    if "filler_hits" in st.session_state:
        row = drilldown(st.session_state["filler_hits"], "filler",
                        "Click a row to see all records containing that filler value.")
        if row is not None:
            mask = df[row["Column"]].astype(str).str.strip() == str(row["Filler Value"])
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{row['Column']}` = `{row['Filler Value']}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # NDC
    st.markdown("---")
    st.markdown("**NDC Validation** — Must be exactly 11 characters (Rx only)")
    auto_ndc = [c for c in cols if "ndc" in c.lower()]
    ndc_col  = st.selectbox("NDC column", auto_ndc if auto_ndc else cols, key="ndc_col")
    if st.button("Run", key="btn_ndc"):
        s = df[ndc_col].astype(str).str.strip()
        blank_mask   = df[ndc_col].isnull() | (s == "")
        valid_mask   = s.str.len() == 11
        wrong_mask   = ~blank_mask & ~valid_mask
        blank_n      = int(blank_mask.sum())
        valid_n      = int(valid_mask.sum())
        wrong_len    = int(wrong_mask.sum())
        ma, mb, mc   = st.columns(3)
        ma.metric("Valid (11 chars)", f"{valid_n:,}")
        mb.metric("Wrong length", f"{wrong_len:,}")
        mc.metric("Blank / Missing", f"{blank_n:,}")

        # Build a summary by actual length for drill-down
        if wrong_len or blank_n:
            ndc_summary_rows = []
            if wrong_len:
                length_counts = (
                    df[wrong_mask][[ndc_col]]
                    .assign(_LEN=s[wrong_mask].str.len())
                    .groupby("_LEN")
                    .size()
                    .reset_index(name="Count")
                    .rename(columns={"_LEN": "Length"})
                )
                length_counts["%"] = (length_counts["Count"] / total_rows * 100).round(2)
                length_counts.insert(0, "Category", "Wrong length")
                ndc_summary_rows.append(length_counts)
            if blank_n:
                ndc_summary_rows.append(pd.DataFrame([{
                    "Category": "Blank / Missing", "Length": None,
                    "Count": blank_n, "%": round(blank_n / total_rows * 100, 2)
                }]))
            ndc_summary = pd.concat(ndc_summary_rows, ignore_index=True)
            st.session_state["ndc_summary"]    = ndc_summary
            st.session_state["ndc_wrong_mask"] = wrong_mask.values
            st.session_state["ndc_blank_mask"] = blank_mask.values
            st.session_state["ndc_col_saved"]  = ndc_col

    if "ndc_summary" in st.session_state:
        row = drilldown(st.session_state["ndc_summary"], "ndc",
                        "Click a row to see all records with that NDC length / issue.")
        if row is not None:
            nc = st.session_state["ndc_col_saved"]
            if row["Category"] == "Blank / Missing":
                mask = st.session_state["ndc_blank_mask"]
            else:
                s2   = df[nc].astype(str).str.strip()
                mask = st.session_state["ndc_wrong_mask"] & (s2.str.len() == int(row["Length"])).values
            res = df[mask].reset_index(drop=True)
            label = f"Blank / Missing" if row["Category"] == "Blank / Missing" else f"Length {int(row['Length'])}"
            st.markdown(f"#### NDC — {label} — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # Low-variation fields
    st.markdown("---")
    st.markdown("**Suspiciously Low Variation** — Fields that may be hardcoded or constant")
    var_thresh = st.slider("Flag columns with ≤ N unique values", 1, 20, 3, key="var_thresh")
    if st.button("Run", key="btn_var"):
        low_var = [
            {"Column": c, "Unique Values": df[c].nunique(dropna=True),
             "Sample Values": str(df[c].dropna().unique().tolist()[:5])}
            for c in cols if 0 < df[c].nunique(dropna=True) <= var_thresh
        ]
        if low_var:
            st.dataframe(pd.DataFrame(low_var), use_container_width=True)
        else:
            st.success(f"No columns with ≤ {var_thresh} unique values.")

    # Expected values check
    st.markdown("---")
    st.markdown("**Allowed Values Check** — Verify a column only contains vendor-specified values")
    ev_col  = st.selectbox("Column to validate", cols, key="ev_col")
    ev_vals = st.text_area("Allowed values (one per line)", key="ev_vals", height=100)
    if st.button("Run", key="btn_ev") and ev_vals.strip():
        allowed = {v.strip() for v in ev_vals.splitlines() if v.strip()}
        actual  = set(df[ev_col].dropna().astype(str).str.strip().unique())
        unexpected = actual - allowed
        st.metric("Unexpected values", len(unexpected))
        if unexpected:
            bad_mask = df[ev_col].astype(str).str.strip().isin(unexpected)
            ev_df = df.loc[bad_mask, [ev_col]].value_counts().reset_index(name="Count")
            st.session_state["ev_hits"]      = ev_df
            st.session_state["ev_col_saved"] = ev_col
        else:
            st.success(f"✅ All values in `{ev_col}` match the allowed set.")
            st.session_state.pop("ev_hits", None)

    if "ev_hits" in st.session_state:
        row = drilldown(st.session_state["ev_hits"], "ev",
                        "Click a row to see all records with that unexpected value.")
        if row is not None:
            ec   = st.session_state["ev_col_saved"]
            val  = row[ec]
            mask = df[ec].astype(str).str.strip() == str(val)
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{ec}` = `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — Date Validations
# ════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Date Validations")

    auto_date_cols = [c for c in cols if any(x in c.lower() for x in ["date", "dob"])]
    date_cols_tab  = st.multiselect("Date columns to analyze", cols, default=auto_date_cols, key="dv_cols")
    date_fmt_tab   = st.text_input("Expected date format", value="%Y-%m-%d", key="dv_fmt",
                                   help="e.g. %Y-%m-%d | %m/%d/%Y | %Y%m%d | %m%d%Y")
    sys_defaults   = st.text_input("System-default sentinel dates to flag (comma-separated)",
                                   value="1753-01-01,9999-12-31,1900-01-01,0001-01-01", key="dv_defaults")

    if st.button("Run date analysis", key="btn_dv") and date_cols_tab:
        sentinel_vals = {v.strip() for v in sys_defaults.split(",") if v.strip()}
        today = pd.Timestamp(date.today())
        for col in date_cols_tab:
            st.markdown(f"**{col}**")
            raw_s   = df[col].astype(str).str.strip()
            parsed  = pd.to_datetime(raw_s, format=date_fmt_tab, errors="coerce")
            blank_n = int((raw_s == "").sum()) + int(df[col].isnull().sum())
            parse_err = int(parsed.isnull().sum()) - blank_n
            future_n  = int((parsed > today).sum())
            no4yr     = int(raw_s[raw_s != ""].apply(lambda v: not bool(re.search(r'(19|20)\d{2}', v))).sum())
            default_n = int(raw_s.isin(sentinel_vals).sum())
            ma, mb, mc, md, me = st.columns(5)
            ma.metric("Blank", f"{blank_n:,}")
            mb.metric("Parse Errors", f"{parse_err:,}")
            mc.metric("Future Dates", f"{future_n:,}")
            md.metric("No 4-digit Year", f"{no4yr:,}")
            me.metric("Sentinel Defaults", f"{default_n:,}")
            if future_n:
                with st.expander(f"Future date rows — {col}"):
                    st.dataframe(df[parsed > today][[col]].head(10), use_container_width=True)
            if default_n:
                with st.expander(f"Sentinel date rows — {col}"):
                    st.dataframe(df[raw_s.isin(sentinel_vals)][[col]].head(10), use_container_width=True)

    st.markdown("---")
    st.markdown("**Date Order Check** — Flag rows where Column A > Column B (illogical)")
    n_ord = int(st.number_input("Number of comparisons", 0, 8, 2, key="dv_n_ord"))
    order_comps = []
    if date_cols_tab:
        for i in range(n_ord):
            ca, cb = st.columns(2)
            a = ca.selectbox(f"Earlier date [{i+1}]", date_cols_tab, key=f"dv_oa_{i}")
            b = cb.selectbox(f"Later date [{i+1}]",   date_cols_tab, index=min(1, len(date_cols_tab)-1), key=f"dv_ob_{i}")
            order_comps.append((a, b))
    if st.button("Run order check", key="btn_dv_ord") and date_cols_tab and order_comps:
        tmp = df.copy()
        for col in date_cols_tab:
            tmp[col] = pd.to_datetime(tmp[col].astype(str).str.strip(), format=date_fmt_tab, errors="coerce")
        comp_results = []
        for a, b in order_comps:
            if a != b:
                issue = (tmp[a] > tmp[b]).fillna(False)
                comp_results.append({"Earlier (A)": a, "Later (B)": b,
                                     "Label": f"{a} > {b}",
                                     "Rows": int(issue.sum()),
                                     "_mask": issue.values})
        st.session_state["dv_ord_results"]   = comp_results
        st.session_state["dv_ord_date_cols"] = date_cols_tab

    if "dv_ord_results" in st.session_state:
        comp_results = st.session_state["dv_ord_results"]
        if not any(r["Rows"] for r in comp_results):
            st.success("✅ No date order violations found.")
        else:
            summary = pd.DataFrame([{"Comparison": r["Label"], "Rows with Violation": r["Rows"]}
                                     for r in comp_results])
            row = drilldown(summary, "dv_ord",
                            "Click a comparison to see the rows where that date order is violated.")
            if row is not None:
                chosen = next(r for r in comp_results if r["Label"] == row["Comparison"])
                res = df[chosen["_mask"]].reset_index(drop=True)
                # Show all date columns so the user can see all dates side by side
                disp_cols = [c for c in st.session_state["dv_ord_date_cols"] if c in res.columns]
                st.markdown(f"#### `{chosen['Label']}` — {len(res):,} rows")
                st.dataframe(res[disp_cols + [c for c in res.columns if c not in disp_cols]],
                             use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — Plan & Benefit
# ════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Plan & Benefit Information")

    plan_cols = st.multiselect("Plan-related columns to review", cols, key="plan_cols")
    if st.button("Show value distributions", key="btn_plan") and plan_cols:
        for col in plan_cols:
            st.markdown(f"**{col}** — {df[col].nunique()} unique values")
            dist = df[col].value_counts(dropna=False).reset_index()
            dist.columns = ["Value", "Count"]
            dist["%"] = (dist["Count"] / total_rows * 100).round(2)
            st.dataframe(dist, use_container_width=True)

    st.markdown("---")
    st.markdown("**Expected Values Check** — Flag values not in the vendor spec")
    pev_col  = st.selectbox("Column to validate", cols, key="pev_col")
    pev_vals = st.text_area("Allowed values (one per line)", key="pev_vals", height=100)
    if st.button("Run", key="btn_pev") and pev_vals.strip():
        allowed  = {v.strip() for v in pev_vals.splitlines() if v.strip()}
        bad_mask = ~df[pev_col].astype(str).str.strip().isin(allowed) & df[pev_col].notna()
        bad_vals = df.loc[bad_mask, pev_col].value_counts().reset_index(name="Count")
        st.metric("Unexpected values", len(bad_vals))
        if not bad_vals.empty:
            st.session_state["pev_hits"]      = bad_vals
            st.session_state["pev_col_saved"] = pev_col
        else:
            st.success(f"✅ All values in `{pev_col}` match the allowed set.")
            st.session_state.pop("pev_hits", None)

    if "pev_hits" in st.session_state:
        row = drilldown(st.session_state["pev_hits"], "pev",
                        "Click a row to see all records with that unexpected value.")
        if row is not None:
            pc   = st.session_state["pev_col_saved"]
            val  = row[pc]
            mask = df[pc].astype(str).str.strip() == str(val)
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{pc}` = `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 8 — Financial Reconciliation
# ════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Financial Reconciliation")

    fin_kw   = ["paid", "allowed", "billed", "amount", "amt", "copay", "ded", "oop"]
    auto_fin = [c for c in cols if any(k in c.lower() for k in fin_kw)]

    # Sum check
    st.markdown("**Column Sum Check** — Verify sum of columns equals a target")
    fin_sum_cols = st.multiselect("Columns to sum", cols, key="fin_sum")
    fin_cmp_col  = st.selectbox("Should equal", cols, key="fin_cmp")
    if st.button("Run", key="btn_fin_sum") and fin_sum_cols:
        tmp  = df.copy()
        all_f = list(set(fin_sum_cols + [fin_cmp_col]))
        for c in all_f:
            tmp[c] = pd.to_numeric(tmp[c], errors="coerce")
        row_sums   = tmp[fin_sum_cols].sum(axis=1, skipna=False).round(2)
        cmp_vals   = tmp[fin_cmp_col].round(2)
        valid_mask = tmp[all_f].notna().all(axis=1)
        match_mask = (row_sums == cmp_vals) & valid_mask
        valid_n    = int(valid_mask.sum())
        match_n    = int(match_mask.sum())
        pct        = match_n / valid_n * 100 if valid_n else 0
        ma, mb, mc = st.columns(3)
        ma.metric("Matching rows", f"{match_n:,}")
        mb.metric("Valid rows", f"{valid_n:,}")
        mc.metric("Match %", f"{pct:.2f}%")
        mismatch = tmp[~match_mask & valid_mask]
        if not mismatch.empty:
            st.dataframe(mismatch[all_f].head(20), use_container_width=True)

    # Allowed <= Billed
    st.markdown("---")
    st.markdown("**Allowed ≤ Billed**")
    billed_col  = st.selectbox("Billed amount column",  auto_fin if auto_fin else cols, key="billed_col")
    allowed_col = st.selectbox("Allowed amount column", auto_fin if auto_fin else cols, key="allowed_col")
    if st.button("Run", key="btn_alw_bil"):
        tmp = df.copy()
        tmp["_B"] = pd.to_numeric(tmp[billed_col],  errors="coerce")
        tmp["_A"] = pd.to_numeric(tmp[allowed_col], errors="coerce")
        valid = tmp[["_B", "_A"]].notna().all(axis=1)
        viol  = tmp[valid & (tmp["_A"] > tmp["_B"])]
        st.metric("Rows where Allowed > Billed", f"{len(viol):,}")
        if not viol.empty:
            st.dataframe(viol[[billed_col, allowed_col]].head(20), use_container_width=True)
        else:
            st.success("✅ Allowed never exceeds billed.")

    # Zero-dollar lines
    st.markdown("---")
    st.markdown("**Zero-Dollar Line Analysis**")
    zero_cols      = st.multiselect("Financial columns to check", auto_fin if auto_fin else cols, key="zero_cols")
    status_col_fin = st.selectbox("Status column (optional, for breakdown)", ["(none)"] + cols, key="status_col_fin")
    if st.button("Run", key="btn_zero") and zero_cols:
        tmp = df.copy()
        for c in zero_cols:
            tmp[c] = pd.to_numeric(tmp[c], errors="coerce")
        st.session_state["zero_breakdown"] = {}
        for col in zero_cols:
            zero_mask = tmp[col].fillna(0) == 0
            n_zero    = int(zero_mask.sum())
            st.write(f"**{col}**: {n_zero:,} zero/null rows ({n_zero/total_rows*100:.2f}%)")
            if n_zero and status_col_fin != "(none)":
                bk = tmp.loc[zero_mask, status_col_fin].value_counts().reset_index()
                bk.columns = ["Status", "Count"]
                # store zero_mask indices so we can cross-filter by status
                st.session_state["zero_breakdown"][col] = {
                    "summary": bk,
                    "zero_idx": df.index[zero_mask].tolist(),
                    "status_col": status_col_fin,
                }

    if "zero_breakdown" in st.session_state:
        for col, data in st.session_state["zero_breakdown"].items():
            st.markdown(f"**{col}** — click a status to see those records:")
            row = drilldown(data["summary"], f"zero_{col}",
                            f"Click a status row to see zero-value `{col}` records with that status.")
            if row is not None:
                sc   = data["status_col"]
                zero_df = df.loc[data["zero_idx"]]
                res  = zero_df[zero_df[sc].astype(str) == str(row["Status"])].reset_index(drop=True)
                st.markdown(f"#### `{col}` = 0, Status = `{row['Status']}` — {len(res):,} rows")
                st.dataframe(res, use_container_width=True)

    # Status vs paid
    st.markdown("---")
    st.markdown("**Status vs Paid Alignment** — Denied claims should have $0 paid")
    status_col_aln  = st.selectbox("Status column", cols, key="status_aln")
    denied_kw_input = st.text_input("Denied status keywords (comma-separated)", value="denied,deny,D,DEN", key="denied_kw")
    paid_col_aln    = st.selectbox("Paid amount column", auto_fin if auto_fin else cols, key="paid_aln")
    if st.button("Run", key="btn_status_aln"):
        denied_kws = {k.strip().lower() for k in denied_kw_input.split(",") if k.strip()}
        tmp = df.copy()
        tmp["_STATUS"] = tmp[status_col_aln].astype(str).str.strip().str.lower()
        tmp["_PAID"]   = pd.to_numeric(tmp[paid_col_aln], errors="coerce").fillna(0)
        viol = tmp[tmp["_STATUS"].isin(denied_kws) & (tmp["_PAID"].abs() > 0)]
        st.metric("Denied claims with non-zero paid", f"{len(viol):,}")
        if not viol.empty:
            st.dataframe(viol[[status_col_aln, paid_col_aln]].head(20), use_container_width=True)
        else:
            st.success("✅ All denied claims have $0 paid.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 9 — Service Classification
# ════════════════════════════════════════════════════════════════════════════
with tabs[8]:
    st.subheader("Service Classification and Coding")

    st.markdown("**Claim Type Distribution**")
    ct_col = st.selectbox("Claim type column", cols, key="ct_col")
    if st.button("Show distribution", key="btn_ct"):
        dist = df[ct_col].value_counts(dropna=False).reset_index()
        dist.columns = ["Value", "Count"]
        dist["%"] = (dist["Count"] / total_rows * 100).round(2)
        st.session_state["ct_dist"]      = dist
        st.session_state["ct_col_saved"] = ct_col

    if "ct_dist" in st.session_state:
        row = drilldown(st.session_state["ct_dist"], "ct",
                        "Click a row to see all records with that claim type.")
        if row is not None:
            cc   = st.session_state["ct_col_saved"]
            val  = row["Value"]
            mask = df[cc].astype(str) == str(val) if pd.notna(val) else df[cc].isnull()
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{cc}` = `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    st.markdown("---")
    st.markdown("**Procedure Code Type Consistency**")
    proc_col = st.selectbox("Procedure code column", cols, key="proc_col")
    if st.button("Analyze", key="btn_proc"):
        s = df[proc_col].astype(str).str.strip()
        def classify(v):
            if not v or v in ("", "nan"): return "Blank"
            if re.fullmatch(r'\d{5}',      v): return "CPT (5-digit)"
            if re.fullmatch(r'[A-Z]\d{4}', v): return "HCPCS (letter + 4 digits)"
            if re.fullmatch(r'[A-Z0-9]{7}', v): return "ICD-10-PCS (7-char)"
            if re.fullmatch(r'\d{2,4}',    v): return "ICD-9 (2–4 digit)"
            return "Other"
        cat_series = s.apply(classify)
        cats = cat_series.value_counts().reset_index()
        cats.columns = ["Code Type", "Count"]
        cats["%"] = (cats["Count"] / total_rows * 100).round(2)
        st.session_state["proc_cats"]       = cats
        st.session_state["proc_series"]     = cat_series
        st.session_state["proc_col_saved"]  = proc_col

    if "proc_cats" in st.session_state:
        cats       = st.session_state["proc_cats"]
        cat_series = st.session_state["proc_series"]
        saved_col  = st.session_state["proc_col_saved"]

        n_types = int((cats.loc[cats["Code Type"] != "Blank", "Code Type"].nunique()))
        if n_types > 1:
            st.warning(f"⚠️ {n_types} distinct code types detected — possible mixing of ICD and CPT.")
        elif n_types == 1:
            st.success("✅ Procedure codes appear consistent.")

        st.caption("Click a row to see example records of that code type.")
        sel_proc = st.dataframe(
            cats,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="proc_sel_table",
        )
        selected_proc = sel_proc.selection.rows if sel_proc.selection else []
        if selected_proc:
            chosen_type = cats.iloc[selected_proc[0]]["Code Type"]
            mask = cat_series == chosen_type
            example_rows = df[mask.values].reset_index(drop=True)
            st.markdown(f"#### Example rows — `{chosen_type}` ({len(example_rows):,} total)")
            st.dataframe(example_rows, use_container_width=True)

    st.markdown("---")
    st.markdown("**Column Mismatch Check** — Two columns that should have the same value")
    mm_a   = st.selectbox("Column A", cols, key="mm_a")
    mm_b   = st.selectbox("Column B", cols, index=min(1, len(cols)-1), key="mm_b")
    mm_ids = st.multiselect("Identifier columns (for display)", cols, key="mm_ids")
    if st.button("Run", key="btn_mm"):
        tmp = df.copy()
        tmp[mm_a] = tmp[mm_a].astype(str).str.strip()
        tmp[mm_b] = tmp[mm_b].astype(str).str.strip()
        valid = (tmp[mm_a] != "") & tmp[mm_a].notna() & (tmp[mm_b] != "") & tmp[mm_b].notna()
        mis   = valid & (tmp[mm_a] != tmp[mm_b])
        show  = [c for c in (mm_ids + [mm_a, mm_b]) if c in cols]
        result = tmp.loc[mis, show].drop_duplicates()
        st.metric("Unique mismatched rows", f"{len(result):,}")
        if not result.empty:
            st.dataframe(result.head(50), use_container_width=True)
        else:
            st.success("✅ No mismatches found.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 10 — Volume & Distribution
# ════════════════════════════════════════════════════════════════════════════
with tabs[9]:
    st.subheader("Volume & Distribution Checks")

    vol_date_col = st.selectbox("Date column (service date or paid date)", cols, key="vol_date")
    vol_date_fmt = st.text_input("Date format", value="%Y-%m-%d", key="vol_fmt")
    vol_paid_col = st.selectbox("Paid/amount column for monthly totals (optional)", ["(none)"] + cols, key="vol_paid")

    if st.button("Generate charts", key="btn_vol"):
        tmp = df.copy()
        tmp["_DATE"] = pd.to_datetime(tmp[vol_date_col].astype(str).str.strip(), format=vol_date_fmt, errors="coerce")
        tmp = tmp.dropna(subset=["_DATE"])
        tmp["_YM"] = tmp["_DATE"].dt.to_period("M").astype(str)

        monthly = tmp.groupby("_YM").size().reset_index(name="Claim Count").sort_values("_YM")
        st.markdown("**Monthly Claim Volume**")
        st.bar_chart(monthly.set_index("_YM")["Claim Count"])

        mean_v = monthly["Claim Count"].mean()
        std_v  = monthly["Claim Count"].std()
        spikes = monthly[monthly["Claim Count"] > mean_v + 2 * std_v]
        if not spikes.empty:
            st.warning(f"⚠️ Volume spikes detected ({len(spikes)} month(s) > 2 std dev above mean):")
            st.dataframe(spikes, use_container_width=True)

        if vol_paid_col != "(none)":
            tmp["_PAID"] = pd.to_numeric(tmp[vol_paid_col], errors="coerce")
            monthly_paid = tmp.groupby("_YM")["_PAID"].sum().reset_index(name="Total Paid").sort_values("_YM")
            st.markdown("**Monthly Total Paid**")
            st.bar_chart(monthly_paid.set_index("_YM")["Total Paid"])
            mean_p = monthly_paid["Total Paid"].mean()
            std_p  = monthly_paid["Total Paid"].std()
            paid_spikes = monthly_paid[monthly_paid["Total Paid"] > mean_p + 2 * std_p]
            if not paid_spikes.empty:
                st.warning(f"⚠️ Paid amount anomalies ({len(paid_spikes)} month(s)):")
                st.dataframe(paid_spikes, use_container_width=True)

        st.markdown("**Full Monthly Summary**")
        st.dataframe(monthly, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 11 — SSN Validation
# ════════════════════════════════════════════════════════════════════════════
with tabs[10]:
    st.subheader("SSN Validation")
    st.caption("Checks columns containing 'SSN' or 'social' — must be exactly 9 digits.")

    ssn_id_cols = st.multiselect(
        "Unique row identifier columns (for sample output)",
        cols,
        default=[c for c in cols if any(x in c.upper() for x in ["IDNUMBER", "CLAIM"])][:2],
        key="ssn_id",
    )
    ssn_n_samples = int(st.number_input("Sample identifiers per issue type", 1, 20, 6, key="ssn_samp"))

    if st.button("Run", key="btn_ssn"):
        ssn_cols = [c for c in cols if re.search(r"ssn|social", c, re.IGNORECASE)]
        if not ssn_cols:
            st.warning("No SSN/social columns detected.")
        else:
            def _blank(v): return str(v).strip() == "" if not pd.isnull(v) else False
            def _null_s(v): return str(v).strip().lower() == "null" if not pd.isnull(v) else False
            def _valid(v): return bool(re.fullmatch(r"\d{9}", str(v).strip()))
            def _invalid(v):
                return not (pd.isnull(v) or _blank(v) or _null_s(v)) and (
                    bool(re.search(r"[^0-9]", str(v).strip())) or not _valid(v))

            def sample_ids(mask):
                if not ssn_id_cols: return []
                return (df.loc[mask]
                          .apply(lambda r: " | ".join(str(r[c]) for c in ssn_id_cols if c in r.index), axis=1)
                          .dropna().unique()[:ssn_n_samples].tolist())

            results = []
            for col in ssn_cols:
                blank_m = df[col].apply(_blank)
                null_m  = df[col].apply(_null_s)
                nan_m   = df[col].isnull()
                inv_m   = df[col].apply(_invalid)
                val_m   = df[col].apply(_valid)
                results.append({
                    "Column": col, "Total": total_rows,
                    "NaN": int(nan_m.sum()), "Blank": int(blank_m.sum()),
                    '"null" string': int(null_m.sum()),
                    "Invalid Format": int(inv_m.sum()),
                    "Valid (9 digits)": int(val_m.sum()),
                    "Sample IDs — Invalid": str(sample_ids(inv_m)),
                    "Sample IDs — null str": str(sample_ids(null_m)),
                    "Sample IDs — blank": str(sample_ids(blank_m)),
                })
            st.dataframe(pd.DataFrame(results), use_container_width=True)

    # SSN shared across names
    st.markdown("---")
    st.markdown("**SSNs Shared Across Multiple Names**")
    auto_ssn = [c for c in cols if re.search(r"ssn|social", c, re.IGNORECASE)]
    ssn_sh   = st.selectbox("SSN column", auto_ssn if auto_ssn else cols, key="ssn_sh")
    ssn_fn   = st.selectbox("First name column", cols, key="ssn_fn")
    ssn_ln   = st.selectbox("Last name column",  cols, index=min(1, len(cols)-1), key="ssn_ln")
    ssn_excl = st.text_input("Excluded SSN values (comma-separated)", value="000000000,999999999", key="ssn_excl")
    if st.button("Run", key="btn_ssn_sh"):
        excl = {s.strip() for s in ssn_excl.split(",") if s.strip()}
        tmp  = df.copy()
        for c in [ssn_sh, ssn_fn, ssn_ln]:
            tmp[c] = tmp[c].astype(str).str.strip().str.upper()
        if excl:
            tmp = tmp[~tmp[ssn_sh].isin(excl)]
        grouped = tmp.groupby(ssn_sh)[[ssn_fn, ssn_ln]].nunique()
        varied  = grouped[grouped.max(axis=1) > 1].reset_index()
        st.metric("SSNs with multiple name combos", f"{len(varied):,}")
        if not varied.empty:
            sample = varied[ssn_sh].head(10).tolist()
            st.dataframe(
                tmp[tmp[ssn_sh].isin(sample)][[ssn_sh, ssn_fn, ssn_ln]].drop_duplicates().sort_values(ssn_sh),
                use_container_width=True,
            )
        else:
            st.success("✅ No SSNs associated with multiple name combinations.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 12 — NPI Validation
# ════════════════════════════════════════════════════════════════════════════
with tabs[11]:
    st.subheader("NPI Validation")
    st.caption("Checks NPI columns — must be exactly 10 digits, no letters or special characters.")

    if st.button("Run", key="btn_npi"):
        npi_cols = [c for c in cols if "npi" in c.lower()]
        if not npi_cols:
            st.warning("No NPI columns detected.")
        else:
            def cat_npi(val):
                s = str(val).strip()
                if pd.isna(val) or s.lower() in ("", "nan", "none"): return "Blank or Missing"
                if not s.isdigit():
                    return "Contains Letters" if re.search(r"[a-zA-Z]", s) else "Contains Special Characters"
                if len(s) < 10: return "Too Short"
                if len(s) > 10: return "Too Long"
                return "Valid"

            for col in npi_cols:
                st.markdown(f"**{col}**")
                cats = df[col].astype(str).apply(cat_npi)
                summary = cats.value_counts().rename_axis("Category").reset_index(name="Count")
                summary["%"] = (summary["Count"] / total_rows * 100).round(2)
                st.dataframe(summary, use_container_width=True)
                for issue in summary.loc[summary["Category"] != "Valid", "Category"].tolist():
                    ex = df[cats == issue].head(5)
                    if not ex.empty:
                        with st.expander(f"Sample rows — {issue}"):
                            st.dataframe(ex, use_container_width=True)
