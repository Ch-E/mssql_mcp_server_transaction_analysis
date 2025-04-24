import os
from anthropic import Anthropic
import pandas as pd
import json
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

def get_claude_api_key() -> str:
    """Get Claude API key from environment or prompt user."""
    load_dotenv()
    api_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not api_key:
        # Try to get API key from Claude's API
        try:
            response = requests.get('https://api.anthropic.com/v1/keys', 
                                 headers={'Authorization': f'Bearer {os.getenv("ANTHROPIC_API_KEY")}'})
            if response.status_code == 200:
                api_key = response.json().get('api_key')
                # Save to .env file
                with open('.env', 'a') as f:
                    f.write(f'\nANTHROPIC_API_KEY={api_key}')
                return api_key
        except Exception as e:
            print(f"Error getting API key: {e}")
            return None
    
    return api_key

class ClaudeSQLAssistant:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_claude_api_key()
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = Anthropic(api_key=self.api_key)
        self.table_info = {}

    def update_table_info(self, table_info: Dict[str, List[str]]):
        """Update the table and column information for Claude to use."""
        self.table_info = table_info

    def generate_sql_query(self, natural_language_query: str) -> str:
        """Convert natural language to SQL query using Claude."""
        if not self.table_info:
            raise ValueError("No table information available. Please call update_table_info first.")
            
        system_prompt = f"""You are an expert SQL developer specializing in Microsoft SQL Server (MSSQL). Convert the user's natural language query into a valid MSSQL query.

Available tables and their columns:
{json.dumps(self.table_info, indent=2)}

IMPORTANT: You can ONLY use the tables listed above. If the user asks about tables not in this list, you must inform them that the table doesn't exist.

Rules for MSSQL queries:
1. Always use Microsoft SQL Server (T-SQL) syntax
2. Use TOP instead of LIMIT for limiting results (e.g., SELECT TOP 1000)
3. Always include table names in column references (e.g., table.column)
4. Use proper JOIN syntax (INNER JOIN, LEFT JOIN, etc.)
5. Use square brackets [] for table and column names with spaces or special characters
6. Use proper date/time functions (GETDATE(), DATEADD, etc.)
7. Handle NULL values with IS NULL or IS NOT NULL
8. Use proper string concatenation with + operator
9. Use proper comparison operators (<> for not equal)
10. Always include error handling with TRY/CATCH blocks
11. Return ONLY the SQL query, no explanations or comments
12. Ensure the query is syntactically correct for MSSQL
13. If the user asks about a table that doesn't exist, return: "ERROR: Table '[table_name]' does not exist in the database."

Example valid MSSQL query:
SELECT TOP 1000 [TableName].[Column1], [TableName].[Column2]
FROM [TableName]
WHERE [TableName].[Column1] IS NOT NULL
ORDER BY [TableName].[Column1] DESC;"""

        try:
            response = self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1000,
                temperature=0,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": natural_language_query}
                ]
            )
            
            # Clean up the response to ensure it's a valid SQL query
            sql_query = response.content[0].text.strip()
            
            # Remove any non-SQL content (like explanations or markdown)
            if "```sql" in sql_query:
                sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
            elif "```" in sql_query:
                sql_query = sql_query.split("```")[1].split("```")[0].strip()
            
            # Check if the response is an error message
            if sql_query.startswith("ERROR:"):
                raise ValueError(sql_query)
            
            # Ensure the query has a semicolon at the end
            if not sql_query.endswith(';'):
                sql_query += ';'
                
            return sql_query
            
        except Exception as e:
            print(f"Error generating SQL query: {e}")
            raise

    def analyze_results(self, query: str, results: List[Dict]) -> str:
        """Analyze query results using Claude."""
        if not results:
            return "No results found for analysis."

        # Convert results to a more readable format
        df = pd.DataFrame(results)
        summary = df.describe().to_string()
        
        system_prompt = """You are a data analyst. Analyze the query results and provide insights.
Focus on:
1. Key findings and patterns
2. Statistical significance
3. Potential business implications
4. Data quality observations
5. Recommendations for further analysis"""

        response = self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            temperature=0,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Query: {query}\n\nResults Summary:\n{summary}\n\nFull Results:\n{json.dumps(results, indent=2)}"}
            ]
        )
        
        return response.content[0].text 