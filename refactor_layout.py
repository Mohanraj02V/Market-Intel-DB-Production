import os
import re

fpath = 'frontend/src/components/layout/Layout.jsx'

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Add SearchableSelect import if missing
if 'SearchableSelect' not in content:
    content = content.replace("import { LogOut", "import SearchableSelect from '../common/SearchableSelect';\nimport { LogOut")

# Replace timezone select in Settings
old_tz = '''<select 
                  value={selectedTimezone} 
                  onChange={e => setSelectedTimezone(e.target.value)}
                  className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >'''
new_tz = '''<SearchableSelect 
                  value={selectedTimezone} 
                  onChange={(val) => setSelectedTimezone(val)}
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
# Strip out old options
import re
content = re.sub(r'<select[\s\S]*?className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"[\s\S]*?</select>', new_tz, content)

# Now rebuild the sidebar
sidebar_start = content.find('<aside className="w-64 bg-white border-r border-slate-200 sticky top-0 h-screen flex flex-col shrink-0 z-50">')
sidebar_end = content.find('</aside>') + 8

new_sidebar = '''<aside className="w-64 bg-blue-600 sticky top-0 h-screen flex flex-col shrink-0 z-50 text-white">
        <div className="h-20 flex items-center px-6 shrink-0">
          <span className="text-2xl font-black text-white tracking-tight">
            MarketIntel <span className="font-light text-blue-200">DB</span>
          </span>
        </div>
        
        <nav className="flex-1 overflow-y-auto py-4 pl-4 pr-0 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            
            return (
              <div key={item.path} className="group space-y-1">
                <Link
                  to={item.path}
                  className={lex items-center px-4 py-3.5 text-sm font-bold transition-all }
                >
                  <div className="relative mr-4">
                    <Icon className={w-5 h-5 } />
                    {item.badge && (
                      <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 shadow-sm">
                        {item.badge > 999 ? '999+' : item.badge}
                      </span>
                    )}
                  </div>
                  {item.label}
                </Link>

                {item.subItems && (
                  <div className="hidden group-hover:block pl-12 pr-4 space-y-1 mt-1 mb-2">
                    {item.subItems.map(sub => {
                      const isSubActive = sub.exact 
                        ? location.pathname === sub.path 
                        : location.pathname.startsWith(sub.path);
                      return (
                        <Link
                          key={sub.path}
                          to={sub.path}
                          className={lock px-4 py-2.5 text-xs font-bold rounded-l-full transition-all }
                        >
                          {sub.label}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {user && (
          <div className="p-4 bg-blue-700/30 shrink-0">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-1">
                {user.role === 'LQ' && (
                  <div className="mr-1">
                    <NotificationCenter />
                  </div>
                )}
                <button
                  onClick={() => { setSelectedTimezone(user?.timezone || 'UTC'); setIsSettingsOpen(true); }}
                  className="p-1.5 text-blue-200 hover:bg-blue-500 hover:text-white rounded-lg transition-colors"
                  title="Settings"
                >
                  <Settings className="h-4 w-4" />
                </button>
                <button
                  onClick={handleLogout}
                  className="p-1.5 text-blue-200 hover:bg-blue-500 hover:text-white rounded-lg transition-colors"
                  title="Logout"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex flex-col">
              <div className="text-sm font-medium text-white flex items-center gap-2">
                <span className="font-bold bg-blue-500 text-white px-1.5 py-0.5 rounded-md text-[10px] uppercase tracking-wider">
                  {user.role}
                </span>
                <span className="truncate font-bold">{user.first_name} {user.last_name}</span>
              </div>
              <div className="text-xs text-blue-200 mt-1 font-medium">
                {user.role === 'PRE'
                  ? 'Prospect Research Engineer'
                  : user.role === 'LQ'
                  ? 'Lead Qualifier'
                  : user.role === 'MANAGER'
                  ? 'Manager'
                  : user.is_superuser
                  ? 'Administrator'
                  : user.role}
              </div>
            </div>
          </div>
        )}
      </aside>'''

content = content[:sidebar_start] + new_sidebar + content[sidebar_end:]

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated Layout.jsx with new sidebar design')
