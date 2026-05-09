import re
from typing import List, Dict

def split_sql_batches(sql_text: str) -> List[Dict[str, any]]:
    """
    Splits a SQL file into batches using 'GO' as the separator.
    Returns a list of dicts with 'text', 'line_start', 'line_end'.
    """
    lines = sql_text.split('\n')
    batches = []
    current_batch_lines = []
    start_line = 1
    
    # Regex to match 'GO' on a single line, ignoring whitespace and comments
    go_pattern = re.compile(r'^\s*GO\s*(?:--.*)?$', re.IGNORECASE)
    
    for i, line in enumerate(lines):
        line_num = i + 1
        if go_pattern.match(line):
            if current_batch_lines:
                batch_text = '\n'.join(current_batch_lines).strip()
                if batch_text:
                    batches.append({
                        'text': batch_text,
                        'line_start': start_line,
                        'line_end': line_num - 1
                    })
            current_batch_lines = []
            start_line = line_num + 1
        else:
            current_batch_lines.append(line)
            
    if current_batch_lines:
        batch_text = '\n'.join(current_batch_lines).strip()
        if batch_text:
            batches.append({
                'text': batch_text,
                'line_start': start_line,
                'line_end': len(lines)
            })
            
    return batches
