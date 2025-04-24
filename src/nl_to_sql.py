import re
from typing import Dict, List, Optional

class NaturalLanguageToSQL:
    def __init__(self):
        self.table_info: Dict[str, List[str]] = {}
        self.common_patterns = {
            r'list all (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
            r'show all (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
            r'get all (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
            r'count (.*) in (.*)': lambda match: f"SELECT COUNT(*) FROM {self._format_table_name(match.group(2))}",
            r'what are the (.*) in (.*)': lambda match: f"SELECT DISTINCT {self._format_column_name(match.group(1))} FROM {self._format_table_name(match.group(2))}",
            r'how many (.*) in (.*)': lambda match: f"SELECT COUNT(*) FROM {self._format_table_name(match.group(2))}",
            r'list (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
            r'show (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
            r'get (.*) from (.*)': lambda match: self._format_select_query(match.group(1), match.group(2)),
        }

    def _format_table_name(self, table_name: str) -> str:
        """Format table name for SQL query."""
        # Clean the table name
        table_name = table_name.strip().lower()
        
        # Find the best matching table name from our known tables
        best_match = None
        best_score = 0
        
        for known_table in self.table_info.keys():
            # Simple matching: check if the input is a substring of the table name
            # or if the table name is a substring of the input
            score = 0
            if table_name in known_table.lower():
                score = len(table_name) / len(known_table)
            elif known_table.lower() in table_name:
                score = len(known_table) / len(table_name)
            
            if score > best_score:
                best_score = score
                best_match = known_table
        
        # If we found a good match, use it
        if best_match and best_score > 0.5:
            return best_match
        
        # If no good match found, try to find a table that contains the input
        for known_table in self.table_info.keys():
            if table_name in known_table.lower():
                return known_table
        
        # If still no match, return the original table name with proper formatting
        return f'[{table_name}]'

    def _format_column_name(self, column_name: str) -> str:
        """Format column name for SQL query."""
        # Clean the column name
        column_name = column_name.strip().lower()
        
        # If the column name is "all" or empty, return *
        if column_name == 'all' or not column_name:
            return '*'
        
        # Find the best matching column name from our known columns
        best_match = None
        best_score = 0
        
        for table_name, columns in self.table_info.items():
            for known_column in columns:
                # Simple matching: check if the input is a substring of the column name
                # or if the column name is a substring of the input
                score = 0
                if column_name in known_column.lower():
                    score = len(column_name) / len(known_column)
                elif known_column.lower() in column_name:
                    score = len(known_column) / len(column_name)
                
                if score > best_score:
                    best_score = score
                    best_match = known_column
        
        # If we found a good match, use it
        if best_match and best_score > 0.5:
            return best_match
        
        # If no good match found, return the original column name with proper formatting
        return f'[{column_name}]'

    def _format_select_query(self, columns: str, table: str) -> str:
        """Format a SELECT query with proper column and table names."""
        table_name = self._format_table_name(table)
        
        # If columns is "all" or empty, use *
        if columns.strip().lower() == 'all' or not columns.strip():
            return f"SELECT * FROM {table_name}"
        
        # If we have table info and the table exists, validate columns
        if table_name in self.table_info:
            available_columns = self.table_info[table_name]
            # Split columns by comma and clean them
            requested_columns = [self._format_column_name(col.strip()) for col in columns.split(',')]
            # Filter out invalid columns
            valid_columns = [col for col in requested_columns if col == '*' or col in available_columns]
            if valid_columns:
                return f"SELECT {', '.join(valid_columns)} FROM {table_name}"
        
        # If no valid columns found, use *
        return f"SELECT * FROM {table_name}"

    def update_table_info(self, table_name: str, columns: List[str]):
        """Update the table information for better query generation."""
        self.table_info[table_name] = columns

    def convert_to_sql(self, natural_language: str) -> Optional[str]:
        """Convert natural language to SQL query."""
        natural_language = natural_language.lower().strip()
        
        # Try to match against common patterns
        for pattern, converter in self.common_patterns.items():
            match = re.match(pattern, natural_language)
            if match:
                return converter(match)
        
        # If no pattern matches, try to generate a basic SELECT query
        words = natural_language.split()
        if len(words) >= 3 and words[0] in ['list', 'show', 'get']:
            # Try to extract table name (usually the last word)
            table_name = self._format_table_name(words[-1])
            if table_name in self.table_info:
                # If we have table info, use all columns
                columns = ', '.join(self.table_info[table_name])
                return f"SELECT {columns} FROM {table_name}"
            else:
                # Otherwise use wildcard
                return f"SELECT * FROM {table_name}"
        
        return None

    def get_suggested_query(self, natural_language: str) -> str:
        """Get a suggested SQL query based on the natural language input."""
        sql = self.convert_to_sql(natural_language)
        if sql:
            return sql
        
        # If no conversion is possible, return a helpful message
        return "Could not convert to SQL. Please try one of these formats:\n" + \
               "- List all columns from table_name\n" + \
               "- Show all data from table_name\n" + \
               "- Get count of records in table_name\n" + \
               "- What are the unique values in column_name from table_name" 