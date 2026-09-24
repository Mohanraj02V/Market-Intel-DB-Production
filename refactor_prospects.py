import os

fpath = 'frontend/src/pages/ProspectsPage.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

if 'SearchableSelect' not in content:
    content = content.replace("import { Building2", "import SearchableSelect from '../components/common/SearchableSelect';\nimport { Building2")

old_select = '''<select
              className="w-64 px-3 py-2 border border-slate-200 rounded-xl text-sm bg-white focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-colors"
              value={marketEventFilter}
              onChange={(e) => {
                setMarketEventFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Market Events</option>
              {(!marketEventsList || marketEventsList.length === 0) && (
                <option value="none" disabled>No events created yet</option>
              )}
              {marketEventsList && marketEventsList.map(event => (
                <option key={event.id} value={event.id}>{event.event_title}</option>
              ))}
            </select>'''

new_select = '''<div className="w-64"><SearchableSelect
              value={marketEventFilter}
              onChange={(val) => {
                setMarketEventFilter(val);
                setPage(1);
              }}
              placeholder="All Market Events"
              options={[
                {value: '', label: 'All Market Events'},
                ...((marketEventsList || []).map(event => ({value: event.id, label: event.event_title})))
              ]}
            /></div>'''

content = content.replace(old_select, new_select)

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated ProspectsPage.jsx')
