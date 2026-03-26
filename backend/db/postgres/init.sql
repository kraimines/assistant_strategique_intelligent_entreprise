-- ===========================================================================
-- init.sql — Exécuté automatiquement par PostgreSQL au 1er démarrage
-- talan_hr est déjà créée via POSTGRES_DB — on crée seulement CRM et ERP
-- ===========================================================================

-- Base CRM
CREATE DATABASE talan_crm
    WITH OWNER = talan
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8';

-- Base ERP
CREATE DATABASE talan_erp
    WITH OWNER = talan
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8';

-- Donner tous les droits à l'utilisateur talan sur toutes les bases
GRANT ALL PRIVILEGES ON DATABASE talan_hr  TO talan;
GRANT ALL PRIVILEGES ON DATABASE talan_crm TO talan;
GRANT ALL PRIVILEGES ON DATABASE talan_erp TO talan;