import streamlit as st
import pandas as pd
import numpy as np
import re
import io
from datetime import date

st.set_page_config(page_title="Eligibility Testing", layout="wide", page_icon="🧾")
st.title("Eligibility Testing Tool")

# ── DRILLDOWN HELPER ──────────────────────────────────────────────────────────
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
skip_space = c2.checkbox("Skip initial space")
no_quote   = c3.checkbox("Disable quoting")

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
    for _k in [
        "req_results", "dup_counts", "dup_key_cols",
        "dummy_hits", "filler_hits", "pop_results",
        "ev_hits", "pev_hits", "gender_dist",
        "mem_uniq_summary", "mem_uniq_tmp", "mem_uniq_id_cols", "mem_uniq_bio_cols",
        "default_ssn_hits", "dep_sub_results",
        "elevated_dep_hits", "plan_dist_results",
        "cov_date_results", "rehire_hits", "hire_birth_hits",
        "hire_founding_hits", "term_placeholder_hits",
        "no_cov_hits", "active_death_hits",
        "sub_dep_attr_hits", "fin_neg_hits",
        "dv_ord_results", "dv_ord_date_cols",
        "vol_monthly", "vol_ratio",
    ]:
        st.session_state.pop(_k, None)
    st.session_state["_loaded_file_id"] = _file_id


@st.cache_data
def load_file(data, sep, skip, nq):
    kw = {"dtype": str, "keep_default_na": False, "na_values": [],
          "skipinitialspace": skip, "sep": sep}
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

cols       = df.columns.tolist()
total_rows = len(df)
st.divider()

# ── TABS ──────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "🔍 Data Explorer",
    "🗂 File Structure",
    "👤 Member Identification",
    "📋 Plan & Benefit",
    "✅ Field Accuracy",
    "📅 Coverage Status & Dates",
    "📈 Volume & Distribution",
    "🔐 SSN Validation",
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
            uniq_stats.append({
                "Column": col, "Unique Values": n_uniq,
                "% Unique": round(pct, 2),
                "All Unique?": "✅ YES" if n_uniq == total_rows else "",
            })
        uniq_df = pd.DataFrame(uniq_stats).sort_values("% Unique", ascending=False)
        st.dataframe(uniq_df, use_container_width=True, height=400)

        perfect = [r["Column"] for _, r in uniq_df.iterrows() if r["All Unique?"] == "✅ YES"]
        near    = [r["Column"] for _, r in uniq_df.iterrows()
                   if r["% Unique"] >= 90 and r["All Unique?"] != "✅ YES"]

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
            uvals  = df[col].dropna().unique().tolist()
            counts = df[col].value_counts(dropna=False).reset_index()
            counts.columns = ["Value", "Count"]
            counts["%"] = (counts["Count"] / total_rows * 100).round(2)
            with st.expander(f"**{col}** — {len(uvals):,} unique values", expanded=len(uv_cols) == 1):
                st.dataframe(counts, use_container_width=True, height=min(400, 38 + len(counts) * 35))


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — File Structure & Schema
# ════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("File Structure & Schema")

    # Filename checks
    fname    = uploaded.name
    has_year = bool(re.search(r'\b(19|20)\d{2}\b', fname))
    st.write(f"**Filename:** `{fname}`")
    st.write(f"{'✅' if has_year else '❌'} 4-digit year in filename")
    st.write(f"**{len(cols)} columns detected:** `{'`, `'.join(cols[:20])}{'…' if len(cols) > 20 else ''}`")

    # ── Dummy / test value scan ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Dummy / Test Value Scan**")
    dummy_input = st.text_input(
        "Values to scan for (comma-separated, case-insensitive word match)",
        value="test,9999,123456,dummy,fake,sample",
        key="dummy_input",
    )
    if st.button("Scan", key="btn_dummy"):
        dvals = [v.strip() for v in dummy_input.split(",") if v.strip()]
        hits  = []
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
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{row['Column']}` containing `{row['Dummy Value']}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # ── Company / client code ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Company / Client Code in Data**")
    co_col = st.selectbox("Column to inspect for company identifier", cols, key="co_col")
    if st.button("Show unique values", key="btn_co"):
        uvals = sorted(df[co_col].dropna().astype(str).unique().tolist())
        st.write(f"**{len(uvals)} unique value(s)** in `{co_col}`:")
        st.write(uvals[:50])

    # ── Reporting period field ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Reporting Period / Time Period Field**")
    st.caption("Identify which field(s) define the reporting period covered by this file.")
    rp_col = st.selectbox("Column representing the reporting period", cols, key="rp_col")
    if st.button("Show distribution", key="btn_rp"):
        dist = df[rp_col].value_counts(dropna=False).reset_index()
        dist.columns = ["Value", "Count"]
        dist["%"] = (dist["Count"] / total_rows * 100).round(2)
        st.dataframe(dist, use_container_width=True)

    # ── Duplicate records ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Duplicate Records**")
    fs_dup_cols = st.multiselect("Columns defining a unique record", cols, key="fs_dup_cols")
    if st.button("Check duplicates", key="btn_fs_dup") and fs_dup_cols:
        dup_mask = df.duplicated(subset=fs_dup_cols, keep=False)
        n_dup    = int(dup_mask.sum())
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
        else:
            st.success("No duplicate records found.")
            st.session_state.pop("dup_counts", None)

    if "dup_counts" in st.session_state:
        counts   = st.session_state["dup_counts"]
        key_cols = st.session_state["dup_key_cols"]
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
            row = counts.iloc[selected_rows[0]]
            mask = pd.Series([True] * len(df), index=df.index)
            for col in key_cols:
                mask &= df[col].astype(str) == str(row[col])
            matching = df[mask].reset_index(drop=True)
            st.markdown(f"#### All {len(matching)} duplicate rows for selected key")
            varying  = [c for c in df.columns if c not in key_cols and matching[c].nunique() > 1]
            constant = [c for c in df.columns if c not in key_cols and matching[c].nunique() <= 1]
            if varying:
                st.success(
                    f"**Columns that differ across duplicates** (good candidates to add to your key): "
                    f"`{'`, `'.join(varying)}`"
                )
            if constant:
                st.info(
                    f"**Columns identical across all duplicates** (won't help distinguish): "
                    f"`{'`, `'.join(constant)}`"
                )
            st.dataframe(matching, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Member Identification & Eligibility Mapping
# ════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Member Identification & Eligibility Mapping")

    # ── Member ID → one member only ─────────────────────────────────────────
    st.markdown("**Member ID → One Member Only**")
    st.caption("Each member ID should link to exactly one unique identity (name/DOB combination).")
    mem_id_cols  = st.multiselect("Member ID column(s)", cols, key="mem_id")
    mem_bio_cols = st.multiselect("Member identity columns (Name, DOB, SSN…)", cols, key="mem_bio")
    if st.button("Check", key="btn_mem_uniq") and mem_id_cols and mem_bio_cols:
        tmp = df.copy()
        for c in mem_id_cols + mem_bio_cols:
            tmp[c] = tmp[c].astype(str).str.strip().str.upper()
        tmp["_ID"]   = list(zip(*(tmp[c] for c in mem_id_cols)))
        tmp["_DEMO"] = list(zip(*(tmp[c] for c in mem_bio_cols)))
        check = tmp.groupby("_ID")["_DEMO"].nunique().reset_index(name="distinct_identities")
        bad   = check[check["distinct_identities"] > 1]
        st.metric("ID combos linked to multiple identities", f"{len(bad):,}")
        if not bad.empty:
            # Rebuild a display summary: one row per bad ID combo with its identity count
            # Store the raw df with _ID column so we can drill into any row
            summary_rows = []
            for id_val in bad["_ID"].tolist():
                n_ids = int(bad.loc[bad["_ID"] == id_val, "distinct_identities"].iloc[0])
                label = " | ".join(str(v) for v in id_val) if isinstance(id_val, tuple) else str(id_val)
                summary_rows.append({"ID Value": label, "Distinct Identities": n_ids, "_ID": id_val})
            summary_df = pd.DataFrame(summary_rows)
            st.session_state["mem_uniq_summary"]  = summary_df
            st.session_state["mem_uniq_tmp"]      = tmp
            st.session_state["mem_uniq_id_cols"]  = mem_id_cols
            st.session_state["mem_uniq_bio_cols"] = mem_bio_cols
        else:
            st.success("✅ All member IDs map to exactly one member.")
            st.session_state.pop("mem_uniq_summary", None)

    if "mem_uniq_summary" in st.session_state:
        display_summary = st.session_state["mem_uniq_summary"][["ID Value", "Distinct Identities"]]
        row = drilldown(display_summary, "mem_uniq",
                        "Click a row to see all records sharing that ID with conflicting identities.")
        if row is not None:
            chosen_id  = st.session_state["mem_uniq_summary"].iloc[
                display_summary.index[display_summary["ID Value"] == row["ID Value"]][0]
            ]["_ID"]
            tmp2       = st.session_state["mem_uniq_tmp"]
            id_cols    = st.session_state["mem_uniq_id_cols"]
            bio_cols   = st.session_state["mem_uniq_bio_cols"]
            mask       = tmp2["_ID"] == chosen_id
            res        = df[mask.values].reset_index(drop=True)
            st.markdown(f"#### ID `{row['ID Value']}` — {len(res):,} rows ({row['Distinct Identities']} distinct identities)")
            st.dataframe(res, use_container_width=True)

    # ── Dependent → Subscriber tie ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Dependent → Subscriber Tie**")
    st.caption(
        "Verify dependents can be linked back to a subscriber (employee) record using "
        "family/cardholder ID or dependent code."
    )
    dep_fam_col = st.selectbox("Family / Cardholder ID column", cols, key="dep_fam_col")
    dep_rel_col = st.selectbox("Relationship / role column", cols, key="dep_rel_col")
    dep_emp_kw  = st.text_input(
        "Employee / subscriber code values (comma-separated)",
        value="EE,employee,self,00,E,18,subscriber", key="dep_emp_kw",
    )
    if st.button("Check ties", key="btn_dep_tie"):
        emp_kws = {k.strip().lower() for k in dep_emp_kw.split(",") if k.strip()}
        tmp     = df.copy()
        tmp["_REL"] = tmp[dep_rel_col].astype(str).str.strip().str.lower()
        tmp["_FAM"] = tmp[dep_fam_col].astype(str).str.strip()
        is_emp  = tmp["_REL"].isin(emp_kws)
        is_dep  = ~is_emp
        sub_fam_ids = set(tmp.loc[is_emp, "_FAM"])
        dep_rows    = tmp[is_dep].copy()
        dep_rows["_HAS_SUB"] = dep_rows["_FAM"].isin(sub_fam_ids)
        orphan = dep_rows[~dep_rows["_HAS_SUB"]]
        ma, mb = st.columns(2)
        ma.metric("Dependent records", f"{int(is_dep.sum()):,}")
        mb.metric("Dependents with no matching subscriber", f"{len(orphan):,}")
        if not orphan.empty:
            st.warning(f"⚠️ {len(orphan):,} dependent records cannot be tied to a subscriber.")
            with st.expander("Show orphaned dependents"):
                st.dataframe(orphan.drop(columns=["_REL","_FAM","_HAS_SUB"]).head(50), use_container_width=True)
        else:
            st.success("✅ All dependents can be tied to a subscriber record.")

    # ── Default / placeholder SSN / ID detection ─────────────────────────────
    st.markdown("---")
    st.markdown("**Default / Placeholder SSNs and Member IDs**")
    st.caption(
        "Identifies known default SSNs (000000000, 990000001) and placeholder name patterns "
        "such as 'GIRL', 'BOY', 'BABY', 'NEWBORN'. These are sometimes intentional for "
        "newborns but should be validated."
    )
    default_ssn_col   = st.selectbox("SSN column to check", cols, key="def_ssn_col")
    default_name_cols = st.multiselect("Name column(s) to check for placeholder values", cols, key="def_name_cols")
    default_ssn_vals  = st.text_input(
        "Default SSN values (comma-separated, exact match)",
        value="000000000,990000001,999999999,123456789,000000001",
        key="def_ssn_vals",
    )
    default_name_kws  = st.text_input(
        "Placeholder name keywords (comma-separated, case-insensitive)",
        value="GIRL,BOY,BABY,NEWBORN,INFANT,TEST,UNKNOWN,DEFAULT",
        key="def_name_kws",
    )
    if st.button("Run", key="btn_default_ssn"):
        ssn_vals_set = {v.strip() for v in default_ssn_vals.split(",") if v.strip()}
        name_kws_set = [v.strip() for v in default_name_kws.split(",") if v.strip()]
        hits = []

        s_ssn = df[default_ssn_col].astype(str).str.strip()
        for sv in ssn_vals_set:
            cnt = int((s_ssn == sv).sum())
            if cnt:
                hits.append({"Source": f"SSN — `{default_ssn_col}`", "Pattern": sv, "Count": cnt,
                             "%": round(cnt / total_rows * 100, 2)})

        for nc in default_name_cols:
            s_name = df[nc].astype(str).str.strip()
            for kw in name_kws_set:
                cnt = int(s_name.str.contains(rf'\b{re.escape(kw)}\b', case=False, na=False).sum())
                if cnt:
                    hits.append({"Source": f"Name — `{nc}`", "Pattern": kw, "Count": cnt,
                                 "%": round(cnt / total_rows * 100, 2)})

        if hits:
            st.warning(f"⚠️ Default/placeholder patterns found.")
            st.session_state["default_ssn_hits"] = pd.DataFrame(hits)
        else:
            st.success("✅ No default SSNs or placeholder names detected.")
            st.session_state.pop("default_ssn_hits", None)

    if "default_ssn_hits" in st.session_state:
        row = drilldown(st.session_state["default_ssn_hits"], "def_ssn",
                        "Click a row to see all records matching that pattern.")
        if row is not None:
            src     = row["Source"]
            pattern = row["Pattern"]
            if "SSN" in src:
                mask = df[default_ssn_col].astype(str).str.strip() == pattern
            else:
                # Extract column name from label like "Name — `col`"
                nc_match = re.search(r'`(.+?)`', src)
                nc       = nc_match.group(1) if nc_match else cols[0]
                mask     = df[nc].astype(str).str.contains(rf'\b{re.escape(pattern)}\b', case=False, na=False)
            res = df[mask].reset_index(drop=True)
            st.markdown(f"#### {src} = `{pattern}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # ── Subscriber ID type clarification ─────────────────────────────────────
    st.markdown("---")
    st.markdown("**Subscriber ID Type Clarification**")
    st.caption(
        "Determine whether the Subscriber ID field represents SSN, contract number, or an alternate ID — "
        "and whether it aligns with member ID or cardholder ID."
    )
    sub_id_col = st.selectbox("Subscriber ID column", cols, key="sub_id_col")
    mbr_id_col = st.selectbox("Member ID / Cardholder ID column to compare", cols, key="sub_vs_mbr_col")
    if st.button("Compare", key="btn_sub_id"):
        tmp = df.copy()
        tmp["_SUB"] = tmp[sub_id_col].astype(str).str.strip()
        tmp["_MBR"] = tmp[mbr_id_col].astype(str).str.strip()
        # Check if values look like SSNs (9 digits)
        ssn_like = int(tmp["_SUB"].str.fullmatch(r'\d{9}').fillna(False).sum())
        match_n  = int((tmp["_SUB"] == tmp["_MBR"]).sum())
        ma, mb, mc = st.columns(3)
        ma.metric("Total rows", f"{total_rows:,}")
        mb.metric(f"Subscriber ID matches {mbr_id_col}", f"{match_n:,}",
                  delta=f"{match_n/total_rows*100:.1f}%")
        mc.metric("Subscriber ID looks like 9-digit SSN", f"{ssn_like:,}",
                  delta=f"{ssn_like/total_rows*100:.1f}%")
        if match_n == total_rows:
            st.success(f"✅ Subscriber ID is identical to {mbr_id_col} on every row.")
        elif match_n == 0:
            st.warning(f"⚠️ Subscriber ID never matches {mbr_id_col} — they represent different identifiers.")
        else:
            st.info(f"Subscriber ID matches {mbr_id_col} on {match_n:,} of {total_rows:,} rows ({match_n/total_rows*100:.1f}%).")
        with st.expander("Sample subscriber ID values"):
            st.write(sorted(tmp["_SUB"].dropna().unique().tolist()[:30]))

    # ── Elevated dependents appearing as employees ────────────────────────────
    st.markdown("---")
    st.markdown("**Elevated Dependents / Spouses Appearing as Employees**")
    st.caption(
        "A dependent or spouse who also appears as an employee-coded record under a different "
        "family/cardholder ID should be flagged for investigation."
    )
    elev_id_col  = st.selectbox("Member unique ID column (appears on both records)", cols, key="elev_id_col")
    elev_fam_col = st.selectbox("Family / Cardholder ID column", cols, key="elev_fam_col")
    elev_rel_col = st.selectbox("Relationship column", cols, key="elev_rel_col")
    elev_emp_kw  = st.text_input("Employee codes (comma-separated)", value="EE,employee,self,00,E,18", key="elev_emp_kw")
    elev_dep_kw  = st.text_input("Dependent/spouse codes (comma-separated)", value="spouse,child,dependent,01,02,S,D,C", key="elev_dep_kw")
    if st.button("Run", key="btn_elevated"):
        emp_kws = {k.strip().lower() for k in elev_emp_kw.split(",") if k.strip()}
        dep_kws = {k.strip().lower() for k in elev_dep_kw.split(",") if k.strip()}
        tmp = df.copy()
        tmp["_REL"] = tmp[elev_rel_col].astype(str).str.strip().str.lower()
        tmp["_MID"] = tmp[elev_id_col].astype(str).str.strip()
        tmp["_FAM"] = tmp[elev_fam_col].astype(str).str.strip()
        is_emp = tmp["_REL"].isin(emp_kws)
        is_dep = tmp["_REL"].isin(dep_kws)
        emp_ids = set(tmp.loc[is_emp, "_MID"])
        dep_ids = set(tmp.loc[is_dep, "_MID"])
        elevated = emp_ids & dep_ids  # Same member ID appears as both
        st.metric("Members appearing as both employee and dependent/spouse", f"{len(elevated):,}")
        if elevated:
            st.warning(f"⚠️ {len(elevated):,} member IDs appear as both an employee and a dependent/spouse.")
            st.session_state["elevated_dep_hits"] = df[tmp["_MID"].isin(elevated)].reset_index(drop=True)
        else:
            st.success("✅ No members appear as both employee and dependent/spouse.")
            st.session_state.pop("elevated_dep_hits", None)

    if "elevated_dep_hits" in st.session_state:
        with st.expander("Show elevated member records"):
            st.dataframe(st.session_state["elevated_dep_hits"], use_container_width=True)

    # ── Dependent age ≥26 ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Dependent Age Check — Non-Spouse Dependents ≥ 26**")
    st.caption("Non-spouse dependents aged 26+ should be less than 2% of all dependents.")
    dob_col_mi   = st.selectbox("Date of Birth column", cols, key="mi_dob")
    rel_col_mi   = st.selectbox("Relationship column", cols, key="mi_rel")
    dob_fmt_mi   = st.text_input("DOB format", value="%Y-%m-%d", key="mi_dob_fmt")
    spouse_kw_mi = st.text_input("Spouse codes (comma-separated)", value="spouse,01,S,SP", key="mi_spouse")
    emp_kw_mi    = st.text_input("Employee/self codes (comma-separated)", value="employee,self,EE,00,E,18", key="mi_emp")
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
            ma, mb, mc   = st.columns(3)
            ma.metric("Total Dependents", f"{total_dep:,}")
            mb.metric("Non-Spouse ≥ 26", f"{n_prob:,}")
            mc.metric("% of Dependents", f"{pct:.2f}%",
                      delta="⚠️ > 2%" if pct > 2 else "✅ OK", delta_color="inverse")
            if n_prob:
                st.dataframe(tmp[problem_mask][[dob_col_mi, rel_col_mi, "_AGE"]].head(50),
                             use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Demographic alignment ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Demographic Alignment**")
    st.caption(
        "Verify member demographics make sense relative to their role and status. "
        "Examples: toddlers are not employees; 95-year-olds were not recently hired."
    )
    dob_col_da = st.selectbox("Date of Birth column", cols, key="da_dob")
    rel_col_da = st.selectbox("Relationship / subscriber column", cols, key="da_rel")
    dob_fmt_da = st.text_input("Date format for DOB", value="%Y-%m-%d", key="da_fmt")
    emp_kw_da  = st.text_input("Employee codes (comma-separated)", value="EE,employee,self,00,E,18", key="da_emp_kw")

    st.markdown("**Minors coded as employees**")
    min_work_age = st.number_input("Minimum employee age", min_value=14, max_value=25, value=16, key="da_min_work")
    if st.button("Run", key="btn_da_minor_emp"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE"] = ((pd.Timestamp(date.today()) - tmp["_DOB"]).dt.days / 365.25)
            emp_kws     = {k.strip().lower() for k in emp_kw_da.split(",") if k.strip()}
            tmp["_REL"] = tmp[rel_col_da].astype(str).str.strip().str.lower()
            mask        = tmp["_REL"].isin(emp_kws) & (tmp["_AGE"] < min_work_age) & tmp["_AGE"].notna()
            st.metric(f"Members < {min_work_age} coded as employee", f"{int(mask.sum()):,}")
            if mask.any():
                st.dataframe(tmp[mask][[dob_col_da, rel_col_da, "_AGE"]].rename(columns={"_AGE": "Age (yrs)"}).round(1).head(30),
                             use_container_width=True)
            else:
                st.success(f"✅ No members under {min_work_age} coded as employees.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("**Unusually old active employees**")
    max_emp_age = st.number_input("Flag employees older than (years)", min_value=70, max_value=110, value=85, key="da_max_emp")
    if st.button("Run", key="btn_da_old_emp"):
        try:
            tmp = df.copy()
            tmp["_DOB"] = pd.to_datetime(tmp[dob_col_da].astype(str).str.strip(), format=dob_fmt_da, errors="coerce")
            tmp["_AGE"] = ((pd.Timestamp(date.today()) - tmp["_DOB"]).dt.days / 365.25)
            emp_kws     = {k.strip().lower() for k in emp_kw_da.split(",") if k.strip()}
            tmp["_REL"] = tmp[rel_col_da].astype(str).str.strip().str.lower()
            mask        = tmp["_REL"].isin(emp_kws) & (tmp["_AGE"] > max_emp_age) & tmp["_AGE"].notna()
            st.metric(f"Employees older than {max_emp_age}", f"{int(mask.sum()):,}")
            if mask.any():
                st.dataframe(tmp[mask][[dob_col_da, rel_col_da, "_AGE"]].rename(columns={"_AGE": "Age (yrs)"}).round(1).head(30),
                             use_container_width=True)
            else:
                st.success(f"✅ No employees found over age {max_emp_age}.")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Gender distribution ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Gender / Sex at Birth Distribution**")
    gender_col = st.selectbox("Gender column", cols, key="gender_col")
    if st.button("Show", key="btn_gender"):
        dist = df[gender_col].value_counts(dropna=False).reset_index()
        dist.columns = ["Value", "Count"]
        dist["%"] = (dist["Count"] / total_rows * 100).round(2)
        st.session_state["gender_dist"]      = dist
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

    # ── Global data check ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Global Data Check** — Confirm no non-US records")
    addr_col = st.selectbox("Country / State / Address column", cols, key="addr_col")
    if st.button("Show unique values", key="btn_global"):
        uv = sorted(df[addr_col].dropna().astype(str).unique().tolist())
        st.write(f"**{len(uv)} unique values** in `{addr_col}`:")
        st.write(uv[:100])


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Plan & Benefit Information
# ════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Plan & Benefit Information")

    # ── Plan granularity ────────────────────────────────────────────────────
    st.markdown("**Plan Identifier Granularity**")
    st.caption(
        "Confirm that plan identifiers provide the most granular level of plan information "
        "(e.g., PPO High Deductible vs. just PPO) and indicate which populations are enrolled."
    )
    plan_cols = st.multiselect("Plan-related columns to review", cols, key="plan_cols")
    if st.button("Show plan distributions", key="btn_plan") and plan_cols:
        for col in plan_cols:
            st.markdown(f"**{col}** — {df[col].nunique()} unique values")
            dist = df[col].value_counts(dropna=False).reset_index()
            dist.columns = ["Value", "Count"]
            dist["%"] = (dist["Count"] / total_rows * 100).round(2)
            row = drilldown(dist, f"plan_{col}",
                            f"Click a value to see all records for that {col}.")
            if row is not None:
                val  = row["Value"]
                mask = df[col].astype(str) == str(val) if pd.notna(val) else df[col].isnull()
                res  = df[mask].reset_index(drop=True)
                st.markdown(f"#### `{col}` = `{val}` — {len(res):,} rows")
                st.dataframe(res, use_container_width=True)
            st.markdown("---")

    # ── Population delineation ───────────────────────────────────────────────
    st.markdown("**Population Delineation**")
    st.caption(
        "Verify that different populations (COBRA, retirees, VIPs, terminated members, etc.) "
        "are clearly distinguished via flags, subgroups, or plan names."
    )
    pop_col = st.selectbox("Column containing population / status flag", cols, key="pop_col")
    if st.button("Show population breakdown", key="btn_pop_breakdown"):
        dist = df[pop_col].value_counts(dropna=False).reset_index()
        dist.columns = ["Population / Status", "Count"]
        dist["%"] = (dist["Count"] / total_rows * 100).round(2)
        row = drilldown(dist, "pop_breakdown", "Click a population to see its records.")
        if row is not None:
            val  = row["Population / Status"]
            mask = df[pop_col].astype(str) == str(val) if pd.notna(val) else df[pop_col].isnull()
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### Population `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # ── Plan crosswalk ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Plan Crosswalk — Allowed Values Check**")
    st.caption("Cross-reference all plan field values against the account structure / specification.")
    pev_col  = st.selectbox("Column to validate", cols, key="pev_col")
    pev_vals = st.text_area("Allowed plan code values (one per line)", key="pev_vals", height=120)
    if st.button("Run", key="btn_pev") and pev_vals.strip():
        allowed  = {v.strip() for v in pev_vals.splitlines() if v.strip()}
        bad_mask = ~df[pev_col].astype(str).str.strip().isin(allowed) & df[pev_col].notna()
        bad_vals = df.loc[bad_mask, pev_col].value_counts().reset_index(name="Count")
        bad_vals.columns = [pev_col, "Count"]
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
# TAB 4 — Field Accuracy & Completion
# ════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Field Accuracy & Completion")

    # ── Full population overview ─────────────────────────────────────────────
    st.markdown("**Full Field Population Overview**")
    if st.button("Run", key="btn_pop"):
        rows_out = []
        for col in cols:
            s       = df[col]
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
                        "Click a row to see records where that field is empty.")
        if row is not None:
            col_name   = row["Column"]
            empty_mask = df[col_name].isnull() | (df[col_name].astype(str).str.strip() == "")
            res        = df[empty_mask].reset_index(drop=True)
            if not res.empty:
                st.markdown(f"#### `{col_name}` — {len(res):,} empty rows")
                st.dataframe(res, use_container_width=True)
            else:
                st.success(f"✅ `{col_name}` has no empty rows.")

    # ── Required fields ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Required Fields — Must Be 100% Populated**")
    st.caption(
        "Per the Eligibility Testing Plan, the following fields must be populated 100% of the time: "
        "Most granular plan code, First Name, Last Name, DOB, SSN, Relationship, Member Unique ID, "
        "Cardholder ID, Coverage Start Date, Enrollment Tier, Dependent Number, Employee ID."
    )
    req_cols = st.multiselect("Select required fields to check", cols, key="req_cols")
    if st.button("Check", key="btn_req") and req_cols:
        req_rows = []
        for col in req_cols:
            s       = df[col]
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
                st.success(f"✅ No empty rows for `{chosen_col}`.")

    # ── Default / filler value detection ────────────────────────────────────
    st.markdown("---")
    st.markdown("**Default / Filler Value Detection**")
    filler_input = st.text_input(
        "Filler values to scan (comma-separated, exact match)",
        value="999999999,1753-01-01,0000000000,000000000,99999,UNKNOWN,N/A,NULL,NONE,DEFAULT,0",
        key="filler_input",
    )
    if st.button("Scan", key="btn_filler"):
        fvals = [v.strip() for v in filler_input.split(",") if v.strip()]
        hits  = []
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

    # ── Null pattern analysis ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Null Pattern Analysis**")
    st.caption(
        "Track frequency and patterns of nulls to determine if they're systemic "
        "(e.g., for new hires or dependents) or anomalies."
    )
    null_col     = st.selectbox("Column to analyze nulls for", cols, key="null_col")
    null_seg_col = st.selectbox("Segment / group column to cross-tab by (e.g., relationship, status)", cols, key="null_seg_col")
    if st.button("Analyze", key="btn_null_pattern"):
        tmp  = df.copy()
        tmp["_EMPTY"] = tmp[null_col].isnull() | (tmp[null_col].astype(str).str.strip() == "")
        seg_stats = (
            tmp.groupby(null_seg_col)
            .agg(Total=("_EMPTY", "count"), Null_Count=("_EMPTY", "sum"))
            .reset_index()
        )
        seg_stats["Null %"] = (seg_stats["Null_Count"] / seg_stats["Total"] * 100).round(2)
        seg_stats = seg_stats.sort_values("Null %", ascending=False)
        row = drilldown(seg_stats, "null_pattern",
                        f"Click a segment to see {null_col} null records in that group.")
        if row is not None:
            seg_val = row[null_seg_col]
            mask    = (tmp[null_seg_col].astype(str) == str(seg_val)) & tmp["_EMPTY"]
            res     = df[mask.values].reset_index(drop=True)
            st.markdown(f"#### `{null_seg_col}` = `{seg_val}` — null `{null_col}` rows: {len(res):,}")
            st.dataframe(res, use_container_width=True)

    # ── Allowed values check ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Allowed Values Check** — Enumerated field validation")
    st.caption("Cross-reference fields with enumerated values against provided data dictionaries.")
    ev_col  = st.selectbox("Column to validate", cols, key="ev_col")
    ev_vals = st.text_area("Allowed values (one per line)", key="ev_vals", height=100)
    if st.button("Run", key="btn_ev") and ev_vals.strip():
        allowed    = {v.strip() for v in ev_vals.splitlines() if v.strip()}
        actual     = set(df[ev_col].dropna().astype(str).str.strip().unique())
        unexpected = actual - allowed
        st.metric("Unexpected values", len(unexpected))
        if unexpected:
            bad_mask = df[ev_col].astype(str).str.strip().isin(unexpected)
            ev_df    = df.loc[bad_mask, [ev_col]].value_counts().reset_index(name="Count")
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

    # ── Subscriber vs dependent attribute uniqueness ──────────────────────────
    st.markdown("---")
    st.markdown("**Subscriber vs. Dependent Attribute Uniqueness**")
    st.caption(
        "Attributes that should be unique at a member level (address, phone, email) "
        "should not be identical across subscriber and dependent records — that could indicate "
        "data was hardcoded from one field to another."
    )
    attr_col     = st.selectbox("Attribute column to check (e.g., address, phone, email)", cols, key="attr_col")
    attr_fam_col = st.selectbox("Family / Cardholder ID column (to group families)", cols, key="attr_fam_col")
    if st.button("Run", key="btn_attr_uniq"):
        tmp = df.copy()
        tmp["_ATTR"] = tmp[attr_col].astype(str).str.strip()
        tmp["_FAM"]  = tmp[attr_fam_col].astype(str).str.strip()
        # For families with > 1 member, check if every member has the same attribute value
        fam_uniq = tmp.groupby("_FAM")["_ATTR"].nunique().reset_index(name="Unique_Values")
        fam_uniq["Member_Count"] = tmp.groupby("_FAM")["_ATTR"].count().values
        identical_fams = fam_uniq[(fam_uniq["Unique_Values"] == 1) & (fam_uniq["Member_Count"] > 1)]
        total_fams     = len(fam_uniq[fam_uniq["Member_Count"] > 1])
        pct = len(identical_fams) / total_fams * 100 if total_fams else 0
        ma, mb = st.columns(2)
        ma.metric("Multi-member families where all share same attribute", f"{len(identical_fams):,}")
        mb.metric("% of multi-member families", f"{pct:.1f}%",
                  delta="⚠️ High — possible hardcoding" if pct > 50 else "✅ OK", delta_color="inverse")
        if not identical_fams.empty and pct > 10:
            st.warning(
                f"⚠️ {pct:.1f}% of multi-member families have identical `{attr_col}` across all members. "
                "This may indicate the field was copied from subscriber to dependents."
            )
            with st.expander("Sample families with identical attributes"):
                samp_fams = identical_fams["_FAM"].head(5).tolist()
                samp_rows = df[tmp["_FAM"].isin(samp_fams)].reset_index(drop=True)
                st.dataframe(samp_rows, use_container_width=True)

    # ── Financial fields ≥ $0 ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Financial Fields ≥ $0**")
    st.caption("Salary, bonus, premiums, and other financial fields in eligibility data should not be negative.")
    fin_cols = st.multiselect("Financial columns to check", cols, key="fin_cols_elig")
    if st.button("Run", key="btn_fin_elig") and fin_cols:
        results = []
        for col in fin_cols:
            s       = pd.to_numeric(df[col], errors="coerce")
            neg_n   = int((s.round(2) < 0).sum())
            results.append({"Column": col, "Negative Rows": neg_n,
                            "Status": "✅ OK" if neg_n == 0 else f"❌ {neg_n:,} negative"})
        fin_df = pd.DataFrame(results)
        st.session_state["fin_neg_hits"] = fin_df

    if "fin_neg_hits" in st.session_state:
        row = drilldown(st.session_state["fin_neg_hits"], "fin_neg",
                        "Click a row to see records with negative values.")
        if row is not None and row["Negative Rows"] > 0:
            col_name = row["Column"]
            s        = pd.to_numeric(df[col_name], errors="coerce")
            mask     = s.round(2) < 0
            res      = df[mask].reset_index(drop=True)
            st.markdown(f"#### `{col_name}` negative rows — {len(res):,}")
            st.dataframe(res, use_container_width=True)

    # ── Low-variation / suspiciously constant fields ─────────────────────────
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

    # ── Date format consistency ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Date Field Format Consistency**")
    st.caption("Ensure all date fields are in consistent formats and contain valid values.")
    auto_date_cols = [c for c in cols if any(x in c.lower() for x in ["date", "dob", "doh", "dot"])]
    date_cols_tab  = st.multiselect("Date columns to analyze", cols, default=auto_date_cols, key="dv_cols")
    date_fmt_tab   = st.text_input("Expected date format", value="%Y-%m-%d", key="dv_fmt",
                                   help="e.g. %Y-%m-%d | %m/%d/%Y | %Y%m%d | %m%d%Y")
    sys_defaults   = st.text_input(
        "System-default sentinel dates to flag (comma-separated)",
        value="1753-01-01,9999-12-31,1900-01-01,0001-01-01,2135-12-31,12/31/2135",
        key="dv_defaults",
    )
    if st.button("Run date analysis", key="btn_dv") and date_cols_tab:
        sentinel_vals = {v.strip() for v in sys_defaults.split(",") if v.strip()}
        today = pd.Timestamp(date.today())
        for col in date_cols_tab:
            st.markdown(f"**{col}**")
            raw_s     = df[col].astype(str).str.strip()
            parsed    = pd.to_datetime(raw_s, format=date_fmt_tab, errors="coerce")
            blank_n   = int((raw_s == "").sum()) + int(df[col].isnull().sum())
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
                    st.dataframe(df[parsed > today][[col]].head(20), use_container_width=True)
            if default_n:
                with st.expander(f"Sentinel date rows — {col}"):
                    st.dataframe(df[raw_s.isin(sentinel_vals)][[col]].head(20), use_container_width=True)

    # ── Date order check ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Date Order Check** — Flag rows where an earlier date comes after a later date")
    n_ord = int(st.number_input("Number of comparisons", 0, 8, 2, key="dv_n_ord"))
    order_comps = []
    if date_cols_tab:
        for i in range(n_ord):
            ca, cb = st.columns(2)
            a = ca.selectbox(f"Earlier date [{i+1}]", date_cols_tab, key=f"dv_oa_{i}")
            b = cb.selectbox(f"Later date [{i+1}]", date_cols_tab,
                             index=min(1, len(date_cols_tab)-1), key=f"dv_ob_{i}")
            order_comps.append((a, b))
    if st.button("Run order check", key="btn_dv_ord") and date_cols_tab and order_comps:
        tmp = df.copy()
        for col in date_cols_tab:
            tmp[col] = pd.to_datetime(tmp[col].astype(str).str.strip(), format=date_fmt_tab, errors="coerce")
        comp_results = []
        for a, b in order_comps:
            if a != b:
                issue = (tmp[a] > tmp[b]).fillna(False)
                comp_results.append({
                    "Earlier (A)": a, "Later (B)": b,
                    "Label": f"{a} > {b}",
                    "Rows": int(issue.sum()),
                    "_mask": issue.values,
                })
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
                res    = df[chosen["_mask"]].reset_index(drop=True)
                disp_cols = [c for c in st.session_state["dv_ord_date_cols"] if c in res.columns]
                st.markdown(f"#### `{chosen['Label']}` — {len(res):,} rows")
                st.dataframe(res[disp_cols + [c for c in res.columns if c not in disp_cols]],
                             use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Coverage Status & Dates
# ════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Coverage Status & Dates")
    st.caption("Validate logic conflicts, anomalies, and consistency in member coverage and employment dates.")

    # Shared column selectors for this tab
    st.markdown("#### Column Configuration")
    cc1, cc2 = st.columns(2)
    status_col   = cc1.selectbox("Active / Coverage status column", cols, key="cs_status_col")
    active_vals  = cc1.text_input("Active status values (comma-separated)", value="A,Active,ACTIVE,1", key="cs_active_vals")
    termed_vals  = cc1.text_input("Terminated/inactive status values (comma-separated)", value="T,Termed,Inactive,0,INACTIVE", key="cs_termed_vals")
    dob_col_cs   = cc2.selectbox("Date of Birth column", cols, key="cs_dob_col")
    hire_col     = cc2.selectbox("Hire date column", cols, key="cs_hire_col")
    term_col     = cc2.selectbox("Termination date column (if applicable)", ["(none)"] + cols, key="cs_term_col")
    death_col    = cc2.selectbox("Date of Death column (if applicable)", ["(none)"] + cols, key="cs_death_col")
    cov_start    = cc1.selectbox("Coverage Start Date column", cols, key="cs_cov_start")
    cov_end      = cc1.selectbox("Coverage End Date column (if applicable)", ["(none)"] + cols, key="cs_cov_end")
    cs_date_fmt  = cc2.text_input("Date format for all date columns", value="%Y-%m-%d", key="cs_date_fmt")

    def parse_col(tmp, col, fmt):
        return pd.to_datetime(tmp[col].astype(str).str.strip(), format=fmt, errors="coerce")

    # ── Active with date of death ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**1. Active Status with Past Date of Death**")
    st.caption("Members marked as active who have a non-null, past date of death are a logic conflict.")
    if st.button("Run", key="btn_active_death"):
        if death_col == "(none)":
            st.warning("No date of death column selected above.")
        else:
            try:
                tmp = df.copy()
                act_set = {v.strip().lower() for v in active_vals.split(",") if v.strip()}
                tmp["_STATUS"] = tmp[status_col].astype(str).str.strip().str.lower()
                tmp["_DEATH"]  = parse_col(tmp, death_col, cs_date_fmt)
                today          = pd.Timestamp(date.today())
                mask = tmp["_STATUS"].isin(act_set) & tmp["_DEATH"].notna() & (tmp["_DEATH"] < today)
                st.metric("Active members with past date of death", f"{int(mask.sum()):,}")
                if mask.any():
                    st.session_state["active_death_hits"] = df[mask.values].reset_index(drop=True)
                else:
                    st.success("✅ No active members with a past date of death.")
                    st.session_state.pop("active_death_hits", None)
            except Exception as e:
                st.error(f"Error: {e}")

    if "active_death_hits" in st.session_state:
        with st.expander("Show active-with-death records"):
            st.dataframe(st.session_state["active_death_hits"], use_container_width=True)

    # ── Rehire without prior termination ────────────────────────────────────
    st.markdown("---")
    st.markdown("**2. Rehire Detection & Anomalies**")
    st.caption(
        "For employees that term then rehire, this should be clearly identifiable in the data. "
        "Also flags members where a rehire date exists without a prior termination date."
    )
    rehire_col = st.selectbox("Rehire date column (if exists)", ["(none)"] + cols, key="cs_rehire_col")
    if st.button("Run", key="btn_rehire"):
        if rehire_col == "(none)" and term_col == "(none)":
            st.warning("Select at least a termination or rehire column above.")
        else:
            try:
                tmp = df.copy()
                tmp["_HIRE"]  = parse_col(tmp, hire_col, cs_date_fmt)
                if term_col != "(none)":
                    tmp["_TERM"] = parse_col(tmp, term_col, cs_date_fmt)
                if rehire_col != "(none)":
                    tmp["_REHIRE"] = parse_col(tmp, rehire_col, cs_date_fmt)

                hits = []
                # Rehire date exists but no termination date
                if rehire_col != "(none)" and term_col != "(none)":
                    has_rehire  = tmp["_REHIRE"].notna()
                    no_term     = tmp["_TERM"].isna()
                    orphan_mask = has_rehire & no_term
                    n = int(orphan_mask.sum())
                    hits.append({"Check": "Rehire date without termination date", "Count": n})
                    if n:
                        st.session_state["rehire_hits"] = df[orphan_mask.values].reset_index(drop=True)

                # Rehire date before hire date (nonsensical)
                if rehire_col != "(none)":
                    mask_before = tmp["_REHIRE"].notna() & tmp["_HIRE"].notna() & (tmp["_REHIRE"] < tmp["_HIRE"])
                    hits.append({"Check": "Rehire date before original hire date", "Count": int(mask_before.sum())})

                # Term date before hire date
                if term_col != "(none)":
                    mask_term_before = tmp["_TERM"].notna() & tmp["_HIRE"].notna() & (tmp["_TERM"] < tmp["_HIRE"])
                    hits.append({"Check": "Termination date before hire date", "Count": int(mask_term_before.sum())})

                if hits:
                    st.dataframe(pd.DataFrame(hits), use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")

    if "rehire_hits" in st.session_state:
        with st.expander("Show members with rehire but no termination"):
            st.dataframe(st.session_state["rehire_hits"], use_container_width=True)

    # ── Hire before birth ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**3. Hire Date Before Birth Date**")
    if st.button("Run", key="btn_hire_birth"):
        try:
            tmp = df.copy()
            tmp["_DOB"]  = parse_col(tmp, dob_col_cs, cs_date_fmt)
            tmp["_HIRE"] = parse_col(tmp, hire_col, cs_date_fmt)
            mask = tmp["_HIRE"].notna() & tmp["_DOB"].notna() & (tmp["_HIRE"] < tmp["_DOB"])
            st.metric("Hire date before birth date", f"{int(mask.sum()):,}")
            if mask.any():
                st.session_state["hire_birth_hits"] = df[mask.values].reset_index(drop=True)
            else:
                st.success("✅ No hire dates precede birth dates.")
                st.session_state.pop("hire_birth_hits", None)
        except Exception as e:
            st.error(f"Error: {e}")

    if "hire_birth_hits" in st.session_state:
        with st.expander("Show hire-before-birth records"):
            st.dataframe(st.session_state["hire_birth_hits"], use_container_width=True)

    # ── Hire date before company founding ───────────────────────────────────
    st.markdown("---")
    st.markdown("**4. Hire Date Before Company Founding Date**")
    founding_date = st.text_input("Company founding date", value="1900-01-01", key="cs_founding_date")
    if st.button("Run", key="btn_hire_founding"):
        try:
            tmp = df.copy()
            tmp["_HIRE"]  = parse_col(tmp, hire_col, cs_date_fmt)
            founding      = pd.Timestamp(founding_date)
            mask          = tmp["_HIRE"].notna() & (tmp["_HIRE"] < founding)
            st.metric("Hire dates before company founding date", f"{int(mask.sum()):,}")
            if mask.any():
                st.session_state["hire_founding_hits"] = df[mask.values].reset_index(drop=True)
            else:
                st.success("✅ No hire dates precede the company founding date.")
                st.session_state.pop("hire_founding_hits", None)
        except Exception as e:
            st.error(f"Error: {e}")

    if "hire_founding_hits" in st.session_state:
        with st.expander("Show hire-before-founding records"):
            st.dataframe(st.session_state["hire_founding_hits"], use_container_width=True)

    # ── Placeholder termination dates ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("**5. Placeholder Termination Dates**")
    st.caption(
        "Active members often have a far-future placeholder termination date (e.g., 12/31/2135) "
        "instead of a null. Validate that active members use these placeholders rather than nulls, "
        "and that truly terminated members don't have placeholder term dates."
    )
    term_placeholder_vals = st.text_input(
        "Placeholder termination date values (comma-separated)",
        value="12/31/2135,2135-12-31,12/31/9999,9999-12-31,12/31/2099,2099-12-31",
        key="cs_term_placeholder",
    )
    if st.button("Run", key="btn_term_placeholder") and term_col != "(none)":
        try:
            tmp     = df.copy()
            ph_vals = {v.strip() for v in term_placeholder_vals.split(",") if v.strip()}
            act_set = {v.strip().lower() for v in active_vals.split(",") if v.strip()}
            trm_set = {v.strip().lower() for v in termed_vals.split(",") if v.strip()}
            tmp["_TERM_RAW"] = tmp[term_col].astype(str).str.strip()
            tmp["_STATUS"]   = tmp[status_col].astype(str).str.strip().str.lower()
            tmp["_IS_PH"]    = tmp["_TERM_RAW"].isin(ph_vals)
            tmp["_TERM_NULL"] = tmp[term_col].isnull() | (tmp["_TERM_RAW"] == "")

            is_active = tmp["_STATUS"].isin(act_set)
            is_termed = tmp["_STATUS"].isin(trm_set)

            # Active members without placeholder term date (and without null) — unexpected non-placeholder
            active_no_ph = is_active & ~tmp["_IS_PH"] & ~tmp["_TERM_NULL"]
            # Active members with null term date — missing placeholder
            active_null  = is_active & tmp["_TERM_NULL"]
            # Termed members with placeholder term date — may still be "open"
            termed_with_ph = is_termed & tmp["_IS_PH"]

            ma, mb, mc = st.columns(3)
            ma.metric("Active with placeholder term date", f"{int((is_active & tmp['_IS_PH']).sum()):,}")
            mb.metric("Active with NULL term date (no placeholder)", f"{int(active_null.sum()):,}")
            mc.metric("Termed with placeholder term date", f"{int(termed_with_ph.sum()):,}")

            if active_null.any():
                st.warning(f"⚠️ {int(active_null.sum()):,} active members have a null termination date instead of a placeholder.")
            if termed_with_ph.any():
                st.warning(f"⚠️ {int(termed_with_ph.sum()):,} terminated members still have a placeholder termination date.")

            hits = []
            if active_null.any():
                hits.append({"Issue": "Active — null term date", "Count": int(active_null.sum()), "_mask": active_null.values})
            if termed_with_ph.any():
                hits.append({"Issue": "Termed — still has placeholder term date", "Count": int(termed_with_ph.sum()), "_mask": termed_with_ph.values})
            if active_no_ph.any():
                hits.append({"Issue": "Active — non-placeholder, non-null term date", "Count": int(active_no_ph.sum()), "_mask": active_no_ph.values})

            if hits:
                summary = pd.DataFrame([{"Issue": h["Issue"], "Count": h["Count"]} for h in hits])
                st.session_state["term_placeholder_hits"] = hits
                row = drilldown(summary, "term_ph", "Click an issue to see affected records.")
                if row is not None:
                    chosen = next(h for h in hits if h["Issue"] == row["Issue"])
                    res    = df[chosen["_mask"]].reset_index(drop=True)
                    st.markdown(f"#### {chosen['Issue']} — {len(res):,} rows")
                    st.dataframe(res, use_container_width=True)
            else:
                st.success("✅ Placeholder termination date logic appears consistent.")
        except Exception as e:
            st.error(f"Error: {e}")
    elif st.button("Run placeholder check", key="btn_term_ph_warn") if term_col == "(none)" else False:
        st.warning("Select a Termination Date column at the top of this tab.")

    # ── Coverage date logic ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**6. Coverage Start / End Date Logic**")
    st.caption("Coverage start and end dates should be logical (start ≤ end, both not future for active members, etc.).")
    if st.button("Run", key="btn_cov_dates"):
        try:
            tmp  = df.copy()
            tmp["_COV_START"] = parse_col(tmp, cov_start, cs_date_fmt)
            today = pd.Timestamp(date.today())
            issues = []

            # Coverage start in future (not expected for active members)
            start_future = tmp["_COV_START"].notna() & (tmp["_COV_START"] > today)
            issues.append({"Check": "Coverage start date in future", "Count": int(start_future.sum()), "_mask": start_future.values})

            if cov_end != "(none)":
                tmp["_COV_END"] = parse_col(tmp, cov_end, cs_date_fmt)
                # End before start
                end_before_start = tmp["_COV_START"].notna() & tmp["_COV_END"].notna() & (tmp["_COV_END"] < tmp["_COV_START"])
                issues.append({"Check": "Coverage end before start", "Count": int(end_before_start.sum()), "_mask": end_before_start.values})

            summary = pd.DataFrame([{"Check": i["Check"], "Rows": i["Count"]} for i in issues])
            st.session_state["cov_date_results"] = issues

            row = drilldown(summary, "cov_dates", "Click a check to see the flagged records.")
            if row is not None:
                chosen = next(i for i in issues if i["Check"] == row["Check"])
                res    = df[chosen["_mask"]].reset_index(drop=True)
                st.markdown(f"#### {chosen['Check']} — {len(res):,} rows")
                st.dataframe(res, use_container_width=True)

            if all(i["Count"] == 0 for i in issues):
                st.success("✅ Coverage dates are logically consistent.")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Members with no coverage ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**7. Members with No Current Coverage**")
    st.caption(
        "Identify members with no active current or historical coverage and confirm if they "
        "should be on these files."
    )
    if st.button("Run", key="btn_no_cov"):
        try:
            tmp     = df.copy()
            act_set = {v.strip().lower() for v in active_vals.split(",") if v.strip()}
            tmp["_STATUS"] = tmp[status_col].astype(str).str.strip().str.lower()
            tmp["_COV_START"] = parse_col(tmp, cov_start, cs_date_fmt)
            today = pd.Timestamp(date.today())
            is_active = tmp["_STATUS"].isin(act_set)
            no_active_cov = ~is_active & tmp["_COV_START"].notna() & (tmp["_COV_START"] > today)
            null_cov_start = tmp["_COV_START"].isna()

            ma, mb = st.columns(2)
            ma.metric("Rows with null coverage start date", f"{int(null_cov_start.sum()):,}")
            mb.metric("Non-active rows with future coverage start", f"{int(no_active_cov.sum()):,}")

            if null_cov_start.any():
                st.warning(f"⚠️ {int(null_cov_start.sum()):,} rows have no coverage start date.")
                with st.expander("Show null coverage start records (sample)"):
                    st.dataframe(df[null_cov_start.values].head(50), use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # ── HRIS vs. carrier date match ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("**8. HRIS / Carrier Date Comparison**")
    st.caption(
        "When two eligibility sources are available (e.g., carrier file and HRIS/Ben Admin), "
        "enrollment dates and statuses should match."
    )
    hris_col    = st.selectbox("HRIS / Ben Admin date column", ["(none)"] + cols, key="cs_hris_col")
    carrier_col = st.selectbox("Carrier eligibility date column", ["(none)"] + cols, key="cs_carrier_col")
    if st.button("Run", key="btn_hris_match") and hris_col != "(none)" and carrier_col != "(none)":
        try:
            tmp = df.copy()
            tmp["_HRIS"]    = parse_col(tmp, hris_col, cs_date_fmt)
            tmp["_CARRIER"] = parse_col(tmp, carrier_col, cs_date_fmt)
            both_valid = tmp["_HRIS"].notna() & tmp["_CARRIER"].notna()
            mismatch   = both_valid & (tmp["_HRIS"] != tmp["_CARRIER"])
            diff_days  = (tmp.loc[mismatch, "_HRIS"] - tmp.loc[mismatch, "_CARRIER"]).dt.days.abs()
            st.metric("Rows where dates differ", f"{int(mismatch.sum()):,}")
            if mismatch.any():
                st.metric("Median day difference", f"{diff_days.median():.0f} days")
                st.metric("Max day difference", f"{diff_days.max():.0f} days")
                with st.expander("Show mismatched rows"):
                    res = df[mismatch.values].reset_index(drop=True)
                    st.dataframe(res, use_container_width=True)
            else:
                st.success("✅ HRIS and carrier dates match on all rows with both values present.")
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Consistency: active vs. termed ───────────────────────────────────────
    st.markdown("---")
    st.markdown("**9. Active vs. Termed Population Data Consistency**")
    st.caption(
        "Confirm that volume and formatting are consistent across active and termed members — "
        "e.g., termed members should not have systematically fewer populated fields."
    )
    if st.button("Run consistency check", key="btn_active_termed_consistency"):
        try:
            tmp     = df.copy()
            act_set = {v.strip().lower() for v in active_vals.split(",") if v.strip()}
            trm_set = {v.strip().lower() for v in termed_vals.split(",") if v.strip()}
            tmp["_STATUS"] = tmp[status_col].astype(str).str.strip().str.lower()
            active_df = tmp[tmp["_STATUS"].isin(act_set)]
            termed_df = tmp[tmp["_STATUS"].isin(trm_set)]

            rows_out = []
            for col in cols:
                def fill_pct(d):
                    s = d[col]
                    empty = s.isnull().sum() + (s.astype(str).str.strip() == "").sum()
                    return round((len(d) - empty) / len(d) * 100, 1) if len(d) > 0 else None

                a_pct = fill_pct(active_df)
                t_pct = fill_pct(termed_df)
                diff  = abs(a_pct - t_pct) if a_pct is not None and t_pct is not None else None
                rows_out.append({
                    "Column": col,
                    "Active Fill %": a_pct,
                    "Termed Fill %": t_pct,
                    "Diff %": diff,
                    "⚠️ Large Gap": "YES" if diff is not None and diff > 20 else "",
                })
            result = pd.DataFrame(rows_out).sort_values("Diff %", ascending=False)
            st.caption(f"Showing {len(active_df):,} active vs. {len(termed_df):,} termed records.")
            row = drilldown(result, "act_termed_consistency",
                            "Click a column to see records where that field is empty, split by status.")
            if row is not None:
                col_name   = row["Column"]
                empty_mask = df[col_name].isnull() | (df[col_name].astype(str).str.strip() == "")
                res        = df[empty_mask].reset_index(drop=True)
                st.markdown(f"#### `{col_name}` — {len(res):,} empty rows")
                st.dataframe(res, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — Volume & Distribution
# ════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Volume & Distribution Checks")

    # ── Monthly enrollment volume ────────────────────────────────────────────
    st.markdown("**Monthly Enrollment Volumes**")
    st.caption("Chart monthly enrollment volumes and investigate spikes. Known seasonal patterns (e.g., Q4 upticks) should be annotated.")
    vol_date_col = st.selectbox("Coverage start or effective date column", cols, key="vol_date")
    vol_date_fmt = st.text_input("Date format", value="%Y-%m-%d", key="vol_fmt")

    if st.button("Generate enrollment chart", key="btn_vol"):
        try:
            tmp = df.copy()
            tmp["_DATE"] = pd.to_datetime(tmp[vol_date_col].astype(str).str.strip(), format=vol_date_fmt, errors="coerce")
            tmp = tmp.dropna(subset=["_DATE"])
            tmp["_YM"] = tmp["_DATE"].dt.to_period("M").astype(str)

            monthly = tmp.groupby("_YM").size().reset_index(name="Enrollment Count").sort_values("_YM")
            st.session_state["vol_monthly"] = monthly

            st.markdown("**Monthly Enrollment Count**")
            st.bar_chart(monthly.set_index("_YM")["Enrollment Count"])

            mean_v  = monthly["Enrollment Count"].mean()
            std_v   = monthly["Enrollment Count"].std()
            spikes  = monthly[monthly["Enrollment Count"] > mean_v + 2 * std_v]
            if not spikes.empty:
                st.warning(f"⚠️ Volume spikes detected ({len(spikes)} month(s) > 2 std dev above mean):")
                st.dataframe(spikes, use_container_width=True)

            st.markdown("**Full Monthly Summary**")
            st.dataframe(monthly, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")

    # ── Employee vs. dependent ratio ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Employee vs. Dependent Count Ratio**")
    st.caption("Employee vs. dependent counts should be within an acceptable range given the member population.")
    ratio_rel_col = st.selectbox("Relationship / role column", cols, key="ratio_rel_col")
    ratio_emp_kw  = st.text_input("Employee codes (comma-separated)", value="EE,employee,self,00,E,18,subscriber", key="ratio_emp_kw")
    ratio_dep_kw  = st.text_input("Dependent codes (comma-separated)", value="spouse,child,dependent,01,02,S,D,C", key="ratio_dep_kw")
    if st.button("Calculate ratio", key="btn_ratio"):
        emp_kws = {k.strip().lower() for k in ratio_emp_kw.split(",") if k.strip()}
        dep_kws = {k.strip().lower() for k in ratio_dep_kw.split(",") if k.strip()}
        tmp     = df.copy()
        tmp["_REL"] = tmp[ratio_rel_col].astype(str).str.strip().str.lower()
        n_emp = int(tmp["_REL"].isin(emp_kws).sum())
        n_dep = int(tmp["_REL"].isin(dep_kws).sum())
        n_unk = total_rows - n_emp - n_dep
        ratio = n_dep / n_emp if n_emp > 0 else None

        ma, mb, mc, md = st.columns(4)
        ma.metric("Employees", f"{n_emp:,}")
        mb.metric("Dependents", f"{n_dep:,}")
        mc.metric("Unknown / Other", f"{n_unk:,}")
        md.metric("Dep : Emp ratio", f"{ratio:.2f}" if ratio is not None else "N/A")

        if ratio is not None:
            if ratio > 5:
                st.warning(f"⚠️ High dependent ratio ({ratio:.2f}:1) — confirm this is expected for this population.")
            elif ratio < 0.3:
                st.info(f"Low dependent ratio ({ratio:.2f}:1) — expected for some populations (e.g., single-employee groups).")
            else:
                st.success(f"✅ Dependent ratio ({ratio:.2f}:1) appears within a typical range.")

        # Distribution by relationship code
        rel_dist = df[ratio_rel_col].value_counts(dropna=False).reset_index()
        rel_dist.columns = ["Relationship", "Count"]
        rel_dist["%"] = (rel_dist["Count"] / total_rows * 100).round(2)
        st.session_state["vol_ratio"] = rel_dist

    if "vol_ratio" in st.session_state:
        row = drilldown(st.session_state["vol_ratio"], "vol_ratio",
                        "Click a relationship to see all records with that code.")
        if row is not None:
            val  = row["Relationship"]
            mask = df[ratio_rel_col].astype(str) == str(val) if pd.notna(val) else df[ratio_rel_col].isnull()
            res  = df[mask].reset_index(drop=True)
            st.markdown(f"#### Relationship `{val}` — {len(res):,} rows")
            st.dataframe(res, use_container_width=True)

    # ── Enrollment trend by status ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Enrollment Breakdown by Status**")
    st.caption("Active vs. termed vs. COBRA vs. other populations month over month.")
    trend_status_col = st.selectbox("Status column for trend", cols, key="trend_status_col")
    trend_date_col   = st.selectbox("Date column for trend", cols, key="trend_date_col")
    if st.button("Run trend", key="btn_trend"):
        try:
            tmp = df.copy()
            tmp["_DATE"]   = pd.to_datetime(tmp[trend_date_col].astype(str).str.strip(), format=vol_date_fmt, errors="coerce")
            tmp = tmp.dropna(subset=["_DATE"])
            tmp["_YM"]     = tmp["_DATE"].dt.to_period("M").astype(str)
            tmp["_STATUS"] = tmp[trend_status_col].astype(str).str.strip()

            pivot = (
                tmp.groupby(["_YM", "_STATUS"])
                .size()
                .reset_index(name="Count")
                .pivot(index="_YM", columns="_STATUS", values="Count")
                .fillna(0)
                .sort_index()
            )
            st.dataframe(pivot, use_container_width=True)
            st.bar_chart(pivot)
        except Exception as e:
            st.error(f"Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — SSN Validation
# ════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("SSN Validation")
    st.caption(
        "Checks SSN/social columns — must be exactly 9 digits. "
        "Also flags known default SSNs (000000000, 990000001) and special-purpose patterns."
    )

    ssn_id_cols   = st.multiselect(
        "Unique row identifier columns (for sample output)",
        cols,
        default=[c for c in cols if any(x in c.upper() for x in ["ID", "MEMBER", "EE"])][:2],
        key="ssn_id",
    )
    ssn_n_samples = int(st.number_input("Sample identifiers per issue type", 1, 20, 6, key="ssn_samp"))

    # Known default SSN values for eligibility data
    ssn_known_defaults = st.text_input(
        "Known default / placeholder SSN values (comma-separated)",
        value="000000000,990000001,999999999,123456789,111111111",
        key="ssn_known_defaults",
    )

    if st.button("Run", key="btn_ssn"):
        ssn_cols = [c for c in cols if re.search(r"ssn|social", c, re.IGNORECASE)]
        if not ssn_cols:
            st.warning("No SSN/social columns detected. Rename columns or use the Member Identification tab.")
        else:
            known_defaults = {v.strip() for v in ssn_known_defaults.split(",") if v.strip()}

            def _blank(v):  return str(v).strip() == "" if not pd.isnull(v) else False
            def _null_s(v): return str(v).strip().lower() == "null" if not pd.isnull(v) else False
            def _valid(v):  return bool(re.fullmatch(r"\d{9}", str(v).strip()))
            def _default(v): return str(v).strip() in known_defaults
            def _invalid(v):
                return not (pd.isnull(v) or _blank(v) or _null_s(v)) and (
                    bool(re.search(r"[^0-9]", str(v).strip())) or not _valid(v))

            def sample_ids(mask):
                if not ssn_id_cols: return []
                return (
                    df.loc[mask]
                    .apply(lambda r: " | ".join(str(r[c]) for c in ssn_id_cols if c in r.index), axis=1)
                    .dropna().unique()[:ssn_n_samples].tolist()
                )

            results = []
            for col in ssn_cols:
                blank_m   = df[col].apply(_blank)
                null_m    = df[col].apply(_null_s)
                nan_m     = df[col].isnull()
                inv_m     = df[col].apply(_invalid)
                val_m     = df[col].apply(_valid)
                default_m = df[col].apply(_default)
                results.append({
                    "Column": col,
                    "Total": total_rows,
                    "NaN": int(nan_m.sum()),
                    "Blank": int(blank_m.sum()),
                    '"null" string': int(null_m.sum()),
                    "Invalid Format": int(inv_m.sum()),
                    "Known Default SSN": int(default_m.sum()),
                    "Valid (9 digits)": int(val_m.sum()),
                    "Sample IDs — Invalid": str(sample_ids(inv_m)),
                    "Sample IDs — Default": str(sample_ids(default_m)),
                })

            results_df = pd.DataFrame(results)
            st.dataframe(results_df, use_container_width=True)

            for row in results:
                col = row["Column"]
                if row["Invalid Format"]:
                    st.warning(f"⚠️ `{col}`: {row['Invalid Format']:,} rows have an invalid SSN format.")
                if row["Known Default SSN"]:
                    st.info(f"ℹ️ `{col}`: {row['Known Default SSN']:,} rows contain a known default SSN — validate these are intentional (e.g., newborns).")

            # Drill into invalids or defaults for any SSN column
            if len(ssn_cols) > 0:
                st.markdown("---")
                st.markdown("**Drill Into Invalid / Default SSNs**")
                ssn_drill_col = st.selectbox("SSN column to drill into", ssn_cols, key="ssn_drill_col")
                drill_type    = st.radio("Show records with", ["Invalid Format", "Known Default SSN", "Blank / NaN"], key="ssn_drill_type")

                if st.button("Show records", key="btn_ssn_drill"):
                    col_s = df[ssn_drill_col]
                    if drill_type == "Invalid Format":
                        mask = col_s.apply(_invalid)
                    elif drill_type == "Known Default SSN":
                        mask = col_s.apply(_default)
                    else:
                        mask = col_s.isnull() | col_s.astype(str).str.strip().eq("")

                    res = df[mask].reset_index(drop=True)
                    if not res.empty:
                        st.markdown(f"#### `{ssn_drill_col}` — {drill_type} — {len(res):,} rows")
                        # Redact the SSN column in display for privacy
                        display_res = res.copy()
                        display_res[ssn_drill_col] = display_res[ssn_drill_col].astype(str).str[:3] + "******"
                        st.dataframe(display_res, use_container_width=True)
                    else:
                        st.success(f"✅ No records match `{drill_type}` in `{ssn_drill_col}`.")
