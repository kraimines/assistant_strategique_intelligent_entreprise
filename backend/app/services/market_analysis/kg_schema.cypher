// ============================================================================
// Market Analysis Knowledge Graph — Neo4j Schema v3
// Talan Intelligent Enterprise Assistant
// ============================================================================
// Run these Cypher statements once to set up constraints, indexes,
// the Talan business-unit / client / supplier structure and the
// edge-type compatibility matrix consumed by the propagation engine.
// All statements are idempotent (IF NOT EXISTS / MERGE).
// ============================================================================

// ── 1. Uniqueness Constraints ────────────────────────────────────────────────

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Company)         REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Sector)          REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Country)         REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event)           REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:MacroIndicator)  REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:News)            REQUIRE n.external_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:BusinessUnit)    REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Client)          REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Supplier)        REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept)         REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:CompatibilityRule)
  REQUIRE (n.rel_type, n.src_label, n.dst_label) IS UNIQUE;


// ── 2. Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS FOR (n:Company) ON (n.ticker);
CREATE INDEX IF NOT EXISTS FOR (n:Concept) ON (n.is_generic_hub);
CREATE INDEX IF NOT EXISTS FOR (n:News)    ON (n.severity);
CREATE INDEX IF NOT EXISTS FOR (n:News)    ON (n.urgency);
CREATE INDEX IF NOT EXISTS FOR (n:News)    ON (n.published_at);

CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.timestamp);
CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.impact_score);
CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.relation_strength);
CREATE INDEX IF NOT EXISTS FOR ()-[r:IMPACTS]-()          ON (r.timestamp);
CREATE INDEX IF NOT EXISTS FOR ()-[r:INFLUENCES]-()       ON (r.confidence);


// ── 3. Seed Companies ────────────────────────────────────────────────────────

MERGE (t:Company {name: 'Talan'})
  ON CREATE SET
    t.slug         = 'talan',
    t.ticker       = 'TAL.PA',
    t.sector       = 'IT Services / ESN',
    t.country      = 'France',
    t.revenue_eur  = 600000000,
    t.employees    = 6000,
    t.exchange     = 'Euronext Paris',
    t.aliases      = ['Talan ESN', 'Talan Group', 'Talan SA'],
    t.is_generic_hub = false,
    t.specificity  = 1.0,
    t.created_at   = datetime();

MERGE (c1:Company {name: 'Capgemini'})    ON CREATE SET c1.slug='capgemini',    c1.ticker='CAP.PA', c1.country='France',         c1.is_generic_hub=false, c1.created_at=datetime();
MERGE (c2:Company {name: 'Sopra Steria'}) ON CREATE SET c2.slug='sopra-steria', c2.ticker='SOP.PA', c2.country='France',         c2.is_generic_hub=false, c2.created_at=datetime();
MERGE (c3:Company {name: 'Atos'})         ON CREATE SET c3.slug='atos',         c3.ticker='ATO.PA', c3.country='France',         c3.is_generic_hub=false, c3.created_at=datetime();
MERGE (c4:Company {name: 'CGI'})          ON CREATE SET c4.slug='cgi',          c4.ticker='GIB',    c4.country='Canada',         c4.is_generic_hub=false, c4.created_at=datetime();
MERGE (c5:Company {name: 'Accenture'})    ON CREATE SET c5.slug='accenture',    c5.ticker='ACN',    c5.country='Ireland',        c5.is_generic_hub=false, c5.created_at=datetime();
MERGE (t1:Company {name: 'NVIDIA'})       ON CREATE SET t1.slug='nvidia',       t1.ticker='NVDA',   t1.country='United States',  t1.is_generic_hub=false, t1.created_at=datetime();
MERGE (t2:Company {name: 'Microsoft'})    ON CREATE SET t2.slug='microsoft',    t2.ticker='MSFT',   t2.country='United States',  t2.is_generic_hub=false, t2.created_at=datetime();
MERGE (t3:Company {name: 'OpenAI'})       ON CREATE SET t3.slug='openai',                            t3.country='United States', t3.is_generic_hub=false, t3.created_at=datetime();
MERGE (t4:Company {name: 'Google'})       ON CREATE SET t4.slug='google',       t4.ticker='GOOGL',  t4.country='United States',  t4.is_generic_hub=false, t4.created_at=datetime();
MERGE (t5:Company {name: 'Anthropic'})    ON CREATE SET t5.slug='anthropic',                         t5.country='United States', t5.is_generic_hub=false, t5.created_at=datetime();


// ── 4. Sectors with taxonomy paths ───────────────────────────────────────────

MERGE (s1:Sector {name: 'IT Services'})              ON CREATE SET s1.slug='it-services',              s1.taxonomy_path=['Technology','Services','IT Consulting'],         s1.created_at=datetime();
MERGE (s2:Sector {name: 'Banking & Finance'})        ON CREATE SET s2.slug='banking-finance',          s2.taxonomy_path=['Finance','Banking'],                              s2.created_at=datetime();
MERGE (s3:Sector {name: 'Insurance'})                ON CREATE SET s3.slug='insurance',                s3.taxonomy_path=['Finance','Insurance'],                            s3.created_at=datetime();
MERGE (s4:Sector {name: 'Telecom'})                  ON CREATE SET s4.slug='telecom',                  s4.taxonomy_path=['Technology','Telecom'],                           s4.created_at=datetime();
MERGE (s5:Sector {name: 'Public Sector'})            ON CREATE SET s5.slug='public-sector',            s5.taxonomy_path=['Public','Government'],                            s5.created_at=datetime();
MERGE (s6:Sector {name: 'Energy'})                   ON CREATE SET s6.slug='energy',                   s6.taxonomy_path=['Industry','Energy'],                              s6.created_at=datetime();
MERGE (s7:Sector {name: 'Artificial Intelligence'})  ON CREATE SET s7.slug='artificial-intelligence',  s7.taxonomy_path=['Technology','Software','AI/ML'],                  s7.created_at=datetime();
MERGE (s8:Sector {name: 'Semiconductors'})           ON CREATE SET s8.slug='semiconductors',           s8.taxonomy_path=['Technology','Hardware','Semiconductors'],         s8.created_at=datetime();


// ── 5. Countries ─────────────────────────────────────────────────────────────

MERGE (co1:Country {name: 'France'})         ON CREATE SET co1.slug='france',         co1.created_at=datetime();
MERGE (co2:Country {name: 'United States'})  ON CREATE SET co2.slug='united-states',  co2.created_at=datetime();
MERGE (co3:Country {name: 'European Union'}) ON CREATE SET co3.slug='european-union', co3.created_at=datetime();
MERGE (co4:Country {name: 'China'})          ON CREATE SET co4.slug='china',          co4.created_at=datetime();
MERGE (co5:Country {name: 'Russia'})         ON CREATE SET co5.slug='russia',         co5.created_at=datetime();


// ── 6. Macro Indicators ──────────────────────────────────────────────────────

MERGE (m1:MacroIndicator {name: 'CAC40'})              ON CREATE SET m1.slug='cac40',              m1.type='index',            m1.currency='EUR', m1.created_at=datetime();
MERGE (m2:MacroIndicator {name: 'EUR/USD'})            ON CREATE SET m2.slug='eur-usd',            m2.type='forex',                                   m2.created_at=datetime();
MERGE (m3:MacroIndicator {name: 'ECB_Interest_Rate'})  ON CREATE SET m3.slug='ecb-interest-rate',  m3.type='rate',                                    m3.created_at=datetime();
MERGE (m4:MacroIndicator {name: 'VIX'})                ON CREATE SET m4.slug='vix',                m4.type='volatility_index',                        m4.created_at=datetime();
MERGE (m5:MacroIndicator {name: 'Oil_Brent'})          ON CREATE SET m5.slug='oil-brent',          m5.type='commodity',        m5.currency='USD', m5.created_at=datetime();
MERGE (m6:MacroIndicator {name: 'France_Inflation'})   ON CREATE SET m6.slug='france-inflation',   m6.type='macro',                                   m6.created_at=datetime();
MERGE (m7:MacroIndicator {name: 'France_GDP_Growth'})  ON CREATE SET m7.slug='france-gdp-growth',  m7.type='macro',                                   m7.created_at=datetime();


// ── 7. Talan Business Units ──────────────────────────────────────────────────
// Each BU represents an operational unit through which exposure
// to external events is mediated.

MERGE (bu1:BusinessUnit {name: 'Talan Banking & Insurance Consulting'})
  ON CREATE SET
    bu1.slug='bu-banking-insurance',
    bu1.parent_company='Talan',
    bu1.revenue_share=0.32,
    bu1.sector_focus=['Banking & Finance','Insurance'],
    bu1.geo_focus=['France','European Union'],
    bu1.created_at=datetime();

MERGE (bu2:BusinessUnit {name: 'Talan GenAI Studio'})
  ON CREATE SET
    bu2.slug='bu-genai-studio',
    bu2.parent_company='Talan',
    bu2.revenue_share=0.18,
    bu2.sector_focus=['Artificial Intelligence','IT Services'],
    bu2.geo_focus=['France','European Union','United States'],
    bu2.created_at=datetime();

MERGE (bu3:BusinessUnit {name: 'Talan Cloud & Cybersecurity'})
  ON CREATE SET
    bu3.slug='bu-cloud-cyber',
    bu3.parent_company='Talan',
    bu3.revenue_share=0.20,
    bu3.sector_focus=['IT Services'],
    bu3.geo_focus=['France','European Union'],
    bu3.created_at=datetime();

MERGE (bu4:BusinessUnit {name: 'Talan Public Sector Consulting'})
  ON CREATE SET
    bu4.slug='bu-public-sector',
    bu4.parent_company='Talan',
    bu4.revenue_share=0.15,
    bu4.sector_focus=['Public Sector'],
    bu4.geo_focus=['France'],
    bu4.created_at=datetime();

MERGE (bu5:BusinessUnit {name: 'Talan Supply Chain & Industry'})
  ON CREATE SET
    bu5.slug='bu-supply-chain',
    bu5.parent_company='Talan',
    bu5.revenue_share=0.15,
    bu5.sector_focus=['Energy','Telecom'],
    bu5.geo_focus=['France','European Union'],
    bu5.created_at=datetime();

MATCH (t:Company {name: 'Talan'})
MATCH (bu:BusinessUnit)
WHERE bu.parent_company = 'Talan'
MERGE (t)-[:OPERATES_BU]->(bu);


// ── 8. Talan Clients (sector-level + a few named accounts) ───────────────────

MERGE (cl1:Client {name: 'European Banking Clients'})
  ON CREATE SET cl1.slug='client-eu-banking', cl1.sector='Banking & Finance', cl1.country='European Union', cl1.revenue_share=0.28, cl1.criticality='high', cl1.created_at=datetime();
MERGE (cl2:Client {name: 'French Insurance Clients'})
  ON CREATE SET cl2.slug='client-fr-insurance', cl2.sector='Insurance', cl2.country='France', cl2.revenue_share=0.10, cl2.criticality='high', cl2.created_at=datetime();
MERGE (cl3:Client {name: 'French Public Sector Clients'})
  ON CREATE SET cl3.slug='client-fr-public', cl3.sector='Public Sector', cl3.country='France', cl3.revenue_share=0.15, cl3.criticality='medium', cl3.created_at=datetime();
MERGE (cl4:Client {name: 'European Energy & Utilities Clients'})
  ON CREATE SET cl4.slug='client-eu-energy', cl4.sector='Energy', cl4.country='European Union', cl4.revenue_share=0.08, cl4.criticality='medium', cl4.created_at=datetime();
MERGE (cl5:Client {name: 'European Telecom Clients'})
  ON CREATE SET cl5.slug='client-eu-telecom', cl5.sector='Telecom', cl5.country='European Union', cl5.revenue_share=0.07, cl5.criticality='medium', cl5.created_at=datetime();

// BU → Client mapping (BU_SERVES)
MATCH (bu:BusinessUnit {name:'Talan Banking & Insurance Consulting'}), (cl:Client {name:'European Banking Clients'})    MERGE (bu)-[:BU_SERVES]->(cl);
MATCH (bu:BusinessUnit {name:'Talan Banking & Insurance Consulting'}), (cl:Client {name:'French Insurance Clients'})   MERGE (bu)-[:BU_SERVES]->(cl);
MATCH (bu:BusinessUnit {name:'Talan Public Sector Consulting'}),       (cl:Client {name:'French Public Sector Clients'}) MERGE (bu)-[:BU_SERVES]->(cl);
MATCH (bu:BusinessUnit {name:'Talan Supply Chain & Industry'}),        (cl:Client {name:'European Energy & Utilities Clients'}) MERGE (bu)-[:BU_SERVES]->(cl);
MATCH (bu:BusinessUnit {name:'Talan Supply Chain & Industry'}),        (cl:Client {name:'European Telecom Clients'}) MERGE (bu)-[:BU_SERVES]->(cl);


// ── 9. Talan Suppliers ───────────────────────────────────────────────────────

MERGE (sp1:Supplier {name: 'AWS'})       ON CREATE SET sp1.slug='aws',       sp1.category='cloud',         sp1.criticality='high',   sp1.substitutability='medium', sp1.created_at=datetime();
MERGE (sp2:Supplier {name: 'Azure'})     ON CREATE SET sp2.slug='azure',     sp2.category='cloud',         sp2.criticality='high',   sp2.substitutability='medium', sp2.created_at=datetime();
MERGE (sp3:Supplier {name: 'GCP'})       ON CREATE SET sp3.slug='gcp',       sp3.category='cloud',         sp3.criticality='medium', sp3.substitutability='high',   sp3.created_at=datetime();
MERGE (sp4:Supplier {name: 'OpenAI API'}) ON CREATE SET sp4.slug='openai-api', sp4.category='llm',         sp4.criticality='medium', sp4.substitutability='medium', sp4.created_at=datetime();
MERGE (sp5:Supplier {name: 'Anthropic API'}) ON CREATE SET sp5.slug='anthropic-api', sp5.category='llm',   sp5.criticality='medium', sp5.substitutability='medium', sp5.created_at=datetime();
MERGE (sp6:Supplier {name: 'NVIDIA GPUs'}) ON CREATE SET sp6.slug='nvidia-gpus', sp6.category='hardware',  sp6.criticality='medium', sp6.substitutability='low',    sp6.created_at=datetime();

// BU → Supplier dependencies
MATCH (bu:BusinessUnit {name:'Talan GenAI Studio'}),      (sp:Supplier {name:'OpenAI API'})    MERGE (bu)-[:BU_DEPENDS_ON]->(sp);
MATCH (bu:BusinessUnit {name:'Talan GenAI Studio'}),      (sp:Supplier {name:'Anthropic API'}) MERGE (bu)-[:BU_DEPENDS_ON]->(sp);
MATCH (bu:BusinessUnit {name:'Talan GenAI Studio'}),      (sp:Supplier {name:'NVIDIA GPUs'})   MERGE (bu)-[:BU_DEPENDS_ON]->(sp);
MATCH (bu:BusinessUnit {name:'Talan Cloud & Cybersecurity'}), (sp:Supplier {name:'AWS'})       MERGE (bu)-[:BU_DEPENDS_ON]->(sp);
MATCH (bu:BusinessUnit {name:'Talan Cloud & Cybersecurity'}), (sp:Supplier {name:'Azure'})     MERGE (bu)-[:BU_DEPENDS_ON]->(sp);


// ── 10. Structural relations Talan ↔ KG ──────────────────────────────────────

MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'IT Services'})           MERGE (t)-[:BELONGS_TO_SECTOR]->(s);
MATCH (t:Company {name: 'Talan'}), (co:Country {name: 'France'})              MERGE (t)-[:OPERATES_IN]->(co);
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Capgemini'})            MERGE (t)-[:COMPETES_WITH]->(c);
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Sopra Steria'})         MERGE (t)-[:COMPETES_WITH]->(c);
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Atos'})                 MERGE (t)-[:COMPETES_WITH]->(c);
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Banking & Finance'})     MERGE (t)-[:SERVES_SECTOR]->(s);
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Insurance'})             MERGE (t)-[:SERVES_SECTOR]->(s);
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Public Sector'})         MERGE (t)-[:SERVES_SECTOR]->(s);


// ── 11. Generic Concept hubs (replace free-floating "AI/Europe/Economy") ─────
// These nodes are flagged is_generic_hub=true so the propagation engine
// applies the strong hub penalty (β=0.5 in scoring/hub_penalty.py).

MERGE (k1:Concept {name: 'Artificial Intelligence (concept)'}) ON CREATE SET k1.slug='concept-ai',          k1.is_generic_hub=true, k1.parent_concept='Technology', k1.created_at=datetime();
MERGE (k2:Concept {name: 'Europe (region concept)'})           ON CREATE SET k2.slug='concept-europe',      k2.is_generic_hub=true, k2.parent_concept='Geography',  k2.created_at=datetime();
MERGE (k3:Concept {name: 'Economy (concept)'})                 ON CREATE SET k3.slug='concept-economy',     k3.is_generic_hub=true, k3.parent_concept='MacroAbstract', k3.created_at=datetime();
MERGE (k4:Concept {name: 'Innovation (concept)'})              ON CREATE SET k4.slug='concept-innovation',  k4.is_generic_hub=true, k4.parent_concept='Technology', k4.created_at=datetime();
MERGE (k5:Concept {name: 'Digital Transformation (concept)'})  ON CREATE SET k5.slug='concept-digital-tx',  k5.is_generic_hub=true, k5.parent_concept='Technology', k5.created_at=datetime();
MERGE (k6:Concept {name: 'GenAI (concept)'})                   ON CREATE SET k6.slug='concept-genai',       k6.is_generic_hub=true, k6.parent_concept='Technology', k6.created_at=datetime();


// ── 12. Edge-Type Compatibility Matrix ───────────────────────────────────────
// alpha ∈ {0.0, 0.3, 0.7, 1.0}: 0 = drop edge, 1 = full strength.
// Looked up by (rel_type, src_label, dst_label) at inference time.
// half_life_days drives the temporal decay τ(e) = exp(-ln(2)·Δt/λ_r) per §3(b).

MERGE (r:CompatibilityRule {rel_type:'COMPETES_WITH',    src_label:'Competitor',    dst_label:'Company'})       ON CREATE SET r.alpha=1.0, r.half_life_days=60,  r.category='competitive', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'COMPETES_WITH',    src_label:'Company',       dst_label:'Company'})       ON CREATE SET r.alpha=1.0, r.half_life_days=60,  r.category='competitive', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Competitor',    dst_label:'Company'})       ON CREATE SET r.alpha=1.0, r.half_life_days=60,  r.category='competitive', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Supplier',      dst_label:'BusinessUnit'})  ON CREATE SET r.alpha=1.0, r.half_life_days=45,  r.category='supply_chain', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Supplier',      dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=45,  r.category='supply_chain', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Regulation',    dst_label:'Sector'})        ON CREATE SET r.alpha=1.0, r.half_life_days=180, r.category='regulatory',  r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Regulation',    dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=180, r.category='regulatory',  r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'MacroIndicator', dst_label:'Sector'})       ON CREATE SET r.alpha=0.7, r.half_life_days=120, r.category='macro',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'MacroIndicator', dst_label:'Company'})      ON CREATE SET r.alpha=0.3, r.half_life_days=120, r.category='macro',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Event',         dst_label:'Sector'})        ON CREATE SET r.alpha=1.0, r.half_life_days=30,  r.category='event',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Event',         dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=30,  r.category='event',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Event',         dst_label:'BusinessUnit'})  ON CREATE SET r.alpha=1.0, r.half_life_days=30,  r.category='event',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Sector',        dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=90,  r.category='sector',      r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Sector',        dst_label:'BusinessUnit'})  ON CREATE SET r.alpha=1.0, r.half_life_days=90,  r.category='sector',      r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Sector',        dst_label:'Sector'})        ON CREATE SET r.alpha=0.7, r.half_life_days=90,  r.category='sector',      r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Concept',       dst_label:'Company'})       ON CREATE SET r.alpha=0.3, r.half_life_days=90,  r.category='generic',     r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Concept',       dst_label:'Sector'})        ON CREATE SET r.alpha=0.3, r.half_life_days=90,  r.category='generic',     r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Country',       dst_label:'Concept'})       ON CREATE SET r.alpha=0.0, r.half_life_days=180, r.category='blocked',     r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Country',       dst_label:'Company'})       ON CREATE SET r.alpha=0.3, r.half_life_days=180, r.category='geo',         r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'CAUSES_IMPACT_ON', src_label:'Country',       dst_label:'Sector'})        ON CREATE SET r.alpha=0.3, r.half_life_days=180, r.category='geo',         r.created_at=datetime();

MERGE (r:CompatibilityRule {rel_type:'INFLUENCES',       src_label:'Competitor',    dst_label:'Company'})       ON CREATE SET r.alpha=1.0, r.half_life_days=60,  r.category='competitive', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'INFLUENCES',       src_label:'Sector',        dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=90,  r.category='sector',      r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'INFLUENCES',       src_label:'MacroIndicator', dst_label:'Sector'})       ON CREATE SET r.alpha=0.7, r.half_life_days=120, r.category='macro',       r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'INFLUENCES',       src_label:'Concept',       dst_label:'Company'})       ON CREATE SET r.alpha=0.3, r.half_life_days=90,  r.category='generic',     r.created_at=datetime();

MERGE (r:CompatibilityRule {rel_type:'IMPACTS',          src_label:'Competitor',    dst_label:'Company'})       ON CREATE SET r.alpha=1.0, r.half_life_days=60,  r.category='competitive', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'IMPACTS',          src_label:'Supplier',      dst_label:'BusinessUnit'})  ON CREATE SET r.alpha=1.0, r.half_life_days=45,  r.category='supply_chain', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'IMPACTS',          src_label:'Sector',        dst_label:'Company'})       ON CREATE SET r.alpha=0.7, r.half_life_days=90,  r.category='sector',      r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'IMPACTS',          src_label:'Concept',       dst_label:'Company'})       ON CREATE SET r.alpha=0.0, r.half_life_days=90,  r.category='blocked',     r.created_at=datetime();

MERGE (r:CompatibilityRule {rel_type:'MENTIONS',         src_label:'News',          dst_label:'Company'})       ON CREATE SET r.alpha=0.3, r.half_life_days=14,  r.category='evidence',    r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'MENTIONS',         src_label:'News',          dst_label:'Sector'})        ON CREATE SET r.alpha=0.3, r.half_life_days=14,  r.category='evidence',    r.created_at=datetime();

MERGE (r:CompatibilityRule {rel_type:'BELONGS_TO_SECTOR', src_label:'Company',      dst_label:'Sector'})        ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'OPERATES_IN',       src_label:'Company',      dst_label:'Country'})       ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'SERVES_SECTOR',     src_label:'Company',      dst_label:'Sector'})        ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'OPERATES_BU',       src_label:'Company',      dst_label:'BusinessUnit'})  ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'BU_SERVES',         src_label:'BusinessUnit', dst_label:'Client'})        ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'BU_SERVES',         src_label:'BusinessUnit', dst_label:'Sector'})        ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'BU_DEPENDS_ON',     src_label:'BusinessUnit', dst_label:'Supplier'})      ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();
MERGE (r:CompatibilityRule {rel_type:'BU_DEPENDS_ON',     src_label:'BusinessUnit', dst_label:'Technology'})    ON CREATE SET r.alpha=1.0, r.half_life_days=9999, r.category='structural', r.created_at=datetime();


// ── 13. AI sector → IT services demand link (kept) ───────────────────────────
MATCH (ai:Sector {name: 'Artificial Intelligence'}), (it:Sector {name: 'IT Services'})
MERGE (ai)-[r:CAUSES_IMPACT_ON {source_article:'seed_data'}]->(it)
ON CREATE SET
  r.impact_score = 0.6,
  r.confidence   = 0.8,
  r.relation_strength = 0.9,
  r.evidence_quality  = 'primary',
  r.reason       = 'AI adoption drives digital transformation consulting demand',
  r.time_horizon = '1month',
  r.talan_relevant = true,
  r.timestamp    = datetime();
