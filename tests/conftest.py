# tests/conftest.py
import pytest
import os
import pyodbc

def get_connection_string(config):
    """Create a connection string for pyodbc."""
    return f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={config['server']};DATABASE={config['database']};UID={config['user']};PWD={config['password']}"

@pytest.fixture(scope="session")
def mssql_connection():
    """Create a test database connection."""
    try:
        config = {
            "server": os.getenv("MSSQL_SERVER", "localhost"),
            "user": os.getenv("MSSQL_USER", "sa"),
            "password": os.getenv("MSSQL_PASSWORD", "testpassword"),
            "database": os.getenv("MSSQL_DATABASE", "test_db")
        }
        
        connection = pyodbc.connect(get_connection_string(config))
        
        # Create a test table
        cursor = connection.cursor()
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'test_table')
            CREATE TABLE test_table (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name VARCHAR(255),
                value INT
            )
        """)
        connection.commit()
        
        yield connection
        
        # Cleanup
        cursor.execute("DROP TABLE IF EXISTS test_table")
        connection.commit()
        cursor.close()
        connection.close()
            
    except pyodbc.Error as e:
        pytest.fail(f"Failed to connect to SQL Server: {e}")

@pytest.fixture(scope="session")
def mssql_cursor(mssql_connection):
    """Create a test cursor."""
    cursor = mssql_connection.cursor()
    yield cursor
    cursor.close()