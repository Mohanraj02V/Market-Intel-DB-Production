import os
import re

fpath = 'frontend/src/components/users/UserForm.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add import
if 'SearchableSelect' not in content:
    content = content.replace("import { X } from 'lucide-react';", "import { X } from 'lucide-react';\nimport SearchableSelect from '../common/SearchableSelect';")

old_role = '''<select name="role" value={formData.role} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm">
                  <option value="PRE">Prospect Research Engineer (PRE)</option>
                  <option value="LQ">Lead Qualifier (LQ)</option>
                  <option value="MANAGER">Manager</option>
                </select>'''
new_role = '''<SearchableSelect 
                  value={formData.role} 
                  onChange={(val) => setFormData(prev => ({...prev, role: val}))}
                  options={[
                    { value: 'PRE', label: 'Prospect Research Engineer (PRE)' },
                    { value: 'LQ', label: 'Lead Qualifier (LQ)' },
                    { value: 'MANAGER', label: 'Manager' }
                  ]}
                />'''
content = content.replace(old_role, new_role)

old_tz = '''<select name="timezone" value={formData.timezone} onChange={handleChange} className="mt-1 block w-full rounded-xl bg-white border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-sm px-4 py-3 text-slate-900 transition-all outline-none shadow-sm">
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">Eastern Time (US & Canada)</option>
                  <option value="America/Chicago">Central Time (US & Canada)</option>
                  <option value="America/Denver">Mountain Time (US & Canada)</option>
                  <option value="America/Los_Angeles">Pacific Time (US & Canada)</option>
                  <option value="Europe/London">London</option>
                  <option value="Europe/Paris">Paris</option>
                  <option value="Asia/Dubai">Dubai</option>
                  <option value="Asia/Kolkata">India (IST)</option>
                  <option value="Asia/Singapore">Singapore</option>
                  <option value="Australia/Sydney">Sydney</option>
                </select>'''
new_tz = '''<SearchableSelect 
                  value={formData.timezone} 
                  onChange={(val) => setFormData(prev => ({...prev, timezone: val}))}
                  options={[
                    { value: 'UTC', label: 'UTC' },
                    { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
                    { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
                    { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
                    { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
                    { value: 'Europe/London', label: 'London' },
                    { value: 'Europe/Paris', label: 'Paris' },
                    { value: 'Asia/Dubai', label: 'Dubai' },
                    { value: 'Asia/Kolkata', label: 'India (IST)' },
                    { value: 'Asia/Singapore', label: 'Singapore' },
                    { value: 'Australia/Sydney', label: 'Sydney' }
                  ]}
                />'''
content = content.replace(old_tz, new_tz)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated UserForm.jsx with SearchableSelect')
