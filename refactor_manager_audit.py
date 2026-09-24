import os

fpath = 'frontend/src/pages/ManagerAuditPage.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

if 'SearchableSelect' not in content:
    content = content.replace("import { Calendar, UserCircle,", "import SearchableSelect from '../components/common/SearchableSelect';\nimport { Calendar, UserCircle,")

old_select1 = '''<select
                          className="bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 p-2 font-medium"
                          value={selectedPreUserId}
                          onChange={(e) => setSelectedPreUserId(e.target.value)}
                        >
                          {preSamples.map(sg => (
                            <option key={sg.pre_user_id} value={sg.pre_user_id}>{sg.pre_name}</option>
                          ))}
                        </select>'''

new_select1 = '''<div className="w-48"><SearchableSelect
                          value={selectedPreUserId}
                          onChange={(val) => setSelectedPreUserId(val)}
                          options={preSamples.map(sg => ({value: sg.pre_user_id, label: sg.pre_name}))}
                        /></div>'''

old_select2 = '''<select
                          className="bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 p-2 font-medium"
                          value={selectedLqUserId}
                          onChange={(e) => setSelectedLqUserId(e.target.value)}
                        >
                          {lqSamples.map(sg => (
                            <option key={sg.lq_user_id} value={sg.lq_user_id}>{sg.lq_name}</option>
                          ))}
                        </select>'''

new_select2 = '''<div className="w-48"><SearchableSelect
                          value={selectedLqUserId}
                          onChange={(val) => setSelectedLqUserId(val)}
                          options={lqSamples.map(sg => ({value: sg.lq_user_id, label: sg.lq_name}))}
                        /></div>'''

content = content.replace(old_select1, new_select1).replace(old_select2, new_select2)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated ManagerAuditPage.jsx')
