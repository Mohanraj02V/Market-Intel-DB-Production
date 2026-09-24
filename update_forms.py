import os
import glob
import re

jsx_files = glob.glob('frontend/src/**/*.jsx', recursive=True)

old_border = 'border-slate-300'
new_border = 'border-slate-200'

old_ring = 'focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500'
new_ring = 'focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

old_ring2 = 'focus:ring-indigo-500 focus:border-indigo-500'
new_ring2 = 'focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

old_ring3 = 'focus:ring-2 focus:ring-sky-500/30'
new_ring3 = 'focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

old_ring4 = 'focus:ring-2 focus:ring-indigo-500/20'
new_ring4 = 'focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

for fpath in jsx_files:
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        modified = False
        
        # Safe replace for border-slate-300 in border classes
        if 'border-slate-300' in content:
            content = content.replace('border-slate-300', 'border-slate-200')
            modified = True
            
        if old_ring in content:
            content = content.replace(old_ring, new_ring)
            modified = True
            
        if old_ring2 in content:
            content = content.replace(old_ring2, new_ring2)
            modified = True
            
        if old_ring3 in content:
            content = content.replace(old_ring3, new_ring3)
            modified = True
            
        if old_ring4 in content:
            content = content.replace(old_ring4, new_ring4)
            modified = True
            
        def replace_rounded(match):
            return match.group(0).replace('rounded-lg', 'rounded-xl').replace('rounded-md', 'rounded-xl')
            
        new_content = re.sub(r'className=\"[^\"]*border[^\"]*\"', replace_rounded, content)
        if new_content != content:
            content = new_content
            modified = True
            
        new_content2 = re.sub(r'className=\{[^]*border[^]*\}', replace_rounded, content)
        if new_content2 != content:
            content = new_content2
            modified = True

        if modified:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Updated styles in {fpath}')
    except Exception as e:
        print(f'Error processing {fpath}: {e}')
