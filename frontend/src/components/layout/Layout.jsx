import React from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { LogOut, Users, Calendar, Activity, ClipboardList, UserCircle, Mail, LayoutDashboard } from 'lucide-react';
import { logout } from '../../features/auth/authSlice';
import NotificationCenter from './NotificationCenter';

const Layout = () => {
  const { user } = useSelector((state) => state.auth);
  const unreadCount = useSelector((state) => state.inbox.unreadCount);
  const dispatch = useDispatch();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    dispatch(logout());
    navigate('/login');
  };

  const navItems = [];

  if (user?.role === 'PRE') {
    navItems.push(
      { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/prospects', label: 'Prospects', icon: Users },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/pre-tasks', label: 'Tasks', icon: ClipboardList }
    );
  }

  if (user?.is_superuser) {
    navItems.push(
      { path: '/users', label: 'User Management', icon: Users }
    );
  } else if (user?.role === 'LQ') {
    navItems.push(
      { 
        path: '/lq-pipeline', 
        label: 'Lead Qualifier Pipeline', 
        icon: Activity,
        subItems: [
          { path: '/lq-pipeline', label: 'All Prospects', exact: true },
          { path: '/lq-pipeline/pending', label: 'Verification Pending', exact: true },
          { path: '/lq-pipeline/verified', label: 'Outreached', exact: true },
          { path: '/lq-pipeline/issued', label: 'Issued Task to PRE', exact: true },
        ]
      },
      { path: '/calendar', label: 'Calendar', icon: Calendar },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/inbox', label: 'Inbox', icon: Mail, badge: unreadCount > 0 ? unreadCount : null }
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 sticky top-0 h-screen flex flex-col shrink-0 z-50">
        <div className="h-16 flex items-center px-6 border-b border-slate-200 shrink-0">
          <span className="text-xl font-black text-indigo-700 tracking-tight">
            MarketIntel <span className="font-light text-slate-800">DB</span>
          </span>
        </div>
        
        <nav className="flex-1 overflow-y-auto py-6 px-3 space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            
            return (
              <div key={item.path} className="group space-y-1">
                <Link
                  to={item.path}
                  className={`flex items-center px-3 py-2.5 text-sm font-medium rounded-xl transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <div className="relative mr-3">
                    <Icon className={`w-5 h-5 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                    {item.badge && (
                      <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 bg-sky-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 shadow-sm">
                        {item.badge > 999 ? '999+' : item.badge}
                      </span>
                    )}
                  </div>
                  {item.label}
                </Link>

                {item.subItems && (
                  <div className="hidden group-hover:block pl-11 pr-3 space-y-1 mt-1 mb-2">
                    {item.subItems.map(sub => {
                      const isSubActive = sub.exact 
                        ? location.pathname === sub.path 
                        : location.pathname.startsWith(sub.path);
                      return (
                        <Link
                          key={sub.path}
                          to={sub.path}
                          className={`block px-3 py-2 text-xs font-medium rounded-lg transition-colors ${
                            isSubActive
                              ? 'bg-indigo-50 text-indigo-700 font-bold'
                              : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                          }`}
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
          <div className="p-4 border-t border-slate-200 shrink-0 bg-slate-50/50">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1">
                {user.role === 'LQ' && (
                  <div className="mr-1">
                    <NotificationCenter />
                  </div>
                )}
                <button
                  onClick={handleLogout}
                  className="p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 rounded-lg transition-colors"
                  title="Logout"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex flex-col">
              <div className="text-sm font-medium text-slate-900 flex items-center gap-2">
                <span className="font-bold bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded-md text-[10px] uppercase tracking-wider">
                  {user.role}
                </span>
                <span className="truncate font-semibold">{user.first_name} {user.last_name}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1 font-medium">
                {user.role === 'PRE' ? 'Prospect Research Engineer' : 'Lead Qualifier'}
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 h-screen overflow-y-auto bg-slate-50">
        <div className={['/dashboard', '/calendar'].includes(location.pathname) ? 'h-full' : 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full'}>
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
