import React, { useState } from 'react';
import { Building2, User, MapPin, Link as LinkIcon, Maximize2, Minimize2, Landmark, HelpCircle } from 'lucide-react';
import { Link } from 'react-router-dom';

const ShareholderStructureTree = ({ prospect }) => {
  const [isFullScreen, setIsFullScreen] = useState(false);
  
  if (!prospect || !prospect.shareholdings) return null;

  const allHolders = prospect.shareholdings;

  const toggleFullScreen = () => {
    setIsFullScreen(!isFullScreen);
  };

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
    const isGov = shareholder.holder_type === 'Government';
    const isOther = shareholder.holder_type === 'Other';
    const isIndividual = shareholder.holder_type === 'Individual';

    let displayType = 'Shareholder';
    if (isCompany) displayType = 'Corporate Shareholder';
    else if (isIndividual) displayType = 'Individual Shareholder';
    else if (isGov) displayType = 'Government Entity';
    else if (isOther) displayType = 'Other Shareholder';

    let displayName = 'Unknown';
    if (isCompany) displayName = shareholder.company_name;
    else if (isIndividual) displayName = shareholder.individual_name;
    else if (isGov) displayName = shareholder.government_entity_name;
    else if (isOther) displayName = shareholder.other_name;

    return (
      <div className="block p-4 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-slate-500 transition-all group relative text-center">
        {isCompany && shareholder.company && (
          <Link to={`/prospects/${shareholder.company}`} className="absolute inset-0 z-0"></Link>
        )}
        <div className="flex justify-center mb-3 relative z-10">
          <span className={`text-[12px] font-bold px-3 py-1 rounded-full ${isCompany ? 'bg-indigo-600' : isGov ? 'bg-amber-600' : isOther ? 'bg-purple-600' : 'bg-emerald-600'} text-white tracking-wider flex items-center gap-1`}>
            {shareholder.share_percentage}%
          </span>
        </div>
        <h4 className="text-sm font-bold text-slate-200 group-hover:text-white mb-1 truncate relative z-10 pointer-events-none">
          {displayName}
        </h4>
        <div className="text-xs text-slate-500 truncate relative z-10 pointer-events-none">
          {displayType}
        </div>
      </div>
    );
  };

  const containerClasses = isFullScreen
    ? "fixed inset-0 z-50 bg-[#1a1f2e] overflow-auto p-8 font-sans"
    : "bg-[#1a1f2e] rounded-xl overflow-hidden p-8 font-sans relative";

  return (
    <div className={containerClasses}>
      <div className="absolute top-4 right-4 z-20">
        <button
          onClick={toggleFullScreen}
          className="p-2 bg-slate-800 text-slate-400 hover:text-white rounded-lg border border-slate-700 hover:border-slate-500 transition-colors"
          title={isFullScreen ? "Exit Full Screen" : "Full Screen View"}
        >
          {isFullScreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
        </button>
      </div>

      <div className="flex justify-center mb-8 relative z-10 pt-4">
        <div className="inline-flex bg-slate-800/80 rounded-xl px-6 py-2.5 border border-slate-700 shadow-sm backdrop-blur-sm text-sm font-bold text-white tracking-wider uppercase">
          All Shareholders ({allHolders.length})
        </div>
      </div>

      <div className="flex flex-col items-center">
        {/* Top Level: Shareholders */}
        <div className="flex flex-row justify-center flex-wrap gap-6 relative z-10 w-full pb-2">
          {allHolders.length > 0 ? (
            allHolders.map(sh => (
              <div key={sh.id} className="w-64 shrink-0">
                <ShareholderCard shareholder={sh} />
              </div>
            ))
          ) : (
            <div className="text-xs text-slate-500 italic border border-slate-700/50 rounded-xl px-6 py-3 border-dashed">
              No Shareholders found.
            </div>
          )}
        </div>

        {/* Vertical Line down to Current Focus */}
        {allHolders.length > 0 && (
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
