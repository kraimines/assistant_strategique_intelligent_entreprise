"""
ETL Unit Tests — Validates utils and config modules without requiring full databases.

Run with:
    python -m pytest backend/etl/tests/test_etl.py -v
    python -m unittest backend.etl.tests.test_etl
"""

import unittest
import tempfile
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import sys
import os

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.etl import config, utils


class TestConfig(unittest.TestCase):
    """Test configuration module."""

    def test_environment_variables_exist(self):
        """Verify environment variables are read correctly."""
        # Should have defaults, not fail
        self.assertIsNotNone(config.POSTGRES_HOST)
        self.assertIsNotNone(config.POSTGRES_PORT)
        self.assertIsNotNone(config.POSTGRES_USER)

    def test_postgres_connection_string_format(self):
        """Test PostgreSQL connection string format."""
        dsn = config.pg_connection_string("hr")
        self.assertIn("postgresql://", dsn)
        self.assertIn(config.POSTGRES_USER, dsn)
        self.assertIn("talan_hr", dsn)

    def test_postgres_dsn_format(self):
        """Test psycopg2 DSN format."""
        dsn = config.pg_dsn("crm")
        self.assertIn("host=", dsn)
        self.assertIn("dbname=talan_crm", dsn)
        self.assertIn("user=", dsn)

    def test_excel_files_dict_exists(self):
        """Verify EXCEL_FILES dictionary structure."""
        self.assertIn("rh", config.EXCEL_FILES)
        self.assertIn("crm", config.EXCEL_FILES)
        self.assertIn("erp", config.EXCEL_FILES)

    def test_neo4j_configuration(self):
        """Test Neo4j configuration."""
        self.assertIsNotNone(config.NEO4J_URI)
        self.assertIn("bolt://", config.NEO4J_URI)
        self.assertIsNotNone(config.NEO4J_USER)
        self.assertIsNotNone(config.NEO4J_PASSWORD)


class TestUtils(unittest.TestCase):
    """Test utility functions."""

    def test_get_logger(self):
        """Test logger creation."""
        log = utils.get_logger("test")
        self.assertIsNotNone(log)
        self.assertEqual(log.name, "test")

    def test_clean_str_cols(self):
        """Test string column cleaning."""
        df = pd.DataFrame({
            "name": ["  john  ", "jane ", "", None],
            "email": ["a@b.com", "  c@d.com  ", "", ""],
            "id": [1, 2, 3, 4]
        })
        
        df_cleaned = utils.clean_str_cols(df)
        
        # Verify trimming
        self.assertEqual(df_cleaned.loc[0, "name"], "john")
        self.assertEqual(df_cleaned.loc[1, "name"], "jane")
        
        # Verify empty string → None
        self.assertTrue(pd.isna(df_cleaned.loc[2, "name"]))
        self.assertTrue(pd.isna(df_cleaned.loc[2, "email"]))

    def test_coerce_dates(self):
        """Test date coercion."""
        df = pd.DataFrame({
            "hire_date": ["2023-01-15", "2023-02-28", "invalid", None],
            "created_at": ["2024-01-01 10:30", "2024-12-31 23:59", None, None]
        })
        
        df_coerced = utils.coerce_dates(df, ["hire_date", "created_at"])
        
        # Verify first two are valid dates
        self.assertTrue(pd.notna(df_coerced.loc[0, "hire_date"]))
        self.assertTrue(pd.notna(df_coerced.loc[1, "hire_date"]))
        
        # Verify invalid becomes NaT
        self.assertTrue(pd.isna(df_coerced.loc[2, "hire_date"]))

    def test_nullable_float(self):
        """Test float coercion with NULL support."""
        df = pd.DataFrame({
            "salary": ["50000", "75000.50", "invalid", None],
            "bonus": [5000, 10000.25, None, ""]
        })
        
        df_floated = utils.nullable_float(df, ["salary", "bonus"])
        
        # Verify valid conversions
        self.assertEqual(df_floated.loc[0, "salary"], 50000.0)
        self.assertEqual(df_floated.loc[1, "salary"], 75000.50)
        
        # Verify invalid → NaN
        self.assertTrue(pd.isna(df_floated.loc[2, "salary"]))
        self.assertTrue(pd.isna(df_floated.loc[3, "salary"]))

    @patch('backend.etl.utils.psycopg2.connect')
    def test_pg_conn_context_manager(self, mock_connect):
        """Test PostgreSQL context manager."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        with utils.pg_conn("hr") as conn:
            self.assertEqual(conn, mock_conn)
        
        # Verify commit was called on exit
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('backend.etl.utils.psycopg2.connect')
    def test_pg_conn_rollback_on_error(self, mock_connect):
        """Test PostgreSQL context manager rollback on error."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        try:
            with utils.pg_conn("hr") as conn:
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Verify rollback was called
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('backend.etl.utils.psycopg2.connect')
    def test_execute_ddl(self, mock_connect):
        """Test DDL execution."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        ddl = "CREATE TABLE test (id INT PRIMARY KEY);"
        utils.execute_ddl(mock_conn, ddl)
        
        # Verify execute was called
        mock_cursor.execute.assert_called_once_with(ddl)
        mock_cursor.close.assert_called_once()

    def test_read_sheet_missing_file(self):
        """Test read_sheet with missing file."""
        with self.assertRaises(FileNotFoundError):
            utils.read_sheet(Path("/nonexistent/file.xlsx"), "Sheet1")

    def test_read_sheet_creates_dataframe(self):
        """Test read_sheet returns DataFrame."""
        # Create temporary Excel file
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            df_write = pd.DataFrame({
                "id": [1, 2, 3],
                "name": ["A", "B", "C"]
            })
            df_write.to_excel(tmp.name, sheet_name="TestSheet", index=False)
            tmp_path = tmp.name
        
        try:
            df_read = utils.read_sheet(Path(tmp_path), "TestSheet")
            
            # Verify DataFrame structure
            self.assertEqual(len(df_read), 3)
            self.assertIn("id", df_read.columns)
            self.assertIn("name", df_read.columns)
            self.assertEqual(df_read.loc[0, "id"], 1)
            self.assertEqual(df_read.loc[0, "name"], "A")
        finally:
            os.unlink(tmp_path)

    @patch('backend.etl.utils.psycopg2.connect')
    def test_get_row_count(self, mock_connect):
        """Test row count query."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.cursor.return_value = mock_cursor
        
        count = utils.get_row_count(mock_conn, "employees")
        
        self.assertEqual(count, 42)
        # Verify correct query was executed
        call_args = mock_cursor.execute.call_args[0][0]
        self.assertIn("SELECT COUNT(*)", call_args)
        self.assertIn("employees", call_args)

    @patch('backend.etl.utils.psycopg2.connect')
    def test_upsert_dataframe_basic(self, mock_connect):
        """Test DataFrame upsert."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3
        mock_conn.cursor.return_value = mock_cursor
        
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "value": [100, 200, 300]
        })
        
        count = utils.upsert_dataframe(
            mock_conn, df, "test_table", 
            key_columns=["id"], batch_size=10
        )
        
        # Verify at least one execute call for INSERT
        self.assertGreater(mock_cursor.execute.call_count, 0)

    @patch('backend.etl.utils.psycopg2.connect')
    def test_upsert_dataframe_empty(self, mock_connect):
        """Test upsert with empty DataFrame."""
        mock_conn = MagicMock()
        
        df = pd.DataFrame({"id": [], "name": []})
        
        count = utils.upsert_dataframe(mock_conn, df, "test_table", ["id"])
        
        # Should return 0 for empty DataFrame
        self.assertEqual(count, 0)

    @patch('backend.etl.utils.psycopg2.connect')
    def test_upsert_dataframe_batch_processing(self, mock_connect):
        """Test that large DataFrames are processed in batches."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 500
        mock_conn.cursor.return_value = mock_cursor
        
        # Create DataFrame with 1500 rows (3 batches of 500)
        df = pd.DataFrame({
            "id": range(1, 1501),
            "name": [f"User_{i}" for i in range(1, 1501)],
        })
        
        count = utils.upsert_dataframe(
            mock_conn, df, "users", 
            key_columns=["id"], batch_size=500
        )
        
        # Should be called multiple times for batches
        self.assertGreaterEqual(mock_cursor.execute.call_count, 3)


class TestConfigSelfTest(unittest.TestCase):
    """Test config module self-diagnostics."""

    def test_config_self_test_runs(self):
        """Verify config module has self-test capability."""
        # The config module should have pg_connection_string and pg_dsn
        self.assertTrue(callable(config.pg_connection_string))
        self.assertTrue(callable(config.pg_dsn))


class TestIntegration(unittest.TestCase):
    """Integration tests (requires actual PostgreSQL/Neo4j)."""

    @unittest.skip("Requires live database")
    def test_postgres_connection(self):
        """Test actual PostgreSQL connection (requires DB running)."""
        with utils.pg_conn("hr") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            self.assertEqual(result[0], 1)
            cursor.close()

    @unittest.skip("Requires live Neo4j instance")
    def test_neo4j_connection(self):
        """Test actual Neo4j connection (requires DB running)."""
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )
        
        with driver.session() as session:
            result = session.run("RETURN 1 as num")
            value = result.single()
            self.assertEqual(value["num"], 1)
        
        driver.close()


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
