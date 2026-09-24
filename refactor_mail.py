import os

fpath = 'frontend/src/pages/MailSettingsPage.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

if 'SearchableSelect' not in content:
    content = content.replace("import { Mail, Shield,", "import SearchableSelect from '../components/common/SearchableSelect';\nimport { Mail, Shield,")

old_select1 = '''<select name="smtp_security" value={formData.smtp_security || 'TLS'} onChange={handleChange} className="mt-1 block w-full border border-gray-300 rounded p-2">
                                          <option value="NONE">None</option>
                                          <option value="TLS">TLS</option>
                                          <option value="SSL">SSL</option>
                                        </select>'''

new_select1 = '''<SearchableSelect
                                          value={formData.smtp_security || 'TLS'}
                                          onChange={(val) => setFormData(prev => ({...prev, smtp_security: val}))}
                                          options={[
                                            {value: 'NONE', label: 'None'},
                                            {value: 'TLS', label: 'TLS'},
                                            {value: 'SSL', label: 'SSL'}
                                          ]}
                                        />'''

old_select2 = '''<select name="imap_security" value={formData.imap_security || 'SSL'} onChange={handleChange} className="mt-1 block w-full border border-gray-300 rounded p-2">
                                          <option value="NONE">None</option>
                                          <option value="TLS">TLS</option>
                                          <option value="SSL">SSL</option>
                                        </select>'''

new_select2 = '''<SearchableSelect
                                          value={formData.imap_security || 'SSL'}
                                          onChange={(val) => setFormData(prev => ({...prev, imap_security: val}))}
                                          options={[
                                            {value: 'NONE', label: 'None'},
                                            {value: 'TLS', label: 'TLS'},
                                            {value: 'SSL', label: 'SSL'}
                                          ]}
                                        />'''

content = content.replace(old_select1, new_select1).replace(old_select2, new_select2)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated MailSettingsPage.jsx')
