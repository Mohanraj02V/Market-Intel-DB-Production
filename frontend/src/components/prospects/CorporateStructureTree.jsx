import React from 'react';
import { Building2, Network, Globe, MapPin, Link as LinkIcon, AlertCircle, Briefcase, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';

const CorporateStructureTree = ({ prospect }) => {

  if (!prospect) return null;

  const parents = prospect.parent_companies_detail || [];
  const children = prospect.child_companies_detail || [];
  const mergedIn = prospect.acquired_or_merged_from_detail || [];
  
  const branches = children.filter(c => c.company_structure === 'Branch');
  const subsidiaries = children.filter(c => c.company_structure === 'Subsidiary');

  // Renders a company card
  const CompanyCard = ({ company, type, glow = false }) => (
    <div className={`relative p-5 rounded-xl border ${glow ? 'bg-slate-900 border-indigo-500 shadow-[0_0_20px_rgba(99,102,241,0.4)]' : 'bg-slate-800/80 border-slate-700/50 hover:bg-slate-800'} transition-all`}>
      {glow && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-wider whitespace-nowrap">
          Selected Prospect Focus
        </div>
      )}
      <div className="text-center">
        <Link to={`/prospects/${company.id}`} className="inline-block hover:opacity-80 transition-opacity">
          <h3 className="text-lg font-bold text-white mb-1">{company.company_name}</h3>
        </Link>
        <div className="text-xs text-slate-400 flex items-center justify-center gap-1.5 mb-4">
          <MapPin size={12} /> {company.country_head_office} &bull; {company.primary_industries}
        </div>
        
        <div className="grid grid-cols-2 gap-4 border-t border-slate-700/50 pt-3">
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Structure</div>
            <div className="text-sm font-medium text-slate-300">{company.company_structure || 'N/A'}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Operational Status</div>
            <div className={`text-sm font-medium ${company.operational_status === 'Active' ? 'text-emerald-400' : 'text-amber-400'}`}>
              {company.operational_status || 'N/A'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const MiniCard = ({ company, badgeLabel, badgeColor }) => (
    <div className={`block p-4 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-slate-500 transition-all group relative ${company.operational_status === 'Inactive' ? 'opacity-70' : ''}`}>
      <Link to={`/prospects/${company.id}`} className="absolute inset-0 z-0"></Link>
      <div className="flex items-center justify-between mb-2 relative z-10">
        <div className="flex flex-wrap gap-2 items-center">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${badgeColor} text-white uppercase tracking-wider`}>
            {badgeLabel}
          </span>
          {company.operational_status && company.operational_status !== 'Active' && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-900/50 text-amber-500 border border-amber-700/50 uppercase tracking-wider">
              {company.operational_status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-slate-400 text-xs shrink-0">
            <MapPin size={10} /> {company.country_head_office}
          </div>
        </div>
      </div>
      <h4 className={`text-sm font-bold text-slate-200 group-hover:text-white mb-1 truncate relative z-10 pointer-events-none ${company.operational_status === 'Inactive' ? 'line-through decoration-slate-500' : ''}`}>{company.company_name}</h4>
      <div className="text-xs text-slate-500 truncate relative z-10 pointer-events-none">{company.primary_industries}</div>
    </div>
  );

  return (
    <div className="bg-[#1a1f2e] rounded-xl overflow-hidden p-8 font-sans">

      {/* Top Level: Parents */}
      <div className="flex flex-col items-center">
        <div className="mb-4 inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-indigo-900/50 bg-indigo-900/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
          <Building2 size={14} /> Parent / Holding Organizations ({parents.length})
        </div>
        
        {parents.length > 0 ? (
          <div className="flex flex-row justify-center gap-6 relative z-10 w-full overflow-x-auto pb-2">
            {parents.map(p => (
              <div key={p.id} className="w-64 shrink-0">
                <MiniCard company={p} badgeLabel="Parent" badgeColor="bg-indigo-600" />
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-500 italic border border-slate-700/50 rounded-xl px-6 py-3 border-dashed">
            No Parent Organization Linked (Operates as Independent / Top-Level Entity)
          </div>
        )}

        {/* Vertical Line down to Current Focus */}
        <div className="h-12 w-px bg-indigo-900/50 my-2 relative"></div>

        {/* Middle Level: Current Focus */}
        <div className="relative z-10 w-full max-w-md">
          <CompanyCard company={prospect} type={prospect.company_structure} glow={true} />
        </div>

        {/* Merger Visualization */}
        {['Acquired', 'Merged'].includes(prospect.operational_status) && prospect.status_target_detail && (
          <div className="flex flex-col items-center mt-6 w-full relative z-10">
            <div className="h-6 border-l-2 border-dashed border-amber-500/50"></div>
            <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/20 border border-amber-500/50 rounded-full text-[10px] font-bold text-amber-400 uppercase tracking-widest my-2">
              <LinkIcon size={12} /> {prospect.operational_status} WITH
            </div>
            <div className="h-6 border-l-2 border-dashed border-amber-500/50 mb-2"></div>
            
            <div className="w-full max-w-sm">
              <div className="relative p-4 rounded-xl bg-amber-900/10 border border-amber-500/30 hover:bg-amber-900/20 transition-all text-center">
                <div className="absolute -top-3 right-4 bg-amber-500 text-white text-[9px] font-bold px-2 py-0.5 rounded uppercase">
                  {prospect.merger_role === 'Target Company' ? 'Acquiring / Entering Company' : 
                   prospect.merger_role === 'Entering Company' ? 'Target Company' : 'Partner Company'}
                </div>
                <Link to={`/prospects/${prospect.status_target_detail.id}`} className="inline-block hover:opacity-80 transition-opacity">
                  <h4 className="text-base font-bold text-slate-200 mb-1">{prospect.status_target_detail.company_name}</h4>
                </Link>
                <div className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                  <MapPin size={10} /> {prospect.status_target_detail.country_head_office} &bull; {prospect.status_target_detail.primary_industries}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Incoming Mergers Visualization */}
        {mergedIn.length > 0 && (
          <div className="flex flex-col items-center mt-6 w-full relative z-10">
            <div className="h-6 border-l-2 border-dashed border-emerald-500/50"></div>
            <div className="flex items-center gap-2 px-3 py-1 bg-emerald-500/20 border border-emerald-500/50 rounded-full text-[10px] font-bold text-emerald-400 uppercase tracking-widest my-2">
              <LinkIcon size={12} /> MERGED COMPANY OWNER SECTOR ({mergedIn.length})
            </div>
            <div className="h-6 border-l-2 border-dashed border-emerald-500/50 mb-2"></div>
            
            <div className="flex flex-wrap justify-center gap-4 w-full max-w-2xl">
              {mergedIn.map(m => (
                <div key={m.id} className="relative p-4 rounded-xl bg-emerald-900/10 border border-emerald-500/30 hover:bg-emerald-900/20 transition-all text-center w-full sm:w-64">
                  <div className="absolute -top-3 right-4 bg-emerald-500 text-white text-[9px] font-bold px-2 py-0.5 rounded uppercase">
                    {m.merger_role || 'Merged Entity'}
                  </div>
                  <Link to={`/prospects/${m.id}`} className="inline-block hover:opacity-80 transition-opacity">
                    <h4 className="text-base font-bold text-slate-200 mb-1">{m.company_name}</h4>
                  </Link>
                  <div className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                    <MapPin size={10} /> {m.country_head_office} &bull; {m.primary_industries}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* NEW Merged Into Visualization (Where this prospect went) */}
        {prospect.merged_into_prospects_detail && prospect.merged_into_prospects_detail.length > 0 && (
          <div className="flex flex-col items-center mt-6 w-full relative z-10">
            <div className="h-6 border-l-2 border-dashed border-amber-500/50"></div>
            <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/20 border border-amber-500/50 rounded-full text-[10px] font-bold text-amber-400 uppercase tracking-widest my-2">
              <LinkIcon size={12} /> MERGED INTO ({prospect.merged_into_prospects_detail.length})
            </div>
            <div className="h-6 border-l-2 border-dashed border-amber-500/50 mb-2"></div>
            
            <div className="flex flex-wrap justify-center gap-4 w-full max-w-2xl">
              {prospect.merged_into_prospects_detail.map(mc => {
                const isDissolved = prospect.dissolved_into_prospects_detail?.some(d => d.id === mc.id);
                return (
                  <div key={mc.id} className="relative p-4 rounded-xl bg-amber-900/10 border border-amber-500/30 hover:bg-amber-900/20 transition-all text-center w-full sm:w-64">
                    <div className="absolute -top-3 right-4 bg-amber-500 text-white text-[9px] font-bold px-2 py-0.5 rounded uppercase shadow-sm">
                      {isDissolved ? 'Dissolved Into' : 'Merged Into'}
                    </div>
                    <Link to={`/prospects/${mc.id}`} className="inline-block hover:opacity-80 transition-opacity">
                      <h4 className="text-base font-bold text-slate-200 mb-1">{mc.company_name}</h4>
                    </Link>
                    <div className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                      <MapPin size={10} /> {mc.country_head_office} &bull; {mc.primary_industries}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* NEW Merging Companies Visualization (Merged From) */}
        {prospect.operational_status === 'Merged' && prospect.merging_companies_detail && prospect.merging_companies_detail.length > 0 && (
          <div className="flex flex-col items-center mt-6 w-full relative z-10">
            <div className="h-6 border-l-2 border-dashed border-amber-500/50"></div>
            <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/20 border border-amber-500/50 rounded-full text-[10px] font-bold text-amber-400 uppercase tracking-widest my-2">
              <LinkIcon size={12} /> MERGED FROM ({prospect.merging_companies_detail.length})
            </div>
            <div className="h-6 border-l-2 border-dashed border-amber-500/50 mb-2"></div>
            
            <div className="flex flex-wrap justify-center gap-4 w-full max-w-2xl">
              {prospect.merging_companies_detail.map(mc => {
                const isDissolved = prospect.dissolved_companies?.includes(mc.id);
                return (
                  <div key={mc.id} className="relative p-4 rounded-xl bg-amber-900/10 border border-amber-500/30 hover:bg-amber-900/20 transition-all text-center w-full sm:w-64">
                    <div className="absolute -top-3 right-4 bg-amber-500 text-white text-[9px] font-bold px-2 py-0.5 rounded uppercase shadow-sm">
                      {isDissolved ? 'Dissolved' : 'Merging Partner'}
                    </div>
                    <Link to={`/prospects/${mc.id}`} className="inline-block hover:opacity-80 transition-opacity">
                      <h4 className="text-base font-bold text-slate-200 mb-1">{mc.company_name}</h4>
                    </Link>
                    <div className="text-[10px] text-slate-400 flex items-center justify-center gap-1">
                      <MapPin size={10} /> {mc.country_head_office} &bull; {mc.primary_industries}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Vertical Line down to Children */}
        {children.length > 0 && (
          <div className="h-12 w-px bg-indigo-900/50 my-2"></div>
        )}
      </div>

      {/* Bottom Level: Children */}
      {children.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-2 relative z-10">
          
          {/* Branches */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
            <div className="flex justify-center mb-5">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-cyan-900/50 bg-cyan-900/20 text-cyan-400 text-xs font-semibold uppercase tracking-wider">
                <Globe size={14} /> Connected Branch Offices ({branches.length})
              </div>
            </div>
            {branches.length > 0 ? (
              <div className="space-y-3">
                {branches.map(b => (
                  <MiniCard key={b.id} company={b} badgeLabel="Branch" badgeColor="bg-cyan-600" />
                ))}
              </div>
            ) : (
              <div className="text-center text-xs text-slate-500 py-4 border border-dashed border-slate-700 rounded-xl">
                No branch offices connected.
              </div>
            )}
          </div>

          {/* Subsidiaries */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-5">
            <div className="flex justify-center mb-5">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-purple-900/50 bg-purple-900/20 text-purple-400 text-xs font-semibold uppercase tracking-wider">
                <Briefcase size={14} /> Subsidiary & Acquired Entities ({subsidiaries.length})
              </div>
            </div>
            {subsidiaries.length > 0 ? (
              <div className="space-y-3">
                {subsidiaries.map(s => (
                  <MiniCard key={s.id} company={s} badgeLabel="Subsidiary" badgeColor="bg-purple-600" />
                ))}
              </div>
            ) : (
              <div className="text-center text-xs text-slate-500 py-4 border border-dashed border-slate-700 rounded-xl">
                No subsidiaries connected.
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
};

export default CorporateStructureTree;
