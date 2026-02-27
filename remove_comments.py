import os
import io
import tokenize

def remove_comments(source):
    io_obj = io.StringIO(source)
    tokens = tokenize.generate_tokens(io_obj.readline)
    cleaned_tokens = []
    
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        # Also remove trailing whitespace at the end of a line where a comment was removed
        # but untokenize does not handle formatting perfectly.
        # It's better to preserve the original token tuple except for comments.
        cleaned_tokens.append(tok)
        
    try:
        return tokenize.untokenize(cleaned_tokens)
    except Exception as e:
        print(f"Error untokenizing: {e}")
        return source

def process_file(filepath):
    print(f"Processing {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    
    new_source = remove_comments(source)
    
    # Remove empty lines left by comments
    lines = new_source.split('\n')
    final_lines = [line.rstrip() for line in lines]
    final_source = '\n'.join(final_lines)
    
    # Simple regex to remove completely empty lines that might have been left
    import re
    final_source = re.sub(r'\n\s*\n', '\n\n', final_source) # compress multiple blank lines

    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(final_source)

python_files = [
    'backend/analytics.py',
    'backend/data_fetcher.py',
    'backend/database.py',
    'backend/main.py',
    'backend/models.py',
    'frontend/app.py',
    'run.bat'
]

for pf in python_files:
    if os.path.exists(pf):
        if pf.endswith('.py'):
            process_file(pf)
        elif pf.endswith('.bat'):
            with open(pf, 'r', encoding='utf-8') as f:
                content = f.read()
            # remove :: comments and rem comments
            import re
            content = re.sub(r'(?m)^\s*::.*$', '', content)
            content = re.sub(r'(?m)^\s*rem\s+.*$', '', content, flags=re.IGNORECASE)
            with open(pf, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Processed {pf}")
