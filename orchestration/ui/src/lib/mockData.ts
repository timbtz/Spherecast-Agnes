import type {
  ChatResponse,
  ComplianceProduct,
  DagGraph,
  Ingredient,
  Opportunity,
  PipelineRun,
  Proposal,
  RunDetail,
  RunEvent,
} from "@/types/agnes";

// ---------------------------------------------------------------------------
// Realistic seeded data + DAG simulator. Lets the UI feel alive even when the
// FastAPI backend on localhost:8001 is unreachable from the preview sandbox.
// ---------------------------------------------------------------------------

const ingredientNames: Array<[string, string, string, string, Ingredient["grade"]]> = [
  ["Ascorbic Acid (Vitamin C)", "PQ6CK8PD0R", "50-81-7", "54670067", "supplement"],
  ["Magnesium Citrate", "RHO26O27GG", "3344-18-1", "13136", "supplement"],
  ["Cholecalciferol (Vitamin D3)", "1C6V77QF41", "67-97-0", "5280795", "supplement"],
  ["Cyanocobalamin (B12)", "P6YC3EG204", "68-19-9", "5311498", "supplement"],
  ["Zinc Picolinate", "B16WL5R2BD", "17949-65-4", "131534", "supplement"],
  ["Eicosapentaenoic Acid (EPA)", "AAN7QOV9EA", "10417-94-4", "446284", "supplement"],
  ["Docosahexaenoic Acid (DHA)", "ZAD9OKH9JC", "6217-54-5", "445580", "supplement"],
  ["Curcumin", "IT942ZTH98", "458-37-7", "969516", "supplement"],
  ["Coenzyme Q10", "EJ27X76M46", "303-98-0", "5281915", "supplement"],
  ["L-Theanine", "8021PR16QO", "3081-61-6", "439378", "supplement"],
  ["Microcrystalline Cellulose", "OP1R32D61U", "9004-34-6", "14055602", "excipient"],
  ["Silicon Dioxide", "ETJ7Z6XBU4", "7631-86-9", "24261", "excipient"],
  ["Magnesium Stearate", "70097M6I30", "557-04-0", "11177", "excipient"],
  ["Stevia Rebaudioside A", "I306OB31KX", "58543-16-1", "6918840", "sweetener"],
  ["Natural Orange Flavor", "—", "8028-48-6", "—", "flavor"],
  ["Inulin (Chicory)", "JOS53KCS6S", "9005-80-5", "24763", "food"],
  ["Beta-Carotene", "01YAE03M7J", "7235-40-7", "5280489", "supplement"],
  ["Methylsulfonylmethane (MSM)", "9H4PO4Z4FT", "67-71-0", "6213", "supplement"],
  ["Glucosamine Sulfate", "MUP60K1Y4S", "29031-19-4", "439213", "supplement"],
  ["Hyaluronic Acid", "8I86X66Z16", "9004-61-9", "53477741", "supplement"],
];

const smilesByName: Record<string, string> = {
  "Ascorbic Acid (Vitamin C)": "OCC(O)C1OC(=O)C(O)=C1O",
  "Magnesium Citrate": "[Mg+2].OC(=O)CC(O)(C(=O)[O-])CC(=O)[O-]",
  "Curcumin": "COc1cc(/C=C/C(=O)CC(=O)/C=C/c2ccc(O)c(OC)c2)ccc1O",
  "L-Theanine": "CCNC(=O)CCC(N)C(=O)O",
  "Coenzyme Q10": "COC1=C(OC)C(=O)C(C/C=C(\\C)CC...)=C(C)C1=O",
};

const companies = [
  "NorthPeak Wellness",
  "Atlas Nutritionals",
  "Verda Botanica",
  "Helix Health Co.",
  "Cedar & Crown",
];

const certTypes = ["GlutenFree", "NonGMO", "Vegan", "Organic", "NSF", "Kosher", "Halal"];

function makeOpportunities(): Opportunity[] {
  return ingredientNames.slice(0, 14).map((row, i) => {
    const [name, , , , grade] = row;
    const score = Math.max(0.32, Math.min(0.98, 0.95 - i * 0.045 + (i % 3) * 0.03));
    const companyCount = 5 - (i % 5);
    return {
      id: `opp_${i + 1}`,
      ingredient_id: `ing_${i + 1}`,
      ingredient_name: name,
      grade,
      company_count: Math.max(2, companyCount + (i % 4)),
      consolidation_score: Number(score.toFixed(2)),
      compliance_feasible: i % 5 !== 2,
      proposal_text:
        i < 6
          ? proposalText(name, Math.max(2, companyCount + (i % 4)), score)
          : null,
    };
  });
}

function proposalText(name: string, companyCount: number, score: number): string {
  return `Across the current bill-of-materials, ${name} is sourced from ${companyCount} distinct suppliers serving overlapping SKU lines. Agnes scores this consolidation opportunity at ${(
    score * 100
  ).toFixed(0)}% based on grade equivalence, regulatory parity (USP/FCC), and observed price variance of 14–22% across vendors.

Recommendation: shortlist the two top-performing suppliers (NorthPeak Wellness and Atlas Nutritionals), issue a 12-month volume commitment RFQ, and migrate the remaining SKUs at the next manufacturing cycle. Expected annualised savings: $148K–$220K with no compliance disruption — all candidate suppliers carry NSF, NonGMO, and Kosher certifications validated against the DSLD registry.

Risk flags: one secondary supplier shows a 2024 FDA warning letter (resolved); excluded from the shortlist. Substitution feasibility from the Molport substitution graph is HIGH (4 confirmed alternatives available within ±2% cost band).`;
}

function makeIngredients(): Ingredient[] {
  return ingredientNames.map(([name, unii, cas, cid, grade], i) => ({
    id: `ing_${i + 1}`,
    display_name: name,
    unii: unii === "—" ? null : unii,
    cas: cas === "—" ? null : cas,
    pubchem_cid: cid === "—" ? null : cid,
    grade,
    smiles: smilesByName[name] ?? null,
    substitution_edges: 1 + (i % 6),
  }));
}

function makeCompliance(): ComplianceProduct[] {
  const products: ComplianceProduct[] = [];
  for (let c = 0; c < companies.length; c++) {
    for (let p = 0; p < 4; p++) {
      const idx = c * 4 + p;
      const certifications: Record<string, "certified" | "implied" | "none"> = {};
      certTypes.forEach((ct, ci) => {
        const r = (idx * 7 + ci * 3) % 10;
        certifications[ct] = r < 5 ? "certified" : r < 7 ? "implied" : "none";
      });
      products.push({
        product_id: `prod_${idx + 1}`,
        product_name: `${["Daily", "Active", "Pure", "Restore"][p]} ${["Multi", "Omega", "Immunity", "Joint"][p]}`,
        company: companies[c],
        off_market: idx % 11 === 0,
        certifications,
      });
    }
  }
  return products;
}

function makeProposals(): Proposal[] {
  return makeOpportunities()
    .filter((o) => o.proposal_text)
    .map((o, i) => ({
      id: `prop_${i + 1}`,
      ingredient_id: o.ingredient_id,
      ingredient_name: o.ingredient_name,
      grade: o.grade,
      consolidation_score: o.consolidation_score,
      company_count: o.company_count,
      compliance_feasible: o.compliance_feasible,
      proposal_text: o.proposal_text!,
      created_at: new Date(Date.now() - i * 1000 * 60 * 47).toISOString(),
    }));
}

function makeRuns(): PipelineRun[] {
  const pipelines = [
    "proactive_consolidation",
    "supplier_fallout",
    "price_audit",
    "substitution_discovery",
    "new_ingredient_research",
  ];
  return Array.from({ length: 8 }, (_, i) => {
    const status: PipelineRun["status"] = i === 0 ? "completed" : i === 3 ? "failed" : "completed";
    const started = new Date(Date.now() - (i + 1) * 1000 * 60 * 12);
    return {
      run_id: `run_${(i + 100).toString(16)}-${Math.random().toString(16).slice(2, 6)}`,
      pipeline: pipelines[i % pipelines.length],
      status,
      started_at: started.toISOString(),
      ended_at: new Date(started.getTime() + 4500 + i * 230).toISOString(),
      duration_ms: 4500 + i * 230,
    };
  });
}

const PIPELINE_GRAPHS: Record<string, DagGraph> = {
  proactive_consolidation: {
    name: "proactive_consolidation",
    trigger: "manual",
    layers: [
      ["load-bom"],
      ["scan-opportunities", "load-compliance"],
      ["score-consolidation", "check-substitutions"],
      ["compliance-gate"],
      ["generate-proposal"],
      ["persist-proposal"],
    ],
    nodes: [
      { id: "load-bom", type: "tool", depends_on: [] },
      { id: "scan-opportunities", type: "agent", depends_on: ["load-bom"] },
      { id: "load-compliance", type: "tool", depends_on: ["load-bom"] },
      { id: "score-consolidation", type: "agent", depends_on: ["scan-opportunities"] },
      { id: "check-substitutions", type: "tool", depends_on: ["scan-opportunities"] },
      { id: "compliance-gate", type: "agent", depends_on: ["score-consolidation", "load-compliance"] },
      { id: "generate-proposal", type: "agent", depends_on: ["compliance-gate", "check-substitutions"] },
      { id: "persist-proposal", type: "tool", depends_on: ["generate-proposal"] },
    ],
  },
  supplier_fallout: {
    name: "supplier_fallout",
    trigger: "alert",
    layers: [
      ["fetch-incident"],
      ["affected-skus", "supplier-history"],
      ["substitution-search"],
      ["draft-mitigation"],
      ["notify"],
    ],
    nodes: [
      { id: "fetch-incident", type: "tool", depends_on: [] },
      { id: "affected-skus", type: "tool", depends_on: ["fetch-incident"] },
      { id: "supplier-history", type: "agent", depends_on: ["fetch-incident"] },
      { id: "substitution-search", type: "agent", depends_on: ["affected-skus", "supplier-history"] },
      { id: "draft-mitigation", type: "agent", depends_on: ["substitution-search"] },
      { id: "notify", type: "tool", depends_on: ["draft-mitigation"] },
    ],
  },
  price_audit: {
    name: "price_audit",
    trigger: "scheduled",
    layers: [["fetch-prices"], ["benchmark"], ["flag-outliers"], ["report"]],
    nodes: [
      { id: "fetch-prices", type: "tool", depends_on: [] },
      { id: "benchmark", type: "agent", depends_on: ["fetch-prices"] },
      { id: "flag-outliers", type: "agent", depends_on: ["benchmark"] },
      { id: "report", type: "tool", depends_on: ["flag-outliers"] },
    ],
  },
  substitution_discovery: {
    name: "substitution_discovery",
    trigger: "manual",
    layers: [["seed-ingredient"], ["molport-search", "pubchem-search"], ["score-candidates"], ["recommend"]],
    nodes: [
      { id: "seed-ingredient", type: "tool", depends_on: [] },
      { id: "molport-search", type: "tool", depends_on: ["seed-ingredient"] },
      { id: "pubchem-search", type: "tool", depends_on: ["seed-ingredient"] },
      { id: "score-candidates", type: "agent", depends_on: ["molport-search", "pubchem-search"] },
      { id: "recommend", type: "agent", depends_on: ["score-candidates"] },
    ],
  },
  new_ingredient_research: {
    name: "new_ingredient_research",
    trigger: "manual",
    layers: [["intake"], ["dsld-lookup", "pubchem-fetch"], ["regulatory-check"], ["summary"]],
    nodes: [
      { id: "intake", type: "tool", depends_on: [] },
      { id: "dsld-lookup", type: "tool", depends_on: ["intake"] },
      { id: "pubchem-fetch", type: "tool", depends_on: ["intake"] },
      { id: "regulatory-check", type: "agent", depends_on: ["dsld-lookup", "pubchem-fetch"] },
      { id: "summary", type: "agent", depends_on: ["regulatory-check"] },
    ],
  },
};

function pipelineFor(text: string): string {
  const t = text.toLowerCase();
  if (t.includes("price")) return "price_audit";
  if (t.includes("substit") || t.includes("alternative")) return "substitution_discovery";
  if (t.includes("new") && t.includes("ingredient")) return "new_ingredient_research";
  if (t.includes("recall") || t.includes("fallout") || t.includes("disrupt")) return "supplier_fallout";
  return "proactive_consolidation";
}

export const mockData = {
  opportunities: () => makeOpportunities().sort((a, b) => b.consolidation_score - a.consolidation_score),
  ingredients: (grade?: string) => {
    const all = makeIngredients();
    return grade ? all.filter((i) => i.grade === grade) : all;
  },
  compliance: () => makeCompliance(),
  proposals: () => makeProposals(),
  runs: () => makeRuns(),
  graph: (name: string) => PIPELINE_GRAPHS[name] ?? PIPELINE_GRAPHS.proactive_consolidation,

  newRunId(name: string) {
    return `run_${name.slice(0, 4)}_${Math.random().toString(16).slice(2, 8)}`;
  },

  simulateChat(text: string): ChatResponse {
    const pipeline = pipelineFor(text);
    return {
      run_id: this.newRunId(pipeline),
      pipeline,
      status: "running",
      confidence: 0.78 + Math.random() * 0.18,
    };
  },

  runDetail(id: string): RunDetail {
    const runs = makeRuns();
    const r = runs.find((x) => x.run_id === id) ?? runs[0];
    return { ...r, events: [] };
  },

  // Replays a realistic DAG run, emitting node_started/completed events.
  simulateStream(
    runId: string,
    onEvent: (e: RunEvent) => void,
    onClose?: () => void,
  ): () => void {
    // Pick the most likely pipeline based on the run id prefix.
    const guess = Object.keys(PIPELINE_GRAPHS).find((p) => runId.includes(p.slice(0, 4)));
    const graph = PIPELINE_GRAPHS[guess ?? "proactive_consolidation"];
    let cancelled = false;
    const timers: number[] = [];

    let tCursor = 0;
    graph.layers.forEach((layer) => {
      const layerStart = tCursor + 250;
      layer.forEach((nodeId) => {
        const startAt = layerStart + Math.random() * 120;
        const duration = 380 + Math.random() * 720;
        timers.push(
          window.setTimeout(() => {
            if (cancelled) return;
            onEvent({
              event_type: "node_started",
              node_id: nodeId,
              created_at: new Date().toISOString(),
            });
          }, startAt),
        );
        timers.push(
          window.setTimeout(() => {
            if (cancelled) return;
            const elapsed = Math.round(duration);
            const isProposal = nodeId === "generate-proposal";
            onEvent({
              event_type: "node_completed",
              node_id: nodeId,
              created_at: new Date().toISOString(),
              node_output: {
                _elapsed_ms: elapsed,
                ...(isProposal
                  ? {
                      proposal_text: proposalText("Vitamin C", 4, 0.87),
                      summary:
                        "Recommend consolidating Vitamin C from 4 suppliers to 2, projected $186K annual savings, no compliance risk.",
                    }
                  : { ok: true, rows: Math.floor(20 + Math.random() * 200) }),
              },
            });
          }, startAt + duration),
        );
      });
      tCursor = layerStart + 1100;
    });

    timers.push(
      window.setTimeout(() => {
        if (cancelled) return;
        onEvent({
          event_type: "pipeline_completed",
          created_at: new Date().toISOString(),
          message: "Pipeline finished successfully.",
        });
        onClose?.();
      }, tCursor + 200),
    );

    return () => {
      cancelled = true;
      timers.forEach((t) => window.clearTimeout(t));
      onClose?.();
    };
  },
};
