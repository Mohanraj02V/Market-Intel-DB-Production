import os
import re

fpath = 'frontend/src/components/prospects/ProspectForm.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add import
if 'SearchableSelect' not in content:
    content = content.replace("import { toast } from 'react-toastify';", "import { toast } from 'react-toastify';\nimport SearchableSelect from '../common/SearchableSelect';")

# 1. Company Structure
old_cs = '''<select name="company_structure" value={formData.company_structure} onChange={handleChange} className={w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all }>
                  <option value="Parent">Parent Organization (Ultimate Holding / HQ)</option>
                  <option value="Branch">Branch Office (Local Operational Branch)</option>
                  <option value="Subsidiary">Subsidiary Company (Owned Subsidiary / JV)</option>
                </select>'''
new_cs = '''<SearchableSelect 
                  value={formData.company_structure} 
                  onChange={(val) => setFormData(prev => ({...prev, company_structure: val}))}
                  options={[
                    { value: 'Parent', label: 'Parent Organization (Ultimate Holding / HQ)' },
                    { value: 'Branch', label: 'Branch Office (Local Operational Branch)' },
                    { value: 'Subsidiary', label: 'Subsidiary Company (Owned Subsidiary / JV)' }
                  ]}
                />'''
content = content.replace(old_cs, new_cs)

# 2. Operational Status
old_os = '''<select name="operational_status" value={formData.operational_status} onChange={handleChange} className={w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none transition-all }>
                  <option value="Active">Active</option>
                  <option value="Inactive">Inactive</option>
                  <option value="Permanently Closed">Permanently Closed</option>
                  <option value="Acquired">Acquired</option>
                  <option value="Merged">Merged</option>
                </select>'''
new_os = '''<SearchableSelect 
                  value={formData.operational_status} 
                  onChange={(val) => setFormData(prev => ({...prev, operational_status: val}))}
                  options={[
                    { value: 'Active', label: 'Active' },
                    { value: 'Inactive', label: 'Inactive' },
                    { value: 'Permanently Closed', label: 'Permanently Closed' },
                    { value: 'Acquired', label: 'Acquired' },
                    { value: 'Merged', label: 'Merged' }
                  ]}
                />'''
content = content.replace(old_os, new_os)

# 3. Parent Companies (Inside Map)
old_parent = '''<select value={parent} onChange={(e) => handleParentChange(index, e.target.value)} className="flex-1 rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm">
                      <option value="">Select a parent company...</option>
                      {parentOptions.map(opt => (
                        <option key={opt.id} value={opt.id}>{opt.company_name} ({opt.country_head_office})</option>
                      ))}
                    </select>'''
new_parent = '''<div className="flex-1"><SearchableSelect 
                      value={parent}
                      onChange={(val) => handleParentChange(index, val)}
                      placeholder="Select a parent company..."
                      options={parentOptions.map(opt => ({ value: opt.id, label: f"{opt.company_name} ({opt.country_head_office})" }))}
                    /></div>'''
content = content.replace(old_parent, new_parent.replace('f"', '').replace(')"', ')')) # Fix f-string python to JS template literal

# 4. Status Target
old_target = '''<select name="status_target" value={formData.status_target} onChange={handleChange} className="w-full md:w-1/2 rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm">
                  <option value="">Select target company...</option>
                  {targetOptions.map(opt => (
                    <option key={opt.id} value={opt.id}>{opt.company_name}</option>
                  ))}
                </select>'''
new_target = '''<div className="w-full md:w-1/2"><SearchableSelect 
                  value={formData.status_target}
                  onChange={(val) => setFormData(prev => ({...prev, status_target: val}))}
                  placeholder="Select target company..."
                  options={targetOptions.map(opt => ({ value: opt.id, label: opt.company_name }))}
                /></div>'''
content = content.replace(old_target, new_target)

# 5. Market Events
old_me = '''<select 
                    className="w-full rounded-xl border-slate-200 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm py-2 px-3 border bg-white text-slate-900"
                    onChange={(e) => {
                      const id = parseInt(e.target.value);
                      if (!isNaN(id)) handleMarketEventToggle(id);
                      e.target.value = '';
                    }}
                    defaultValue=""
                  >
                    <option value="" disabled>+ Select an event to add...</option>
                    {(!marketEventsList || marketEventsList.length === 0) && (
                      <option value="none" disabled>No events created yet</option>
                    )}
                    {marketEventsList && marketEventsList.map(event => (
                      <option 
                        key={event.id} 
                        value={event.id}
                        disabled={formData.market_event_ids.includes(event.id)}
                      >
                        {event.event_title} {formData.market_event_ids.includes(event.id) ? '(Added)' : ''}
                      </option>
                    ))}
                  </select>'''
new_me = '''<SearchableSelect 
                    value=""
                    onChange={(val) => {
                      const id = parseInt(val);
                      if (!isNaN(id)) handleMarketEventToggle(id);
                    }}
                    placeholder="+ Select an event to add..."
                    options={
                      (!marketEventsList || marketEventsList.length === 0) 
                        ? [{ value: 'none', label: 'No events created yet' }] 
                        : marketEventsList.filter(e => !formData.market_event_ids.includes(e.id)).map(e => ({ value: e.id, label: e.event_title }))
                    }
                  />'''
content = content.replace(old_me, new_me)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated ProspectForm.jsx with SearchableSelect')
