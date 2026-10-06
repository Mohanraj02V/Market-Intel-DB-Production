import React, { useState } from 'react';
import { Building2, User, MapPin, Link as LinkIcon, AlertCircle, Briefcase } from 'lucide-react';
import { Link } from 'react-router-dom';

const ShareholderStructureTree = ({ prospect }) => {
  const [activeTab, setActiveTab] = useState('Company'); // 'Company' | 'Individual'
  
  if (!prospect || !prospect.shareholdings) return null;

  const companyHolders = prospect.shareholdings.filter(s => s.holder_type === 'Company');
  const individualHolders = prospect.shareholdings.filter(s => s.holder_type === 'Individual');

  const CompanyCard = ({ company, glow = false }) => (
    <div className={`relative p-5 rounded-xl border ${glow ? 'bg-slate-900 border-indigo-500 shadow-[0_0_20px_rgba(99,102,241,0.4)]' : 'bg-slate-800/80 border-slate-700/50 hover:bg-slate-800'} transition-all`}>
      {glow && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-wider whitespace-nowrap">
          Selected Prospect Focus
        </div>
      )}
      <div className="text-center">
        <h3 className="text-lg font-bold text-white mb-1">{company.company_name}</h3>
        <div className="text-xs text-slate-400 flex items-center justify-center gap-1.5 mb-4">
          <MapPin size={12} /> {company.country_head_office || 'N/A'} &bull; {company.primary_industries || 'N/A'}
        </div>
      </div>
    </div>
  );

  const ShareholderCard = ({ shareholder }) => {
    const isCompany = shareholder.holder_type === 'Company';
    return (
      <div className="block p-4 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-slate-500 transition-all group relative text-center">
        {isCompany && shareholder.company && (
          <Link to={`/prospects/${shareholder.company}`} className="absolute inset-0 z-0"></Link>
        )}
        <div className="flex justify-center mb-3 relative z-10">
          <span className={`text-[12px] font-bold px-3 py-1 rounded-full ${isCompany ? 'bg-indigo-600' : 'bg-emerald-600'} text-white tracking-wider flex items-center gap-1`}>
            {isCompany ? <Building2 size={12} /> : <User size={12} />}
            {shareholder.share_percentage}%
          </span>
        </div>
        <h4 className="text-sm font-bold text-slate-200 group-hover:text-white mb-1 truncate relative z-10 pointer-events-none">
          {isCompany ? shareholder.company_name : shareholder.individual_name}
        </h4>
        <div className="text-xs text-slate-500 truncate relative z-10 pointer-events-none">
          {isCompany ? 'Corporate Shareholder' : 'Individual Shareholder'}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-[#1a1f2e] rounded-xl overflow-hidden p-8 font-sans">
      <div className="flex justify-center mb-8 relative z-10">
        <div className="inline-flex bg-slate-800/80 rounded-xl p-1.5 border border-slate-700 shadow-sm backdrop-blur-sm">
          <button
            onClick={() => setActiveTab('Company')}
            className={`px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2 ${activeTab === 'Company' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'}`}
          >
            <Building2 size={16} /> Company Shareholders ({companyHolders.length})
          </button>
          <button
            onClick={() => setActiveTab('Individual')}
            className={`px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center gap-2 ${activeTab === 'Individual' ? 'bg-emerald-600 text-white shadow-lg' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'}`}
          >
            <User size={16} /> Individual Shareholders ({individualHolders.length})
          </button>
        </div>
      </div>

      <div className="flex flex-col items-center">
        {/* Top Level: Shareholders */}
        <div className="flex flex-row justify-center flex-wrap gap-6 relative z-10 w-full pb-2">
          {activeTab === 'Company' ? (
            companyHolders.length > 0 ? (
              companyHolders.map(sh => (
                <div key={sh.id} className="w-64 shrink-0">
                  <ShareholderCard shareholder={sh} />
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 italic border border-slate-700/50 rounded-xl px-6 py-3 border-dashed">
                No Corporate Shareholders found.
              </div>
            )
          ) : (
            individualHolders.length > 0 ? (
              individualHolders.map(sh => (
                <div key={sh.id} className="w-64 shrink-0">
                  <ShareholderCard shareholder={sh} />
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 italic border border-slate-700/50 rounded-xl px-6 py-3 border-dashed">
                No Individual Shareholders found.
              </div>
            )
          )}
        </div>

        {/* Vertical Line down to Current Focus */}
        {((activeTab === 'Company' && companyHolders.length > 0) || (activeTab === 'Individual' && individualHolders.length > 0)) && (
          <div className="h-12 w-px bg-slate-600/50 my-2 relative border-l border-dashed border-slate-500"></div>
        )}

        {/* Bottom Level: Current Focus */}
        <div className="relative z-10 w-full max-w-md">
          <CompanyCard company={prospect} glow={true} />
        </div>

      </div>
    </div>
  );
};

export default ShareholderStructureTree;
