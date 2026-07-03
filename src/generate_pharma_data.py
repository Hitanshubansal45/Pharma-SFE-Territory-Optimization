"""
Pharmaceutical Sales Force Effectiveness - Synthetic Dataset Generator
ZS Associates Style Analytics Project
Generates 6 linked tables in a star schema
"""

import pandas as pd
import numpy as np
from faker import Faker
import os
import json

fake = Faker()
np.random.seed(42)
Faker.seed(42)

OUTPUT_DIR = "/home/claude/pharma_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
N_TERRITORIES = 50
N_REPS        = 80
N_HCPS        = 500
N_MONTHS      = 24   # Jan 2023 – Dec 2024
PRODUCTS      = [
    {"product_id": "P001", "name": "Cardivex",   "therapeutic_area": "Cardiology",    "launch_year": 2019, "list_price": 420},
    {"product_id": "P002", "name": "NeuroPrime",  "therapeutic_area": "Neurology",     "launch_year": 2021, "list_price": 680},
    {"product_id": "P003", "name": "OncoClear",   "therapeutic_area": "Oncology",      "launch_year": 2020, "list_price": 1250},
    {"product_id": "P004", "name": "PulmoShield", "therapeutic_area": "Respiratory",   "launch_year": 2018, "list_price": 310},
    {"product_id": "P005", "name": "DiabeCare",   "therapeutic_area": "Endocrinology", "launch_year": 2022, "list_price": 290},
    {"product_id": "P006", "name": "ImmunoBoost", "therapeutic_area": "Immunology",    "launch_year": 2017, "list_price": 890},
]

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Northwest"]

# Product growth rates and market share (for BCG matrix)
PRODUCT_BCG = {
    "P001": {"market_share": 0.28, "market_growth": 0.04},   # Cash Cow
    "P002": {"market_share": 0.18, "market_growth": 0.22},   # Star
    "P003": {"market_share": 0.12, "market_growth": 0.31},   # Star
    "P004": {"market_share": 0.31, "market_growth": 0.02},   # Cash Cow
    "P005": {"market_share": 0.08, "market_growth": 0.18},   # Question Mark
    "P006": {"market_share": 0.05, "market_growth": 0.06},   # Dog
}

# ─────────────────────────────────────────
# TABLE 1: TERRITORIES
# ─────────────────────────────────────────
print("Generating territories...")

territory_ids = [f"T{str(i).zfill(3)}" for i in range(1, N_TERRITORIES + 1)]
regions_assigned = np.random.choice(REGIONS, N_TERRITORIES)

# Market potential index: 1-100 (higher = more prescribers, more opportunity)
market_potential = np.random.beta(2, 2, N_TERRITORIES) * 90 + 10  # range ~10-100

# Urban/rural mix affects potential realization
urban_index = np.clip(np.random.normal(0.6, 0.2, N_TERRITORIES), 0.2, 1.0)

# Competitor intensity (higher = harder market)
competitor_intensity = np.random.uniform(0.3, 0.9, N_TERRITORIES)

territories_df = pd.DataFrame({
    "territory_id":          territory_ids,
    "region":                regions_assigned,
    "state":                 [fake.state_abbr() for _ in range(N_TERRITORIES)],
    "market_potential_index": np.round(market_potential, 1),
    "urban_index":           np.round(urban_index, 2),
    "competitor_intensity":  np.round(competitor_intensity, 2),
    "num_target_hcps":       np.random.randint(80, 300, N_TERRITORIES),
    "population_000s":       np.random.randint(150, 2500, N_TERRITORIES),
})

territories_df.to_csv(f"{OUTPUT_DIR}/territories.csv", index=False)
print(f"  ✓ territories.csv — {len(territories_df)} rows")

# ─────────────────────────────────────────
# TABLE 2: PRODUCTS
# ─────────────────────────────────────────
print("Generating products...")

products_df = pd.DataFrame(PRODUCTS)
for pid, bcg in PRODUCT_BCG.items():
    products_df.loc[products_df["product_id"] == pid, "market_share_pct"]  = bcg["market_share"]
    products_df.loc[products_df["product_id"] == pid, "market_growth_rate"] = bcg["market_growth"]

# BCG classification
def bcg_label(row):
    ms = row["market_share_pct"]
    mg = row["market_growth_rate"]
    if ms >= 0.15 and mg >= 0.10: return "Star"
    if ms >= 0.15 and mg <  0.10: return "Cash Cow"
    if ms <  0.15 and mg >= 0.10: return "Question Mark"
    return "Dog"

products_df["bcg_quadrant"] = products_df.apply(bcg_label, axis=1)
products_df.to_csv(f"{OUTPUT_DIR}/products.csv", index=False)
print(f"  ✓ products.csv — {len(products_df)} rows")

# ─────────────────────────────────────────
# TABLE 3: REPS
# ─────────────────────────────────────────
print("Generating reps...")

rep_ids = [f"R{str(i).zfill(3)}" for i in range(1, N_REPS + 1)]

# Assign reps to territories (some territories have 2 reps)
rep_territories = np.random.choice(territory_ids, N_REPS)

experience = np.random.randint(1, 18, N_REPS)

# Inherent productivity score (hidden ground truth — affects sales)
productivity_score = np.clip(np.random.normal(0.65, 0.2, N_REPS), 0.2, 1.0)

reps_df = pd.DataFrame({
    "rep_id":             rep_ids,
    "rep_name":           [fake.name() for _ in range(N_REPS)],
    "territory_id":       rep_territories,
    "region":             [territories_df.loc[territories_df["territory_id"] == t, "region"].values[0] for t in rep_territories],
    "experience_years":   experience,
    "hire_date":          [fake.date_between(start_date="-18y", end_date="-1y") for _ in range(N_REPS)],
    "education":          np.random.choice(["B.Pharm", "MBA", "B.Sc Life Sciences", "M.Sc Pharmacology"], N_REPS, p=[0.3, 0.25, 0.3, 0.15]),
    "productivity_score": np.round(productivity_score, 2),  # internal metric
})

reps_df.to_csv(f"{OUTPUT_DIR}/reps.csv", index=False)
print(f"  ✓ reps.csv — {len(reps_df)} rows")

# ─────────────────────────────────────────
# TABLE 4: PHYSICIANS (HCPs)
# ─────────────────────────────────────────
print("Generating physicians...")

hcp_ids = [f"H{str(i).zfill(4)}" for i in range(1, N_HCPS + 1)]

# Assign HCPs to territories weighted by num_target_hcps
territory_weights = territories_df["num_target_hcps"] / territories_df["num_target_hcps"].sum()
hcp_territories   = np.random.choice(territory_ids, N_HCPS, p=territory_weights)

specialties = ["Cardiologist", "Neurologist", "Oncologist", "Pulmonologist",
               "Endocrinologist", "Immunologist", "General Practitioner", "Internist"]

# Prescriber tier: A = high volume, B = medium, C = low
prescriber_tiers = np.random.choice(["A", "B", "C"], N_HCPS, p=[0.2, 0.35, 0.45])

# Prescription volume (Rx/month) — correlated with tier
rx_volume = {
    "A": lambda: np.random.randint(40, 120),
    "B": lambda: np.random.randint(15, 45),
    "C": lambda: np.random.randint(2, 18),
}

physicians_df = pd.DataFrame({
    "hcp_id":            hcp_ids,
    "hcp_name":          [f"Dr. {fake.last_name()}" for _ in range(N_HCPS)],
    "territory_id":      hcp_territories,
    "specialty":         np.random.choice(specialties, N_HCPS),
    "prescriber_tier":   prescriber_tiers,
    "monthly_rx_volume": [rx_volume[t]() for t in prescriber_tiers],
    "years_in_practice": np.random.randint(2, 35, N_HCPS),
    "hospital_affiliation": np.random.choice(["Academic", "Community", "Private Practice", "Group Practice"], N_HCPS, p=[0.2, 0.3, 0.35, 0.15]),
    "digital_engagement": np.random.choice(["High", "Medium", "Low"], N_HCPS, p=[0.3, 0.4, 0.3]),
})

physicians_df.to_csv(f"{OUTPUT_DIR}/physicians.csv", index=False)
print(f"  ✓ physicians.csv — {len(physicians_df)} rows")

# ─────────────────────────────────────────
# TABLE 5: SALES (Monthly)
# ─────────────────────────────────────────
print("Generating sales records...")

months = pd.date_range("2023-01-01", periods=N_MONTHS, freq="MS")

sales_records = []
product_ids   = [p["product_id"] for p in PRODUCTS]

for _, rep in reps_df.iterrows():
    territory = territories_df[territories_df["territory_id"] == rep["territory_id"]].iloc[0]
    mpi       = territory["market_potential_index"] / 100
    comp      = 1 - territory["competitor_intensity"]
    prod      = rep["productivity_score"]

    for month in months:
        # Each rep sells 2–4 products per month
        rep_products = np.random.choice(product_ids, size=np.random.randint(2, 5), replace=False)
        for pid in rep_products:
            product = products_df[products_df["product_id"] == pid].iloc[0]
            base    = product["list_price"] * np.random.randint(10, 80)

            # Revenue = base × potential × competition × productivity × seasonal noise
            seasonal = 1 + 0.08 * np.sin(2 * np.pi * month.month / 12)
            trend    = 1 + PRODUCT_BCG[pid]["market_growth"] * (month.year - 2023 + month.month / 12) / 12

            # Deliberately make some high-potential territories UNDERPERFORM (whitespace story)
            if mpi > 0.7 and prod < 0.5:
                perf_factor = np.random.uniform(0.25, 0.45)   # underperforming
            elif mpi < 0.4 and prod > 0.7:
                perf_factor = np.random.uniform(0.55, 0.75)   # oversaturated
            else:
                perf_factor = np.random.uniform(0.45, 0.95)

            revenue = base * mpi * comp * prod * perf_factor * seasonal * trend
            units   = max(1, int(revenue / product["list_price"]))

            sales_records.append({
                "sale_id":       f"S{len(sales_records)+1:06d}",
                "rep_id":        rep["rep_id"],
                "territory_id":  rep["territory_id"],
                "product_id":    pid,
                "month":         month.strftime("%Y-%m-%d"),
                "year":          month.year,
                "month_num":     month.month,
                "units_sold":    units,
                "revenue_usd":   round(revenue, 2),
                "discount_pct":  round(np.random.uniform(0.02, 0.18), 3),
            })

sales_df = pd.DataFrame(sales_records)
sales_df["net_revenue_usd"] = round(sales_df["revenue_usd"] * (1 - sales_df["discount_pct"]), 2)
sales_df.to_csv(f"{OUTPUT_DIR}/sales.csv", index=False)
print(f"  ✓ sales.csv — {len(sales_df)} rows")

# ─────────────────────────────────────────
# TABLE 6: CALL LOGS (Rep → HCP visits)
# ─────────────────────────────────────────
print("Generating call logs...")

call_records = []
call_outcomes = ["Positive - Prescription Written", "Positive - Interest Shown",
                 "Neutral - Information Only", "Negative - No Interest", "Follow-up Scheduled"]
call_outcome_weights = [0.25, 0.20, 0.35, 0.10, 0.10]

promo_channels = ["In-Person Visit", "Virtual Detail", "Conference", "Email Follow-up", "Speaker Program"]

for _, rep in reps_df.iterrows():
    # Get HCPs in same territory
    territory_hcps = physicians_df[physicians_df["territory_id"] == rep["territory_id"]]
    if territory_hcps.empty:
        continue

    # Reps make 8–18 calls/month; productivity affects call rate
    monthly_calls = int(np.clip(rep["productivity_score"] * 20 + np.random.randint(-3, 4), 5, 22))

    for month in months:
        n_calls = monthly_calls + np.random.randint(-2, 3)
        # Bias toward Tier A HCPs but not exclusively
        tier_weights = territory_hcps["prescriber_tier"].map({"A": 0.5, "B": 0.3, "C": 0.2}).values
        tier_weights = tier_weights / tier_weights.sum()

        called_hcps = territory_hcps.sample(
            n=min(n_calls, len(territory_hcps)),
            weights=tier_weights,
            replace=True,
            random_state=None
        )

        for _, hcp in called_hcps.iterrows():
            promoted_product = np.random.choice(product_ids)
            outcome = np.random.choice(call_outcomes, p=call_outcome_weights)

            # Conversion more likely for Tier A HCPs and experienced reps
            converted = (
                outcome.startswith("Positive") and
                np.random.random() < (0.3 + 0.2 * (hcp["prescriber_tier"] == "A") + 0.1 * (rep["experience_years"] > 5))
            )

            call_records.append({
                "call_id":          f"C{len(call_records)+1:07d}",
                "rep_id":           rep["rep_id"],
                "hcp_id":           hcp["hcp_id"],
                "territory_id":     rep["territory_id"],
                "product_promoted": promoted_product,
                "call_date":        fake.date_between_dates(
                                        date_start=month,
                                        date_end=month + pd.offsets.MonthEnd(0)
                                    ),
                "month":            month.strftime("%Y-%m-%d"),
                "year":             month.year,
                "month_num":        month.month,
                "channel":          np.random.choice(promo_channels, p=[0.55, 0.20, 0.08, 0.12, 0.05]),
                "call_outcome":     outcome,
                "converted":        converted,
                "call_duration_min": np.random.randint(5, 45),
                "samples_dropped":  np.random.choice([True, False], p=[0.6, 0.4]),
            })

calls_df = pd.DataFrame(call_records)
calls_df.to_csv(f"{OUTPUT_DIR}/call_logs.csv", index=False)
print(f"  ✓ call_logs.csv — {len(calls_df)} rows")

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
print("\n" + "="*55)
print("DATASET GENERATION COMPLETE")
print("="*55)
summary = {
    "territories": len(territories_df),
    "products":    len(products_df),
    "reps":        len(reps_df),
    "physicians":  len(physicians_df),
    "sales":       len(sales_df),
    "call_logs":   len(calls_df),
    "total_revenue_usd": round(sales_df["revenue_usd"].sum(), 2),
    "date_range":  f"{months[0].strftime('%b %Y')} – {months[-1].strftime('%b %Y')}",
}
for k, v in summary.items():
    print(f"  {k:<25} {v:>15,}" if isinstance(v, (int, float)) else f"  {k:<25} {v}")

with open(f"{OUTPUT_DIR}/dataset_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\n  All files saved to: {OUTPUT_DIR}/")
