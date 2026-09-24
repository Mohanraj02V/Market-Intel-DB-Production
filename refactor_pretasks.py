import os

fpath = 'frontend/src/pages/PreTasksPage.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

if 'SearchableSelect' not in content:
    content = content.replace("import { AlertTriangle", "import SearchableSelect from '../components/common/SearchableSelect';\nimport { AlertTriangle")

old_select = '''<select
              className="bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 p-2 font-medium"
              value={managerUserFilter}
              onChange={(e) => setManagerUserFilter(e.target.value)}
            >
              <option value="ALL">All Users</option>
              {availableUsers.map(u => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>'''

new_select = '''<div className="w-48"><SearchableSelect
              value={managerUserFilter}
              onChange={(val) => setManagerUserFilter(val)}
              options={[{value: 'ALL', label: 'All Users'}, ...availableUsers.map(u => ({value: u, label: u}))]}
            /></div>'''

content = content.replace(old_select, new_select)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated PreTasksPage.jsx')
