import os

extensions = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.html': 'HTML',
    '.css': 'CSS',
    '.bat': 'Batch',
    '.sh': 'Shell',
    '.md': 'Markdown',
    '.json': 'JSON',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.txt': 'Text'
}

ignore_dirs = {'.git', '.pytest_cache', '__pycache__', 'archive', 'stt_env', 'assets', '.gemini', '.system_generated'}

lang_stats = {}
folder_stats = {}
total_files = 0
total_lines = 0
total_code = 0
total_comments = 0
total_blanks = 0

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
    rel = os.path.relpath(root, '.')
    top_folder = rel.split(os.sep)[0] if rel != '.' else 'root'
    
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext in extensions:
            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as fp:
                    lines = fp.readlines()
            except Exception:
                continue
            
            lang = extensions[ext]
            n_lines = len(lines)
            n_blank = sum(1 for line in lines if not line.strip())
            
            if ext in ('.py', '.sh'):
                n_comment = sum(1 for line in lines if line.strip().startswith('#'))
            elif ext in ('.js', '.css'):
                n_comment = sum(1 for line in lines if line.strip().startswith('//') or line.strip().startswith('/*') or line.strip().startswith('*'))
            elif ext == '.html':
                n_comment = sum(1 for line in lines if line.strip().startswith('<!--'))
            elif ext == '.bat':
                n_comment = sum(1 for line in lines if line.strip().lower().startswith(('rem', '::')))
            else:
                n_comment = 0
                
            n_code = n_lines - n_blank - n_comment
            
            total_files += 1
            total_lines += n_lines
            total_code += n_code
            total_comments += n_comment
            total_blanks += n_blank
            
            if lang not in lang_stats:
                lang_stats[lang] = {'files': 0, 'lines': 0, 'code': 0, 'comments': 0, 'blanks': 0}
            lang_stats[lang]['files'] += 1
            lang_stats[lang]['lines'] += n_lines
            lang_stats[lang]['code'] += n_code
            lang_stats[lang]['comments'] += n_comment
            lang_stats[lang]['blanks'] += n_blank
            
            if top_folder not in folder_stats:
                folder_stats[top_folder] = {'files': 0, 'lines': 0, 'code': 0}
            folder_stats[top_folder]['files'] += 1
            folder_stats[top_folder]['lines'] += n_lines
            folder_stats[top_folder]['code'] += n_code

print("=" * 75)
print("  AAROGYA CODEBASE — COMPLETE LINES OF CODE (LOC) AUDIT")
print("=" * 75)
print(f"Total Tracked Files : {total_files}")
print(f"Total Lines of Code : {total_lines:,}")
print(f"Pure Code Lines     : {total_code:,} ({total_code/total_lines*100:.1f}%)")
print(f"Comment / Doc Lines : {total_comments:,} ({total_comments/total_lines*100:.1f}%)")
print(f"Blank / Whitespace  : {total_blanks:,} ({total_blanks/total_lines*100:.1f}%)")

print("\n" + "-" * 75)
print("LOC BREAKDOWN BY LANGUAGE:")
print("-" * 75)
print(f"{'Language':<14} | {'Files':>6} | {'Total Lines':>12} | {'Code Lines':>12} | {'Comments':>9} | {'Blanks':>8}")
print("-" * 75)
for lang, s in sorted(lang_stats.items(), key=lambda x: x[1]['lines'], reverse=True):
    print(f"{lang:<14} | {s['files']:>6} | {s['lines']:>12,} | {s['code']:>12,} | {s['comments']:>9,} | {s['blanks']:>8,}")

print("\n" + "-" * 75)
print("LOC BREAKDOWN BY COMPONENT FOLDER:")
print("-" * 75)
print(f"{'Folder / Module':<24} | {'Files':>6} | {'Total Lines':>12} | {'Code Lines':>12}")
print("-" * 75)
for f, s in sorted(folder_stats.items(), key=lambda x: x[1]['lines'], reverse=True):
    print(f"{f:<24} | {s['files']:>6} | {s['lines']:>12,} | {s['code']:>12,}")
