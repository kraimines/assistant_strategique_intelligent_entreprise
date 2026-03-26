# ETL Pipeline — Quick Start Guide

## 5 Minutes to First Run

### 1. Setup Environment

```bash
# Copy default configuration
cp backend/etl/.env.example .env

# Edit .env if running locally (change POSTGRES_HOST and NEO4J_URI)
# For local dev, change:
# POSTGRES_HOST=localhost
# NEO4J_URI=bolt://localhost:7687
```

### 2. Install Dependencies

```bash
# Install from requirements.txt
pip install -r backend/requirements.txt

# Or manually:
pip install pandas psycopg2-binary neo4j openpyxl
```

### 3. Prepare Data

```bash
# Create data directory
mkdir -p data

# Place your Excel files:
# - data/RH_Talan_Tunisie.xlsx
# - data/CRM_Talan_Tunisie.xlsx
# - data/ERP_Talan_Tunisie.xlsx
```

### 4. Start Databases

#### Option A: Docker (Recommended)

```bash
# Start PostgreSQL and Neo4j
docker-compose -f infra/docker-compose.dev.yml up -d

# Wait for services to be ready (~10 seconds)
docker ps | grep -E "postgres|neo4j"
```

#### Option B: Local Installation

```bash
# PostgreSQL must be running on localhost:5432
# Neo4j must be running on localhost:7687
# Create databases if needed:
psql -U postgres -c "CREATE DATABASE talan_hr;"
psql -U postgres -c "CREATE DATABASE talan_crm;"
psql -U postgres -c "CREATE DATABASE talan_erp;"
```

### 5. Verify Configuration

```bash
cd backend/etl
python config.py

# Expected output:
# === ETL Configuration ===
# Environment: development
# Data Directory: /path/to/data
# Excel Files:
#   ✓ RH: /path/to/data/RH_Talan_Tunisie.xlsx
#   ✓ CRM: /path/to/data/CRM_Talan_Tunisie.xlsx
#   ✓ ERP: /path/to/data/ERP_Talan_Tunisie.xlsx
# PostgreSQL:
#   ✓ talan_hr: postgresql://talan:***@localhost:5432/talan_hr
#   ✓ talan_crm: postgresql://talan:***@localhost:5432/talan_crm
#   ✓ talan_erp: postgresql://talan:***@localhost:5432/talan_erp
# Neo4j:
#   ✓ bolt://localhost:7687 as neo4j
```

### 6. Run ETL Pipeline

```bash
# Full pipeline (PostgreSQL + Neo4j)
python run_all_etl.py

# Examples with partial execution:
python run_all_etl.py --skip-neo4j           # PostgreSQL only
python run_all_etl.py --neo4j-only           # Neo4j only (requires PostgreSQL data)
python run_all_etl.py --hr                   # HR domain only
python run_all_etl.py --hr --crm             # HR + CRM domains
```

### 7. Validate Results

#### PostgreSQL

```bash
# Count rows in each domain
psql -U talan -d talan_hr -c "SELECT COUNT(*) FROM hr.hr_employees;"
psql -U talan -d talan_crm -c "SELECT COUNT(*) FROM crm.crm_accounts;"
psql -U talan -d talan_erp -c "SELECT COUNT(*) FROM erp.erp_customers;"

# List all tables
psql -U talan -d talan_hr -c "SELECT table_name FROM information_schema.tables WHERE table_schema='hr';"
```

#### Neo4j

```bash
# Use Neo4j Browser: http://localhost:7474/browser

# Check node counts
MATCH (n) RETURN labels(n)[0] AS type, COUNT(n) AS count ORDER BY count DESC;

# Check relationship counts
MATCH ()-[r]->() RETURN type(r) AS relationship, COUNT(r) AS count ORDER BY count DESC;
```

## Troubleshooting

### Excel File Not Found

```
FileNotFoundError: [Errno 2] No such file or directory: '.../RH_Talan_Tunisie.xlsx'
```

**Fix**: Ensure Excel files are in the `data/` directory:
```bash
ls -la data/
# Should show:
# RH_Talan_Tunisie.xlsx
# CRM_Talan_Tunisie.xlsx
# ERP_Talan_Tunisie.xlsx
```

### PostgreSQL Connection Error

```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Fix**: Start PostgreSQL container or local service:
```bash
# Docker
docker-compose -f infra/docker-compose.dev.yml up -d postgres

# Or local (macOS)
brew services start postgresql

# Or local (Windows)
net start PostgreSQL-x64-XX
```

### Neo4j Connection Error

```
neo4j.exceptions.ServiceUnavailable: Unable to resolve address
```

**Fix**: Start Neo4j container or local service:
```bash
# Docker
docker-compose -f infra/docker-compose.dev.yml up -d neo4j

# Neo4j Browser: http://localhost:7474
```

### Sheet Not Found Error

```
ValueError: Worksheet named 'employees' not found
```

**Fix**: Check Excel file structure:
```bash
python -c "import openpyxl; wb = openpyxl.load_workbook('data/RH_Talan_Tunisie.xlsx'); print(wb.sheetnames)"
```

Ensure sheet names match those expected by ETL scripts (case-sensitive).

### Permission Denied on Data Directory

```
PermissionError: Permission denied: './data'
```

**Fix**:
```bash
chmod 755 data/
chmod 644 data/*.xlsx
```

## Next Steps

1. **Read Full Documentation**: See `backend/etl/README.md`
2. **Understand Configuration**: Edit `backend/etl/config.py`
3. **Write Tests**: Add tests to `backend/etl/tests/test_etl.py`
4. **Integrate with API**: Connect ETL to FastAPI endpoints

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│           Excel Source Files (data/)                    │
│  RH_*.xlsx    CRM_*.xlsx    ERP_*.xlsx                  │
└────────────┬──────────────┬──────────────┬──────────────┘
             │              │              │
       ┌─────▼──────┬──────▼──────┬──────▼──────┐
       │  etl_rh.py │ etl_crm.py  │ etl_erp.py  │  T-04/05/06/07
       └─────┬──────┴──────┬──────┴──────┬──────┘
             │             │             │
       ┌─────▼─────────────▼─────────────▼─────┐
       │    PostgreSQL (3 Databases)           │  T-07
       │  talan_hr  talan_crm  talan_erp      │
       └─────────────┬────────────────────────┘
                     │
              ┌──────▼──────────┐
              │  etl_neo4j.py   │  T-08
              └──────┬──────────┘
                     │
              ┌──────▼──────────┐
              │  Neo4j Graph    │
              │  (15 types)     │
              └─────────────────┘
```

## Performance Expectations

| Stage | Time | Size |
|-------|------|------|
| T-04/05 (RH) | 5-10s | 200 employees, 500+ skills |
| T-06 (CRM) | 3-5s | 80 accounts, 150 opportunities |
| T-07 (ERP) | 8-12s | 500+ invoices, 200 products |
| T-08 (Neo4j) | 10-15s | 3000 nodes, 5000 relations |
| **Total** | **30-45s** | **All domains** |

## Support

- Check logs: `LOG_LEVEL=DEBUG python run_all_etl.py`
- Read documentation: [backend/etl/README.md](README.md)
- Browse code: Start with `run_all_etl.py` entry point
- Run tests: `python -m pytest backend/etl/tests/ -v`
