// ============================================================================
// Market Analysis Knowledge Graph — Neo4j Schema
// Talan Intelligent Enterprise Assistant
// ============================================================================
// Run these Cypher statements once to set up constraints and indexes.
// They are all idempotent (IF NOT EXISTS).
// ============================================================================

// ── 1. Uniqueness Constraints ────────────────────────────────────────────────

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Company)
  REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Sector)
  REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Country)
  REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event)
  REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:MacroIndicator)
  REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:News)
  REQUIRE n.external_id IS UNIQUE;


// ── 2. Indexes ────────────────────────────────────────────────────────────────

// Company ticker lookup (fast stock data joins)
CREATE INDEX IF NOT EXISTS FOR (n:Company) ON (n.ticker);

// Temporal indexes on causal edges
CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.timestamp);
CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.impact_score);
CREATE INDEX IF NOT EXISTS FOR ()-[r:CAUSES_IMPACT_ON]-() ON (r.talan_relevant);

// News severity / urgency filtering
CREATE INDEX IF NOT EXISTS FOR (n:News) ON (n.severity);
CREATE INDEX IF NOT EXISTS FOR (n:News) ON (n.urgency);
CREATE INDEX IF NOT EXISTS FOR (n:News) ON (n.published_at);


// ── 3. Seed Nodes — Talan + Key Competitors + Sectors ────────────────────────

// Talan (primary company node — always present)
MERGE (t:Company {name: 'Talan'})
  ON CREATE SET
    t.ticker      = 'TAL.PA',
    t.sector      = 'IT Services / ESN',
    t.country     = 'France',
    t.revenue_eur = 600000000,
    t.employees   = 6000,
    t.exchange    = 'Euronext Paris',
    t.aliases     = ['Talan ESN', 'Talan Group', 'Talan SA'],
    t.created_at  = datetime();

// Key French IT competitors
MERGE (c1:Company {name: 'Capgemini'})
  ON CREATE SET c1.ticker = 'CAP.PA', c1.country = 'France', c1.created_at = datetime();
MERGE (c2:Company {name: 'Sopra Steria'})
  ON CREATE SET c2.ticker = 'SOP.PA', c2.country = 'France', c2.created_at = datetime();
MERGE (c3:Company {name: 'Atos'})
  ON CREATE SET c3.ticker = 'ATO.PA', c3.country = 'France', c3.created_at = datetime();
MERGE (c4:Company {name: 'CGI'})
  ON CREATE SET c4.ticker = 'GIB', c4.country = 'Canada', c4.created_at = datetime();
MERGE (c5:Company {name: 'Accenture'})
  ON CREATE SET c5.ticker = 'ACN', c5.country = 'Ireland', c5.created_at = datetime();

// Key tech companies that affect the IT services sector
MERGE (t1:Company {name: 'NVIDIA'})
  ON CREATE SET t1.ticker = 'NVDA', t1.country = 'United States', t1.created_at = datetime();
MERGE (t2:Company {name: 'Microsoft'})
  ON CREATE SET t2.ticker = 'MSFT', t2.country = 'United States', t2.created_at = datetime();
MERGE (t3:Company {name: 'OpenAI'})
  ON CREATE SET t3.country = 'United States', t3.created_at = datetime();
MERGE (t4:Company {name: 'Google'})
  ON CREATE SET t4.ticker = 'GOOGL', t4.country = 'United States', t4.created_at = datetime();

// Sectors
MERGE (s1:Sector {name: 'IT Services'})         ON CREATE SET s1.created_at = datetime();
MERGE (s2:Sector {name: 'Banking & Finance'})   ON CREATE SET s2.created_at = datetime();
MERGE (s3:Sector {name: 'Insurance'})           ON CREATE SET s3.created_at = datetime();
MERGE (s4:Sector {name: 'Telecom'})             ON CREATE SET s4.created_at = datetime();
MERGE (s5:Sector {name: 'Public Sector'})       ON CREATE SET s5.created_at = datetime();
MERGE (s6:Sector {name: 'Energy'})              ON CREATE SET s6.created_at = datetime();
MERGE (s7:Sector {name: 'Artificial Intelligence'}) ON CREATE SET s7.created_at = datetime();
MERGE (s8:Sector {name: 'Semiconductors'})      ON CREATE SET s8.created_at = datetime();

// Countries
MERGE (co1:Country {name: 'France'})            ON CREATE SET co1.created_at = datetime();
MERGE (co2:Country {name: 'United States'})     ON CREATE SET co2.created_at = datetime();
MERGE (co3:Country {name: 'European Union'})    ON CREATE SET co3.created_at = datetime();
MERGE (co4:Country {name: 'China'})             ON CREATE SET co4.created_at = datetime();
MERGE (co5:Country {name: 'Russia'})            ON CREATE SET co5.created_at = datetime();

// Macro Indicators
MERGE (m1:MacroIndicator {name: 'CAC40'})
  ON CREATE SET m1.type = 'index', m1.currency = 'EUR', m1.created_at = datetime();
MERGE (m2:MacroIndicator {name: 'EUR/USD'})
  ON CREATE SET m2.type = 'forex', m2.created_at = datetime();
MERGE (m3:MacroIndicator {name: 'ECB_Interest_Rate'})
  ON CREATE SET m3.type = 'rate', m3.created_at = datetime();
MERGE (m4:MacroIndicator {name: 'VIX'})
  ON CREATE SET m4.type = 'volatility_index', m4.created_at = datetime();
MERGE (m5:MacroIndicator {name: 'Oil_Brent'})
  ON CREATE SET m5.type = 'commodity', m5.currency = 'USD', m5.created_at = datetime();
MERGE (m6:MacroIndicator {name: 'France_Inflation'})
  ON CREATE SET m6.type = 'macro', m6.created_at = datetime();
MERGE (m7:MacroIndicator {name: 'France_GDP_Growth'})
  ON CREATE SET m7.type = 'macro', m7.created_at = datetime();


// ── 4. Structural Relations ───────────────────────────────────────────────────

// Talan — sector membership
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'IT Services'})
MERGE (t)-[:BELONGS_TO_SECTOR]->(s);

MATCH (t:Company {name: 'Talan'}), (co:Country {name: 'France'})
MERGE (t)-[:OPERATES_IN]->(co);

// Competitors
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Capgemini'})
MERGE (t)-[:COMPETES_WITH]->(c);
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Sopra Steria'})
MERGE (t)-[:COMPETES_WITH]->(c);
MATCH (t:Company {name: 'Talan'}), (c:Company {name: 'Atos'})
MERGE (t)-[:COMPETES_WITH]->(c);

// Key client sectors for Talan
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Banking & Finance'})
MERGE (t)-[:SERVES_SECTOR]->(s);
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Insurance'})
MERGE (t)-[:SERVES_SECTOR]->(s);
MATCH (t:Company {name: 'Talan'}), (s:Sector {name: 'Public Sector'})
MERGE (t)-[:SERVES_SECTOR]->(s);

// AI sector influences IT services demand
MATCH (ai:Sector {name: 'Artificial Intelligence'}), (it:Sector {name: 'IT Services'})
MERGE (ai)-[:CAUSES_IMPACT_ON {
  impact_score: 0.6,
  confidence: 0.8,
  reason: 'AI adoption drives digital transformation consulting demand',
  time_horizon: '1month',
  talan_relevant: true,
  timestamp: datetime(),
  source_article: 'seed_data'
}]->(it);


// ── 5. Sample Historical Event (DeepSeek shock — Jan 2025) ───────────────────

MERGE (e1:Event {name: 'DeepSeek_R1_Release_Jan2025'})
  ON CREATE SET
    e1.description = 'DeepSeek released R1, a powerful open-source LLM rivaling GPT-4 at fraction of cost',
    e1.date        = date('2025-01-20'),
    e1.created_at  = datetime();

MATCH (e:Event {name: 'DeepSeek_R1_Release_Jan2025'}), (n:Company {name: 'NVIDIA'})
MERGE (e)-[:CAUSES_IMPACT_ON {
  impact_score:  -0.8,
  confidence:    0.9,
  reason:        'Reduced expected demand for NVIDIA GPU training clusters if efficient small models suffice',
  time_horizon:  '48h',
  talan_relevant: false,
  timestamp:     datetime('2025-01-20T00:00:00'),
  source_article: 'seed_deepseek'
}]->(n);

MATCH (e:Event {name: 'DeepSeek_R1_Release_Jan2025'}), (s:Sector {name: 'IT Services'})
MERGE (e)-[:CAUSES_IMPACT_ON {
  impact_score:  0.3,
  confidence:    0.6,
  reason:        'Cheaper AI inference → more AI projects → more consulting work for ESNs',
  time_horizon:  '1month',
  talan_relevant: true,
  timestamp:     datetime('2025-01-20T00:00:00'),
  source_article: 'seed_deepseek'
}]->(s);

MATCH (s:Sector {name: 'IT Services'}), (t:Company {name: 'Talan'})
MERGE (s)-[:CAUSES_IMPACT_ON {
  impact_score:  0.2,
  confidence:    0.5,
  reason:        'AI consulting wave benefits all ESNs including Talan',
  time_horizon:  '1month',
  talan_relevant: true,
  timestamp:     datetime('2025-01-20T00:00:00'),
  source_article: 'seed_deepseek'
}]->(t);


// ── 6. Useful Queries Reference ───────────────────────────────────────────────
// (Comments only — not executed)

// All risks reaching Talan within 2 hops:
// MATCH path = (source)-[:CAUSES_IMPACT_ON*1..2]->(t:Company {name: 'Talan'})
// RETURN source.name, [r IN relationships(path) | r.impact_score] AS scores
// ORDER BY scores[0] ASC LIMIT 20;

// Hidden risk chains (3 hops, negative impact):
// MATCH path = (src)-[rels:CAUSES_IMPACT_ON*2..3]->(t {name: 'Talan'})
// WHERE REDUCE(s=0, r IN rels | s + r.impact_score) < -0.3
// RETURN src.name, length(path) AS hops, REDUCE(s=0, r IN rels | s + r.impact_score) AS chain_score
// ORDER BY chain_score ASC LIMIT 10;

// Most impactful recent events:
// MATCH ()-[r:CAUSES_IMPACT_ON]->() WHERE r.timestamp > datetime() - duration('P7D')
// RETURN r.impact_score, r.reason, r.source_article ORDER BY abs(r.impact_score) DESC LIMIT 10;
