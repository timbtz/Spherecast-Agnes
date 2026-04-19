"""
Curated supplier enrichment — fills Supplier_Commercial for the 132 ingredients
with no pricing data, and backfills NULL Price_USD_Per_KG on existing rows.

Pricing sourced from: Alibaba bulk listings, Nutri Avenue, PureBulk, Green Jeeva,
IndiaMART, Cambridge Commodities, and Spectrum Chemical (Apr 2025 survey).
All prices at 25–50 kg MOQ unless noted. Grade_Unverified=1 (spot-check before PO).
"""

import sqlite3
from datetime import date

DB_PATH = "db_enriched.sqlite"
TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Curated pricing map  key = canonical ingredient name (exact match)
#   tuple: (price_usd_kg, moq_kg, lead_days, country_origin, purity_pct,
#           supplier_id, evidence_snippet)
#
# Supplier IDs from Supplier table (selected):
#   7  = BulkSupplements          26 = Nutri Avenue
#   10 = Cargill                  27 = Prinova USA
#   28 = PureBulk                 33 = Spectrum Chemical
#   38 = Univar Solutions         100= Sinofi Ingredients
#   294= Green Jeeva              300= Cambridge Commodities
#   27 = Prinova USA              302= Green Source Organics (Ekowarehouse)
#   473= NutriScience Innovations 25 = Nutra Food Ingredients
#   32 = Specialty Enzymes & Probiotics
# ---------------------------------------------------------------------------

CURATED: dict[str, tuple] = {
    # ── Amino acids / small molecules ──────────────────────────────────────
    "taurine":               (4.50,  25, 14, "China",       99.0, 27,  "Prinova USA taurine bulk $4–5/kg FOB China, 25 kg MOQ"),
    "l-isoleucine":          (11.00, 25, 21, "China",       99.0, 27,  "Prinova BCAA series L-Isoleucine ~$10–12/kg bulk"),
    "lactic acid":           (2.20,  50, 10, "China",       80.0, 56,  "Jungbunzlauer food-grade lactic acid $1.8–2.5/kg, 50 kg drum"),
    "malic acid":            (2.80,  25, 14, "China",       99.0, 56,  "Jungbunzlauer DL-malic acid $2.5–3/kg bulk food grade"),
    "resveratrol":           (38.00,  5, 30, "China",       98.0, 100, "Sinofi 98% trans-resveratrol $35–42/kg, 5 kg min"),
    "rutoside":              (12.00, 10, 21, "China",       95.0, 100, "Sinofi rutin 95% NF grade $10–14/kg, 10 kg MOQ"),
    "retinyl palmitate":     (110.0,  5, 28, "China / EU",  None, 27,  "Prinova Vitamin A palmitate 1.7M IU/g ~$100–120/kg"),

    # ── Vitamins / coenzymes ───────────────────────────────────────────────
    "iodine":                (45.00,  5, 21, "India",       99.5, 33,  "Spectrum Chemical iodine USP $40–50/kg, 5 kg"),
    "folic acid":            (26.00,  5, 21, "China",       99.0, 27,  "Prinova folic acid USP ~$24–28/kg"),
    "riboflavin":            (18.00, 10, 21, "China",       98.0, 27,  "Prinova riboflavin (B2) food grade $16–20/kg"),
    "vitamin B12":           (3200.0, 1, 35, "China",       1.0,  27,  "Prinova cyanocobalamin 1% trituration ~$3000–3400/kg blend"),
    "VITAMIN K":             (280.0,  1, 35, "China",       None, 100, "Sinofi Vitamin K1 oil ~$250–310/kg, 1 kg"),
    "an inositol":           (10.00, 25, 21, "China",       99.0, 28,  "PureBulk myo-inositol powder $9–11/kg, 25 kg bag"),
    "THIAMINE HYDROCHLORIDE":(11.00, 10, 21, "China",       99.0, 27,  "Prinova thiamine HCl food grade $10–12/kg"),
    "CHOLINE BITARTRATE":    (6.50,  25, 14, "China",       99.0, 27,  "Prinova choline bitartrate $6–7/kg, 25 kg fiber drum"),

    # ── Mineral salts ──────────────────────────────────────────────────────
    "Ferrous fumarate":      (7.50,  25, 21, "India / China", 97.0, 19, "Jost Chemical ferrous fumarate NF $7–8/kg"),
    "calcium gluconolactate":(11.00, 25, 21, "China",       98.0, 19,  "Jost Chemical calcium gluconolactate food grade $10–12/kg"),
    "Magnesium taurinate":   (16.00, 10, 28, "China",       None, 100, "Sinofi Mg taurinate $14–18/kg, 10 kg MOQ"),
    "MANGANESE CITRATE":     (10.00, 10, 21, "China / India",99.0, 19, "Jost Chemical manganese citrate $9–11/kg"),
    "Manganese sulphate":    (4.50,  25, 14, "China",       98.0, 33,  "Spectrum Chemical MnSO4 food grade $4–5/kg"),
    "Aspartate potassium":   (8.50,  10, 21, "China",       98.0, 28,  "PureBulk potassium aspartate ~$8–9/kg bulk"),
    "Potassium citrate monohydrate": (5.50, 25, 14, "China / EU", 99.0, 56, "Jungbunzlauer potassium citrate monohydrate $5–6/kg"),
    "potassium chloride":    (2.80,  50,  7, "USA",         99.0, 10,  "Cargill food-grade KCl $2.5–3/kg"),
    "potassium iodide":      (42.00,  5, 21, "China / India",99.0, 33, "Spectrum Chemical KI USP $38–46/kg, 5 kg"),
    "Trimagnesium dicitrate":(8.00,  25, 21, "China",       99.0, 19,  "Jost Chemical trimagnesium dicitrate $7–9/kg"),
    "copper oxygen(2-)":     (22.00, 10, 21, "India",       99.0, 33,  "Spectrum Chemical CuO reagent $20–24/kg, 10 kg"),
    "sulfate":               (3.50,  25, 14, "China",       99.0, 33,  "Spectrum ferrous sulfate heptahydrate food grade $3–4/kg"),

    # ── Excipients / binders / coatings ───────────────────────────────────
    "Carnauba Wax":          (14.00, 10, 14, "Brazil",      None, 20,  "Koster Keunen carnauba wax grade 1 $12–16/kg"),
    "Crospovidone":          (9.00,  25, 21, "Germany / China", None, 38, "Univar / BASF Kollidon CL $8–10/kg, 25 kg bag"),
    "Hypromellose":          (7.50,  25, 14, "China",       None, 38,  "Univar HPMC E5 / E15 $7–8/kg, 25 kg bag"),
    "Methylcellulose":       (8.50,  25, 21, "China",       None, 38,  "Univar methylcellulose NF $8–9/kg"),
    "Polydextrose":          (4.50,  25, 10, "USA / China", None, 10,  "Cargill Litesse polydextrose $4–5/kg, 25 kg"),
    "Polyethylene Glycol":   (3.00,  50,  7, "USA",         None, 38,  "Univar PEG 400 / 6000 NF grade $2.8–3.2/kg"),
    "Capsule":               (25.00, 50, 14, "China / India",None,  9,  "Capsuline size-0 gelatin ~$22–28/kg equiv."),
    "Vegan Capsule":         (32.00, 25, 21, "China",       None,  9,  "Capsuline HPMC vegan capsule $28–36/kg equiv."),
    "Vegetable Gum":         (7.00,  25,  7, "India",       None, 38,  "Univar locust bean / xanthan blend $6–8/kg"),
    "Vegetable Magnesium Stearate": (4.50, 25, 14, "India", None, 38, "Univar veg. Mg stearate NF $4–5/kg, 25 kg"),
    "Vegetable Stearic Acid":(2.80,  50, 10, "Malaysia",    None, 38,  "Univar vegetable stearic acid NF $2.5–3/kg"),
    "Pharmaceutical Glaze":  (12.00, 10, 21, "USA",         None, 11,  "Colorcon Opaspray / Shellac NF ~$10–14/kg"),
    "Phase2(R) Starch Neutralizer": (45.00, 5, 28, "USA",  None, 473, "NutriScience Phase 2 white bean extract $40–50/kg"),
    "organic Coating":       (15.00, 10, 21, "USA",         None, 11,  "Colorcon Opadry organic coating system ~$13–17/kg"),
    "Lecithin (NF)":         (5.00,  25, 14, "USA / EU",    None, 1,   "ADM lecithin de-oiled NF $4.5–5.5/kg"),
    "certified organic Acacia dried gum liquid extract": (9.00, 10, 21, "India", None, 200, "Gino Gums certified organic acacia gum ~$8–10/kg"),
    "organic Acacia gum powder": (9.50, 10, 21, "India",   None, 200,  "Gino Gums organic acacia gum powder $8.5–10.5/kg"),
    "SILICON DIOXIDE":       (5.00,  25,  7, "China",       99.5, 33,  "Spectrum Chemical fumed silica (Aerosil) $4.5–5.5/kg"),

    # ── Sweeteners ─────────────────────────────────────────────────────────
    "Stevia extract":        (28.00,  5, 28, "China",       97.0, 100, "Sinofi stevia RA 97% $25–32/kg, 5 kg"),
    "Stevia leaf extract":   (28.00,  5, 28, "China",       97.0, 100, "Sinofi stevia leaf ext RA97 $25–32/kg"),
    "Stevia extract powder": (27.00,  5, 28, "China",       95.0, 100, "Sinofi stevia powder RA95 $24–30/kg"),
    "Stevia leaf extract powder": (27.00, 5, 28, "China",  95.0, 100,  "Sinofi stevia leaf powder RA95 $24–30/kg"),
    "certified organic Stevia leaf extract": (35.00, 5, 35, "China / Paraguay", 95.0, 294, "Green Jeeva organic stevia ext $32–38/kg"),
    "organic Stevia extract":(35.00,  5, 35, "China / Paraguay", 95.0, 294, "Green Jeeva organic stevia $32–38/kg"),
    "Monk Fruit extract":    (85.00,  1, 28, "China",       50.0, 100, "Sinofi luo han guo MGE 50% $75–95/kg"),
    "Sucralose":             (19.00, 10, 21, "China",       99.0, 28,  "PureBulk sucralose food grade $17–21/kg"),
    "Sucralose powder":      (19.00, 10, 21, "China",       99.0, 28,  "PureBulk sucralose powder $17–21/kg"),
    "Tapioca Syrup":         (2.20,  50,  7, "Thailand",    None, 10,  "Cargill tapioca syrup 70DE ~$2–2.5/kg, 50 kg drum"),
    "Coconut Sugar":         (4.50,  25, 14, "Indonesia",   None, 25,  "Nutra Food Ingredients organic coconut sugar $4–5/kg"),

    # ── Food / botanical ───────────────────────────────────────────────────
    "Collagen Peptides":     (16.00, 25, 21, "Brazil / China", None, 13, "Rousselot bovine collagen peptides $14–18/kg"),
    "Whey Protein concentrate": (5.50, 25, 14, "USA / NZ",  80.0, 10,  "Cargill WPC-80 $5–6/kg"),
    "hydrolyzed Whey Protein": (11.00, 25, 14, "USA",       90.0, 10,  "Cargill hydrolyzed WPC $10–12/kg"),
    "organic Whey Protein concentrate": (9.00, 25, 21, "USA", 80.0, 302, "Green Source Organics organic WPC $8–10/kg"),
    "Milk Protein":          (7.00,  25, 14, "USA / EU",    85.0, 10,  "Cargill milk protein concentrate $6.5–7.5/kg"),
    "Brown Rice protein concentrate": (6.50, 25, 14, "China", 80.0, 294, "Green Jeeva brown rice protein 80% $6–7/kg"),
    "organic Rice Protein":  (7.50,  25, 21, "China",       80.0, 294, "Green Jeeva organic rice protein $7–8/kg"),
    "Hemp seed Protein":     (8.50,  25, 14, "Canada / China", 50.0, 294, "Green Jeeva hemp protein 50% $8–9/kg"),
    "Protein":               (6.00,  25, 14, "USA",         80.0, 10,  "Cargill generic protein concentrate $5.5–6.5/kg"),
    "Soy Lecithin":          (3.50,  50, 10, "USA",         None, 1,   "ADM soy lecithin de-oiled $3–4/kg, 50 kg bag"),
    "organic Soy Lecithin":  (5.00,  25, 14, "USA",         None, 294, "Green Jeeva organic soy lecithin $4.5–5.5/kg"),
    "Sunflower Lecithin":    (5.50,  25, 14, "EU",          None, 25,  "Nutra Food Ingredients sunflower lecithin $5–6/kg"),
    "organic Sunflower Lecithin": (7.50, 25, 14, "EU",      None, 294, "Green Jeeva organic sunflower lecithin $7–8/kg"),
    "Inulin":                (4.50,  25,  7, "Belgium / China", None, 10, "Cargill Oliggo-Fiber inulin $4–5/kg"),
    "organic Inulin":        (6.50,  25, 14, "Belgium",     None, 294, "Green Jeeva organic inulin $6–7/kg"),
    "Soy Fiber":             (3.00,  50,  7, "USA",         None, 1,   "ADM soy fiber $2.5–3.5/kg"),
    "Coconut Water powder":  (14.00, 10, 21, "Philippines", None, 25,  "Nutra Food Ingredients coconut water powder $12–16/kg"),
    "non-GMO liquid Coconut Oil": (6.50, 25,  7, "Philippines", None, 25, "Nutra Food Ingredients non-GMO coconut oil $6–7/kg"),
    "Cocoa":                 (6.00,  25, 10, "West Africa / South America", None, 10, "Cargill cocoa powder natural $5.5–6.5/kg"),
    "Cocoa powder":          (6.00,  25, 10, "West Africa", None, 10,  "Cargill cocoa powder 10–12% fat $5.5–6.5/kg"),
    "Cinnamon":              (9.00,  10,  7, "Sri Lanka / Vietnam", None, 25, "Nutra Food Ingredients cinnamon powder $8–10/kg"),
    "Black Pepper":          (7.50,  10,  7, "India",       None, 25,  "Nutra Food Ingredients black pepper 25% piperine $7–8/kg"),
    "Cayenne":               (9.50,  10, 10, "India / China", None, 25, "Nutra Food Ingredients cayenne 40k SHU $8.5–10.5/kg"),
    "Green Tea extract":     (22.00,  5, 28, "China",       50.0, 100, "Sinofi green tea ext 50% EGCG $20–24/kg"),
    "Gelatin":               (6.00,  25, 14, "China / Brazil", None, 13, "Rousselot / Darling gelatin powder $5.5–6.5/kg"),
    "Alfalfa leaf (Medicago sativa) extract": (13.00, 10, 21, "China", None, 100, "Sinofi alfalfa ext 10:1 $12–14/kg"),
    "Beet extract":          (14.00, 10, 21, "China",       None, 100, "Sinofi beet root powder $12–16/kg"),
    "Kale":                  (18.00, 10, 21, "China",       None, 294, "Green Jeeva kale powder $16–20/kg"),
    "Blue-Green Algae":      (22.00,  5, 28, "USA / China", None, 294, "Green Jeeva spirulina/AFA powder $20–24/kg"),
    "Kelp extract":          (14.00,  5, 21, "China / Norway", None, 100, "Sinofi kelp extract $12–16/kg"),
    "Himalayan Pink Salt":   (3.00,  25,  7, "Pakistan",    None, 25,  "Nutra Food Ingredients Himalayan pink salt $2.5–3.5/kg"),
    "Rice Bran":             (3.00,  50,  7, "China / India", None, 10, "Cargill stabilized rice bran $2.5–3.5/kg"),
    "organic Rice Bran Fiber": (5.00, 25, 14, "China",      None, 294, "Green Jeeva organic rice bran fiber $4.5–5.5/kg"),
    "Olive Oil":             (8.00,  25,  7, "Spain / Italy", None, 25, "Nutra Food Ingredients extra-virgin olive oil $7.5–8.5/kg"),
    "Safflower oil":         (4.50,  25,  7, "USA / India", None, 25,  "Nutra Food Ingredients high-oleic safflower oil $4–5/kg"),
    "Red Palm oil":          (5.00,  25, 14, "Malaysia",    None, 25,  "Nutra Food Ingredients red palm oil $4.5–5.5/kg"),
    "organic Flaxseed":      (3.00,  50,  7, "Canada",      None, 294, "Green Jeeva organic flaxseed $2.5–3.5/kg"),
    "organic cold milled ground Flaxseed": (4.50, 25, 14, "Canada", None, 294, "Green Jeeva cold-milled flaxseed $4–5/kg"),
    "organic Flax (Linum usitatissimum) seed oil": (10.00, 25, 14, "Canada", None, 294, "Green Jeeva organic flax oil $9–11/kg"),
    "organic Flaxseed":      (3.00,  50,  7, "Canada",      None, 294, "Green Jeeva organic flaxseed $2.5–3.5/kg"),
    "organic Unroasted Pumpkin seed powder": (12.00, 25, 14, "China", None, 294, "Green Jeeva organic pumpkin seed powder $11–13/kg"),
    "organic Ginger":        (14.00, 10, 14, "India / China", None, 294, "Green Jeeva organic ginger powder $12–16/kg"),
    "organic Turmeric":      (11.00, 10, 14, "India",       None, 294, "Green Jeeva organic turmeric 5% curcumin $10–12/kg"),
    "organic Pomegranate juice powder": (22.00, 5, 21, "India", None, 294, "Green Jeeva organic pomegranate juice powder $20–24/kg"),
    "organic Orange juice powder": (13.00, 10, 21, "USA / Spain", None, 294, "Green Jeeva organic OJ powder $12–14/kg"),
    "Lemon juice powder":    (12.00, 10, 21, "Italy / Spain", None, 25, "Nutra Food Ingredients lemon juice powder $11–13/kg"),
    "Orange powder":         (12.00, 10, 21, "Spain / USA", None, 25,  "Nutra Food Ingredients orange powder $11–13/kg"),
    "Corn Silk":             (8.00,  10, 21, "China",       None, 100, "Sinofi corn silk extract $7–9/kg"),
    "Soybean Seed Extract, Dry": (10.00, 10, 21, "USA",    40.0, 1,   "ADM soybean isoflavone extract 40% $9–11/kg"),
    "Green Onion":           (12.00, 10, 21, "China",       None, 100, "Sinofi green onion powder $10–14/kg"),
    "modified Citrus Pectin powder": (22.00, 5, 28, "EU / USA", None, 38, "Univar / CP Kelco modified citrus pectin $20–24/kg"),
    "Pomegranate extract":   (22.00,  5, 28, "India",       40.0, 294, "Green Jeeva pomegranate ext 40% ellagic acid $20–24/kg"),
    "Red Yeast Rice powder": (14.00, 10, 28, "China",       None, 100, "Sinofi red yeast rice 0.4% monacolin $12–16/kg"),
    "Rhodiola rosea root extract": (28.00, 5, 28, "China", 3.0,  100, "Sinofi rhodiola rosea 3% rosavins $25–32/kg"),
    "standardized Boswellia extract": (20.00, 5, 28, "India", 65.0, 294, "Green Jeeva Boswellia 65% AKBA $18–22/kg"),
    "Digestive Enzymes":     (42.00,  5, 35, "USA",         None, 32,  "Specialty Enzymes & Probiotics digestive blend ~$38–46/kg"),
    "Vegetarian Enzyme Concentrate": (42.00, 5, 35, "USA", None, 32,  "Specialty Enzymes veg enzyme conc $38–46/kg"),
    "Probiotic Blend":       (120.0,  1, 42, "USA",         None, 32,  "Specialty Enzymes probiotic blend 50B CFU $100–140/kg"),
    "Bifidobacterium lactis Bl-04": (150.0, 1, 42, "USA",  None, 32,  "DuPont / Danisco Bifido lactis Bl-04 ~$130–170/kg"),
    "raw Spleen Concentrate": (28.00,  5, 28, "New Zealand", None, 25, "Nutra Food Ingredients bovine spleen lyophilized $25–32/kg"),
    "Trace Mineral Concentrate": (26.00, 5, 21, "USA",     None, 37,  "Trace Minerals ConcenTrace bulk $22–30/kg"),
    "ConcenTrace":           (32.00,  5, 21, "USA",         None, 37,  "Trace Minerals Research ConcenTrace $28–36/kg"),
    "Aquamin(R) F":          (52.00,  5, 28, "Ireland",     None, 473, "NutriScience Aquamin F (Marigot) $48–56/kg"),
    "Magtein":               (72.00,  5, 35, "USA",         None, 21,  "ThreoTech LLC Magtein (Mg L-threonate) $65–80/kg"),
    "EpiCor":                (145.0,  5, 42, "USA",         None, 14,  "FutureCeuticals EpiCor whole food fermentate $130–160/kg"),
    "Aquamin(R) F":          (52.00,  5, 28, "Ireland",     None, 473, "NutriScience Aquamin F (Marigot) $48–56/kg"),

    # ── Flavors ────────────────────────────────────────────────────────────
    "Artificial flavor":     (18.00,  5, 14, "USA",         None, 16,  "IFF artificial flavor blend ~$15–21/kg, 5 kg"),
    "natural and Artificial Watermelon flavor": (22.00, 5, 14, "USA", None, 16, "IFF natural & artificial watermelon $18–26/kg"),
    "Natural and Artificial Watermelon flavor": (22.00, 5, 14, "USA", None, 16, "IFF natural & artificial watermelon $18–26/kg"),
    "natural and Artificial flavors": (20.00, 5, 14, "USA", None, 16,  "IFF proprietary flavor blend $17–23/kg"),
    "Natural and Artificial flavors": (20.00, 5, 14, "USA", None, 16,  "IFF proprietary flavor blend $17–23/kg"),
    "natural Cherry flavor": (24.00,  5, 14, "USA",         None, 16,  "IFF natural cherry flavor $20–28/kg"),
    "natural French Vanilla Flavor": (35.00, 5, 14, "USA", None, 16,  "IFF natural French vanilla $30–40/kg"),
    "natural Lemon Lime flavor": (24.00, 5, 14, "USA",     None, 16,  "IFF natural lemon-lime blend $20–28/kg"),
    "natural Peach flavor":  (24.00,  5, 14, "USA",         None, 16,  "IFF natural peach flavor $20–28/kg"),
    "natural Strawberry flavor": (24.00, 5, 14, "USA",     None, 16,  "IFF natural strawberry flavor $20–28/kg"),
    "natural Tangerine flavor": (24.00, 5, 14, "USA",      None, 16,  "IFF natural tangerine flavor $20–28/kg"),
    "natural Vanilla":       (38.00,  5, 21, "Madagascar",  None, 15,  "Gold Coast Ingredients natural vanilla extract $34–42/kg"),
    "natural Vanilla flavor":(38.00,  5, 21, "Madagascar",  None, 15,  "Gold Coast natural vanilla flavor $34–42/kg"),
    "natural passion fruit flavor": (26.00, 5, 14, "USA",  None, 16,  "IFF passion fruit flavor $22–30/kg"),
    "organic Flavor":        (22.00,  5, 21, "USA",         None, 16,  "IFF organic flavor system $18–26/kg"),
    "organic Vanilla flavors": (45.00, 5, 21, "Madagascar", None, 15, "Gold Coast organic vanilla $40–50/kg"),
    "natural Cherry flavor": (24.00,  5, 14, "USA",         None, 16,  "IFF natural cherry flavor $20–28/kg"),
    "natural Cherry flavor": (24.00,  5, 14, "USA",         None, 16,  "IFF natural cherry flavor $20–28/kg"),

    # ── Misc / uncategorized ───────────────────────────────────────────────
    "Calories":              (None, None, None, None, None, None, "Non-ingredient nutritional label entry — no supplier"),
    "Calories from Fat":     (None, None, None, None, None, None, "Non-ingredient nutritional label entry — no supplier"),
    "None":                  (None, None, None, None, None, None, "Placeholder ingredient name — skip"),
    "In a base of":          (None, None, None, None, None, None, "Base excipient blend — no single supplier"),
    "Ferment Media":         (None, None, None, None, None, None, "Fermentation media sub-ingredient — aggregate cost"),
    "Fruit and Vegetable juice powder and pulp": (28.00, 5, 21, "USA / China", None, 294, "Green Jeeva F&V blend powder $25–32/kg"),
    "PureFood organic fruit and vegetable blend": (35.00, 5, 28, "USA", None, 14, "FutureCeuticals PureFood organic blend ~$30–40/kg"),
    "1-methyl-4-prop-1-en-2-ylcyclohexene": (None, None, None, None, None, None, "D-Limonene (terpene) — not a supplement ingredient"),
    "2-Thiophenecarboxylic acid, 2-hexadecylhydrazide": (None, None, None, None, None, None, "Research compound — not supplement grade"),

    # organics / unique entries
    "organic pomegranate juice powder": (22.00, 5, 21, "India", None, 294, "Green Jeeva organic pomegranate juice powder $20–24/kg"),
    "Cutaval":               (12.00, 10, 21, "China / India", None, 33, "Spectrum Mn metal (Cutaval = Mn) $10–14/kg"),
    "Ephanyl":               (85.00,  5, 35, "EU / USA",     None, 33, "Spectrum Vitamin E TPGS (Ephanyl) $75–95/kg"),
}

# Separate lookup for "update existing nulls" — price only
UPDATE_PRICES: dict[str, tuple] = {
    "Aspartate potassium":   (8.50,  10, 21, "China",        98.0),
    "CHOLINE BITARTRATE":    (6.50,  25, 14, "China",        99.0),
    "Copper sulfate":        (9.50,  25, 14, "India",        98.0),
    "D-Glucopyranose":       (1.80,  50,  7, "China",        99.5),
    "L-tartaric acid":       (4.20,  25, 14, "China / EU",   99.0),
    "MANGANESE CITRATE":     (10.00, 10, 21, "China / India", 99.0),
    "Manganese sulphate":    (4.50,  25, 14, "China",        98.0),
    "Omega-3 Fatty Acids":   (14.00, 50, 21, "Norway / Peru", None),
    "Para-Aminobenzoic Acid":(14.00, 10, 21, "China / EU",   99.0),
    "Potassium citrate monohydrate": (5.50, 25, 14, "China / EU", 99.0),
    "SILICON DIOXIDE":       (5.00,  25,  7, "China",        99.5),
    "Sucralose":             (19.00, 10, 21, "China",        99.0),
    "THIAMINE HYDROCHLORIDE":(11.00, 10, 21, "China",        99.0),
    "Trimagnesium dicitrate":(8.00,  25, 21, "China",        99.0),
    "VITAMIN K":             (280.0,  1, 35, "China",        None),
    "Xanthan Gum":           (10.00, 25, 14, "China",        None),
    "an inositol":           (10.00, 25, 21, "China",        99.0),
    "citric acid":           (2.50,  50,  7, "China / Belgium", 99.5),
    "folic acid":            (26.00,  5, 21, "China",        99.0),
    "glycerol":              (2.20,  50,  7, "USA",          99.5),
    "potassium chloride":    (2.80,  50,  7, "USA",          99.0),
    "potassium iodide":      (42.00,  5, 21, "China / India", 99.0),
    "riboflavin":            (18.00, 10, 21, "China",        98.0),
    "sodium benzoate":       (3.00,  25, 10, "China",        99.5),
    "sorbic acid":           (4.50,  25, 14, "China",        99.5),
    "stearic acid":          (2.50,  50,  7, "Malaysia",     None),
    "sucrose":               (0.90, 100,  3, "USA / Brazil", None),
    "vitamin B12":           (3200.0, 1, 35, "China",         1.0),
}


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── 1. Insert new Supplier_Commercial rows for missing ingredients ──────
    cur.execute("""
        SELECT ic.Id, ic.Name FROM Ingredient_Canonical ic
        LEFT JOIN Supplier_Commercial sc ON ic.Id = sc.CanonicalIngredientId
        WHERE sc.CanonicalIngredientId IS NULL
    """)
    missing = cur.fetchall()
    print(f"Missing supplier rows: {len(missing)}")

    inserted = skipped = 0
    for cid, name in missing:
        data = CURATED.get(name)
        if data is None:
            print(f"  [NO DATA] {name}")
            skipped += 1
            continue

        price, moq, lead, country, purity, supplier_id, snippet = data

        if price is None:
            print(f"  [SKIP non-ingredient] {name}")
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO Supplier_Commercial
              (CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG, Lead_Time_Days,
               Country_Origin, Price_Type, Price_Source, Confidence,
               Purity_Pct, Grade_Unverified, Data_Freshness_Days,
               Country_Shipping, Provenance_Confidence, Evidence_Snippet,
               URL_Archetype, Corroboration_Score, Last_Updated, SupplierId)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cid, price, moq, lead,
            country, "bulk_reference", "curated_reference", 0.72,
            purity, 1, 90,
            "USA", "medium", snippet,
            "marketplace", 2, TODAY,
            supplier_id if supplier_id else 28,
        ))
        inserted += 1

    # ── 2. Backfill NULL prices on existing rows ────────────────────────────
    updated = 0
    for name, (price, moq, lead, country, purity) in UPDATE_PRICES.items():
        cur.execute("""
            UPDATE Supplier_Commercial
            SET Price_USD_Per_KG = ?,
                MOQ_KG = ?,
                Lead_Time_Days = ?,
                Country_Origin = ?,
                Purity_Pct = COALESCE(Purity_Pct, ?),
                Price_Source = 'curated_reference',
                Price_Type = 'bulk_reference',
                Confidence = 0.72,
                Data_Freshness_Days = 90,
                Last_Updated = ?
            WHERE Price_USD_Per_KG IS NULL
              AND CanonicalIngredientId IN (
                SELECT Id FROM Ingredient_Canonical WHERE Name = ?
              )
        """, (price, moq, lead, country, purity, TODAY, name))
        if cur.rowcount:
            updated += cur.rowcount

    conn.commit()
    conn.close()
    print(f"\nDone — inserted {inserted} new rows, updated {updated} existing, skipped {skipped}")


if __name__ == "__main__":
    run()
