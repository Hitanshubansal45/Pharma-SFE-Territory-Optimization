"""
Pharmaceutical SFE - SQL Analysis Layer
6 Analytical Modules — ZS Associates Style
Uses DuckDB (in-memory SQL) for fast analysis
Outputs one CSV per module → Tableau ready
"""

import duckdb
import pandas as pd
import os

DATA_DIR   = "/home/claude/pharma_data"
OUTPUT_DIR = "/home/claude/pharma_analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

con = duckdb.connect()

# Load all tables into DuckDB
con.execute(f"CREATE TABLE territories AS SELECT * FROM read_csv_auto('{DATA_DIR}/territories.csv')")
con.execute(f"CREATE TABLE products    AS SELECT * FROM read_csv_auto('{DATA_DIR}/products.csv')")
con.execute(f"CREATE TABLE reps        AS SELECT * FROM read_csv_auto('{DATA_DIR}/reps.csv')")
con.execute(f"CREATE TABLE physicians  AS SELECT * FROM read_csv_auto('{DATA_DIR}/physicians.csv')")
con.execute(f"CREATE TABLE sales       AS SELECT * FROM read_csv_auto('{DATA_DIR}/sales.csv')")
con.execute(f"CREATE TABLE call_logs   AS SELECT * FROM read_csv_auto('{DATA_DIR}/call_logs.csv')")

print("Tables loaded into DuckDB ✓\n")

# ─────────────────────────────────────────────────────────────
# MODULE 1: SALES PERFORMANCE ANALYSIS
# Territory-level revenue, YoY growth, top/bottom ranking
# ─────────────────────────────────────────────────────────────
print("MODULE 1: Sales Performance Analysis...")

q1 = """
WITH yearly AS (
    SELECT
        s.territory_id,
        t.region,
        s.year,
        SUM(s.revenue_usd)     AS revenue,
        SUM(s.net_revenue_usd) AS net_revenue,
        SUM(s.units_sold)      AS units,
        COUNT(DISTINCT s.rep_id) AS active_reps
    FROM sales s
    JOIN territories t USING (territory_id)
    GROUP BY s.territory_id, t.region, s.year
),
pivoted AS (
    SELECT
        territory_id,
        region,
        MAX(CASE WHEN year = 2023 THEN revenue END) AS rev_2023,
        MAX(CASE WHEN year = 2024 THEN revenue END) AS rev_2024,
        MAX(CASE WHEN year = 2023 THEN units   END) AS units_2023,
        MAX(CASE WHEN year = 2024 THEN units   END) AS units_2024,
        MAX(active_reps) AS active_reps
    FROM yearly
    GROUP BY territory_id, region
)
SELECT
    p.*,
    t.market_potential_index,
    t.competitor_intensity,
    t.urban_index,
    t.num_target_hcps,
    ROUND((p.rev_2024 - p.rev_2023) / NULLIF(p.rev_2023, 0) * 100, 2) AS yoy_growth_pct,
    ROUND(p.rev_2024 / NULLIF(t.market_potential_index, 0), 2)          AS revenue_per_mpi,
    NTILE(5) OVER (ORDER BY p.rev_2024)                                  AS revenue_quintile
FROM pivoted p
JOIN territories t USING (territory_id)
ORDER BY rev_2024 DESC
"""

m1 = con.execute(q1).df()
m1.to_csv(f"{OUTPUT_DIR}/m1_sales_performance.csv", index=False)
print(f"  ✓ m1_sales_performance.csv — {len(m1)} rows")

# ─────────────────────────────────────────────────────────────
# MODULE 2: WHITESPACE OPPORTUNITY ANALYSIS (Core ZS Output)
# Market potential vs actual sales → quadrant classification
# ─────────────────────────────────────────────────────────────
print("MODULE 2: Whitespace Opportunity Analysis...")

q2 = """
WITH terr_sales AS (
    SELECT
        territory_id,
        SUM(revenue_usd) AS total_revenue,
        SUM(units_sold)  AS total_units
    FROM sales
    WHERE year = 2024
    GROUP BY territory_id
),
terr_calls AS (
    SELECT
        territory_id,
        COUNT(*)                        AS total_calls,
        AVG(CAST(converted AS INTEGER)) AS conversion_rate
    FROM call_logs
    WHERE year = 2024
    GROUP BY territory_id
),
combined AS (
    SELECT
        t.territory_id,
        t.region,
        t.market_potential_index                                              AS mpi,
        t.competitor_intensity,
        t.urban_index,
        t.num_target_hcps,
        COALESCE(ts.total_revenue, 0)                                         AS actual_revenue,
        COALESCE(tc.total_calls, 0)                                           AS call_volume,
        COALESCE(tc.conversion_rate, 0)                                       AS conversion_rate,
        -- Estimated potential revenue: MPI × scaling factor
        ROUND(t.market_potential_index * 8500, 2)                             AS potential_revenue,
        ROUND(COALESCE(ts.total_revenue, 0) /
              NULLIF(t.market_potential_index * 8500, 0) * 100, 1)           AS realization_pct
    FROM territories t
    LEFT JOIN terr_sales  ts USING (territory_id)
    LEFT JOIN terr_calls  tc USING (territory_id)
),
med AS (
    SELECT
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mpi)            AS med_mpi,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY actual_revenue) AS med_revenue
    FROM combined
)
SELECT
    c.*,
    m.med_mpi,
    m.med_revenue,
    ROUND(c.potential_revenue - c.actual_revenue, 2) AS opportunity_gap_usd,
    CASE
        WHEN c.mpi >= m.med_mpi AND c.actual_revenue >= m.med_revenue THEN 'Star'
        WHEN c.mpi >= m.med_mpi AND c.actual_revenue <  m.med_revenue THEN 'Whitespace'
        WHEN c.mpi <  m.med_mpi AND c.actual_revenue >= m.med_revenue THEN 'Saturated'
        ELSE 'Abandon'
    END AS whitespace_quadrant
FROM combined c, med m
ORDER BY opportunity_gap_usd DESC
"""

m2 = con.execute(q2).df()
m2.to_csv(f"{OUTPUT_DIR}/m2_whitespace_analysis.csv", index=False)
print(f"  ✓ m2_whitespace_analysis.csv — {len(m2)} rows")
print(f"    Quadrant counts:\n{m2['whitespace_quadrant'].value_counts().to_string()}")
total_gap = m2[m2['whitespace_quadrant'] == 'Whitespace']['opportunity_gap_usd'].sum()
print(f"    Total whitespace opportunity: ${total_gap:,.0f}")

# ─────────────────────────────────────────────────────────────
# MODULE 3: SALES FORCE EFFECTIVENESS (SFE) METRICS
# Rep-level productivity, call rates, conversion
# ─────────────────────────────────────────────────────────────
print("\nMODULE 3: Sales Force Effectiveness...")

q3 = """
WITH rep_sales AS (
    SELECT
        rep_id,
        SUM(revenue_usd)  AS total_revenue,
        SUM(units_sold)   AS total_units,
        COUNT(DISTINCT product_id) AS products_sold,
        COUNT(DISTINCT month)      AS active_months
    FROM sales
    GROUP BY rep_id
),
rep_calls AS (
    SELECT
        rep_id,
        COUNT(*)                         AS total_calls,
        SUM(CAST(converted AS INTEGER))  AS total_conversions,
        AVG(CAST(converted AS INTEGER))  AS conversion_rate,
        COUNT(DISTINCT hcp_id)           AS unique_hcps_visited,
        COUNT(DISTINCT month)            AS months_active,
        AVG(call_duration_min)           AS avg_call_duration_min
    FROM call_logs
    GROUP BY rep_id
),
rep_hcp_tier AS (
    SELECT
        cl.rep_id,
        SUM(CASE WHEN ph.prescriber_tier = 'A' THEN 1 ELSE 0 END) AS tier_a_calls,
        SUM(CASE WHEN ph.prescriber_tier = 'B' THEN 1 ELSE 0 END) AS tier_b_calls,
        SUM(CASE WHEN ph.prescriber_tier = 'C' THEN 1 ELSE 0 END) AS tier_c_calls
    FROM call_logs cl
    JOIN physicians ph USING (hcp_id)
    GROUP BY cl.rep_id
)
SELECT
    r.rep_id,
    r.rep_name,
    r.territory_id,
    r.region,
    r.experience_years,
    r.education,
    rs.total_revenue,
    rs.total_units,
    rs.products_sold,
    rc.total_calls,
    rc.total_conversions,
    ROUND(rc.conversion_rate * 100, 1)                                       AS conversion_rate_pct,
    rc.unique_hcps_visited,
    rc.avg_call_duration_min,
    rh.tier_a_calls,
    rh.tier_b_calls,
    rh.tier_c_calls,
    ROUND(rh.tier_a_calls * 100.0 / NULLIF(rc.total_calls, 0), 1)           AS tier_a_call_pct,
    ROUND(rc.total_calls  / NULLIF(rc.months_active, 0), 1)                  AS avg_monthly_calls,
    ROUND(rs.total_revenue / NULLIF(rc.total_calls, 0), 2)                   AS revenue_per_call,
    ROUND(rs.total_revenue / NULLIF(rc.unique_hcps_visited, 0), 2)           AS revenue_per_hcp,
    -- Rep Productivity Index (normalized 0–100)
    ROUND(
        (rs.total_revenue / NULLIF(rc.total_calls, 0)) /
        MAX(rs.total_revenue / NULLIF(rc.total_calls, 0)) OVER () * 100
    , 1) AS productivity_index,
    NTILE(4) OVER (ORDER BY rs.total_revenue) AS performance_quartile
FROM reps r
JOIN rep_sales   rs USING (rep_id)
JOIN rep_calls   rc USING (rep_id)
JOIN rep_hcp_tier rh USING (rep_id)
ORDER BY total_revenue DESC
"""

m3 = con.execute(q3).df()
m3.to_csv(f"{OUTPUT_DIR}/m3_sfe_metrics.csv", index=False)
print(f"  ✓ m3_sfe_metrics.csv — {len(m3)} rows")
print(f"    Avg revenue/call: ${m3['revenue_per_call'].mean():,.0f}")
print(f"    Avg productivity index: {m3['productivity_index'].mean():.1f}")

# ─────────────────────────────────────────────────────────────
# MODULE 4: HCP COVERAGE GAP ANALYSIS
# High-value doctors with low rep coverage = missed revenue
# ─────────────────────────────────────────────────────────────
print("\nMODULE 4: HCP Coverage Gap Analysis...")

q4 = """
WITH hcp_calls AS (
    SELECT
        hcp_id,
        COUNT(*)                         AS total_calls_received,
        COUNT(DISTINCT rep_id)           AS unique_reps,
        COUNT(DISTINCT month)            AS months_contacted,
        AVG(CAST(converted AS INTEGER))  AS conversion_rate,
        COUNT(*) / 24.0                  AS avg_monthly_calls   -- 24 months total
    FROM call_logs
    GROUP BY hcp_id
)
SELECT
    ph.hcp_id,
    ph.hcp_name,
    ph.territory_id,
    ph.specialty,
    ph.prescriber_tier,
    ph.monthly_rx_volume,
    ph.hospital_affiliation,
    ph.digital_engagement,
    COALESCE(hc.total_calls_received, 0)  AS total_calls_received,
    COALESCE(hc.unique_reps, 0)           AS unique_reps_visited,
    COALESCE(hc.months_contacted, 0)      AS months_contacted,
    COALESCE(hc.avg_monthly_calls, 0)     AS avg_monthly_calls,
    COALESCE(hc.conversion_rate, 0)       AS conversion_rate,
    -- Coverage gap flag: Tier A HCP with < 1 call/month = critical gap
    CASE
        WHEN ph.prescriber_tier = 'A' AND COALESCE(hc.avg_monthly_calls, 0) < 1.0 THEN 'Critical Gap'
        WHEN ph.prescriber_tier = 'A' AND COALESCE(hc.avg_monthly_calls, 0) < 2.0 THEN 'Undercovered'
        WHEN ph.prescriber_tier = 'B' AND COALESCE(hc.avg_monthly_calls, 0) < 0.5 THEN 'Undercovered'
        WHEN COALESCE(hc.total_calls_received, 0) = 0                               THEN 'Not Reached'
        ELSE 'Adequately Covered'
    END AS coverage_status,
    -- Estimated monthly revenue at risk (rx volume × avg revenue per Rx)
    ROUND(ph.monthly_rx_volume * 420 *
          CASE ph.prescriber_tier WHEN 'A' THEN 1.0 WHEN 'B' THEN 0.6 ELSE 0.3 END, 0
    ) AS estimated_monthly_revenue_potential
FROM physicians ph
LEFT JOIN hcp_calls hc USING (hcp_id)
ORDER BY ph.prescriber_tier, ph.monthly_rx_volume DESC
"""

m4 = con.execute(q4).df()
m4.to_csv(f"{OUTPUT_DIR}/m4_hcp_coverage_gap.csv", index=False)
print(f"  ✓ m4_hcp_coverage_gap.csv — {len(m4)} rows")
print(f"    Coverage status:\n{m4['coverage_status'].value_counts().to_string()}")
critical = m4[m4['coverage_status'] == 'Critical Gap']
print(f"    Revenue at risk (critical gaps): ${critical['estimated_monthly_revenue_potential'].sum():,.0f}/month")

# ─────────────────────────────────────────────────────────────
# MODULE 5: PRODUCT PORTFOLIO (BCG) ANALYSIS
# Monthly trend + BCG positioning per product
# ─────────────────────────────────────────────────────────────
print("\nMODULE 5: Product Portfolio (BCG) Analysis...")

q5 = """
WITH monthly_product AS (
    SELECT
        s.product_id,
        p.name                                AS product_name,
        p.therapeutic_area,
        p.bcg_quadrant,
        p.market_share_pct,
        p.market_growth_rate,
        p.list_price,
        s.year,
        s.month_num,
        s.month,
        SUM(s.revenue_usd)                    AS monthly_revenue,
        SUM(s.units_sold)                     AS monthly_units,
        COUNT(DISTINCT s.rep_id)              AS reps_selling,
        COUNT(DISTINCT s.territory_id)        AS territories_active
    FROM sales s
    JOIN products p USING (product_id)
    GROUP BY s.product_id, p.name, p.therapeutic_area, p.bcg_quadrant,
             p.market_share_pct, p.market_growth_rate, p.list_price,
             s.year, s.month_num, s.month
),
product_totals AS (
    SELECT
        product_id,
        product_name,
        therapeutic_area,
        bcg_quadrant,
        market_share_pct,
        market_growth_rate,
        list_price,
        SUM(monthly_revenue)                  AS total_revenue,
        SUM(monthly_units)                    AS total_units,
        SUM(CASE WHEN year = 2023 THEN monthly_revenue END) AS rev_2023,
        SUM(CASE WHEN year = 2024 THEN monthly_revenue END) AS rev_2024,
        MAX(reps_selling)                     AS peak_reps_selling,
        MAX(territories_active)               AS peak_territories
    FROM monthly_product
    GROUP BY product_id, product_name, therapeutic_area, bcg_quadrant,
             market_share_pct, market_growth_rate, list_price
)
SELECT
    *,
    ROUND((rev_2024 - rev_2023) / NULLIF(rev_2023, 0) * 100, 1) AS revenue_growth_pct,
    ROUND(total_revenue / SUM(total_revenue) OVER () * 100, 1)   AS portfolio_share_pct
FROM product_totals
ORDER BY total_revenue DESC
"""

m5 = con.execute(q5).df()
m5.to_csv(f"{OUTPUT_DIR}/m5_product_portfolio.csv", index=False)
print(f"  ✓ m5_product_portfolio.csv — {len(m5)} rows")
print(m5[['product_name','bcg_quadrant','total_revenue','portfolio_share_pct']].to_string(index=False))

# Monthly trend for sparklines
q5b = """
SELECT
    s.product_id,
    p.name AS product_name,
    p.bcg_quadrant,
    s.month,
    s.year,
    s.month_num,
    SUM(s.revenue_usd) AS monthly_revenue
FROM sales s JOIN products p USING (product_id)
GROUP BY s.product_id, p.name, p.bcg_quadrant, s.month, s.year, s.month_num
ORDER BY s.product_id, s.month
"""
m5b = con.execute(q5b).df()
m5b.to_csv(f"{OUTPUT_DIR}/m5b_product_monthly_trend.csv", index=False)
print(f"  ✓ m5b_product_monthly_trend.csv — {len(m5b)} rows")

# ─────────────────────────────────────────────────────────────
# MODULE 6: PROMOTIONAL RESPONSE ANALYSIS
# Which channel drives the most conversions? (ZS specialty)
# ─────────────────────────────────────────────────────────────
print("\nMODULE 6: Promotional Response Analysis...")

q6 = """
WITH channel_perf AS (
    SELECT
        channel,
        product_promoted,
        territory_id,
        COUNT(*)                            AS total_interactions,
        SUM(CAST(converted AS INTEGER))     AS conversions,
        AVG(CAST(converted AS INTEGER))     AS conversion_rate,
        AVG(call_duration_min)              AS avg_duration_min,
        SUM(CAST(samples_dropped AS INTEGER)) AS samples_dropped
    FROM call_logs
    GROUP BY channel, product_promoted, territory_id
),
channel_summary AS (
    SELECT
        channel,
        SUM(total_interactions)  AS total_interactions,
        SUM(conversions)         AS total_conversions,
        ROUND(AVG(conversion_rate) * 100, 1) AS avg_conversion_rate_pct,
        ROUND(AVG(avg_duration_min), 1)      AS avg_duration_min,
        SUM(samples_dropped)     AS total_samples_dropped
    FROM channel_perf
    GROUP BY channel
),
-- Cost-effectiveness: assume cost per interaction
cost AS (
    SELECT channel,
        CASE channel
            WHEN 'In-Person Visit'  THEN 180
            WHEN 'Virtual Detail'   THEN 35
            WHEN 'Conference'       THEN 450
            WHEN 'Email Follow-up'  THEN 8
            WHEN 'Speaker Program'  THEN 280
        END AS cost_per_interaction
    FROM (SELECT DISTINCT channel FROM call_logs)
)
SELECT
    cs.*,
    c.cost_per_interaction,
    ROUND(cs.total_interactions * c.cost_per_interaction, 0)          AS total_channel_cost,
    ROUND(c.cost_per_interaction / NULLIF(cs.avg_conversion_rate_pct / 100, 0), 0) AS cost_per_conversion,
    RANK() OVER (ORDER BY cs.avg_conversion_rate_pct DESC)            AS conversion_rank,
    RANK() OVER (ORDER BY
        c.cost_per_interaction / NULLIF(cs.avg_conversion_rate_pct / 100, 0))      AS roi_rank
FROM channel_summary cs
JOIN cost c USING (channel)
ORDER BY roi_rank
"""

m6 = con.execute(q6).df()
m6.to_csv(f"{OUTPUT_DIR}/m6_promotional_response.csv", index=False)
print(f"  ✓ m6_promotional_response.csv — {len(m6)} rows")
print(m6[['channel','avg_conversion_rate_pct','cost_per_conversion','roi_rank']].to_string(index=False))

# ─────────────────────────────────────────────────────────────
# BONUS: EXECUTIVE KPI SUMMARY TABLE (for Tableau KPI cards)
# ─────────────────────────────────────────────────────────────
print("\nGenerating Executive KPI Summary...")

q_kpi = """
SELECT
    ROUND(SUM(revenue_usd), 0)                                          AS total_revenue_2024,
    ROUND(SUM(CASE WHEN year=2023 THEN revenue_usd END), 0)             AS total_revenue_2023,
    ROUND((SUM(CASE WHEN year=2024 THEN revenue_usd END) -
           SUM(CASE WHEN year=2023 THEN revenue_usd END)) /
          NULLIF(SUM(CASE WHEN year=2023 THEN revenue_usd END),0)*100, 1) AS revenue_growth_pct,
    COUNT(DISTINCT CASE WHEN year=2024 THEN territory_id END)            AS active_territories,
    COUNT(DISTINCT CASE WHEN year=2024 THEN rep_id END)                  AS active_reps,
    ROUND(SUM(CASE WHEN year=2024 THEN revenue_usd END) /
          NULLIF(COUNT(DISTINCT CASE WHEN year=2024 THEN rep_id END), 0), 0) AS revenue_per_rep
FROM sales
"""

kpi = con.execute(q_kpi).df()

whitespace_opp = m2[m2['whitespace_quadrant'] == 'Whitespace']['opportunity_gap_usd'].sum()
critical_gap_rev = m4[m4['coverage_status'] == 'Critical Gap']['estimated_monthly_revenue_potential'].sum() * 12

kpi['total_whitespace_opportunity'] = round(whitespace_opp, 0)
kpi['annual_revenue_at_risk_critical_gaps'] = round(critical_gap_rev, 0)
kpi['whitespace_territories'] = len(m2[m2['whitespace_quadrant'] == 'Whitespace'])
kpi['critical_gap_hcps'] = len(m4[m4['coverage_status'] == 'Critical Gap'])

kpi.to_csv(f"{OUTPUT_DIR}/kpi_summary.csv", index=False)

print("\n" + "="*60)
print("ALL MODULES COMPLETE")
print("="*60)
for k, v in kpi.iloc[0].items():
    print(f"  {k:<45} {v:>15,.0f}")

print(f"\n  Output files in: {OUTPUT_DIR}/")
files = os.listdir(OUTPUT_DIR)
for f in sorted(files):
    size = os.path.getsize(f"{OUTPUT_DIR}/{f}")
    print(f"    {f:<45} {size/1024:>6.1f} KB")
