import React, { useState, useRef, useEffect } from 'react';
import { Search, ChevronDown, Check } from 'lucide-react';

const SearchableSelect = ({ options, value, onChange, placeholder = "Select an option..." }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const wrapperRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [wrapperRef]);

  // Handle case where options might be passed empty or invalid
  const validOptions = Array.isArray(options) ? options : [];
  
  const filteredOptions = validOptions.filter(option =>
    (option.label || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const selectedOption = validOptions.find(opt => opt.value === value);

  return (
    <div ref={wrapperRef} className="relative w-full text-left">
      <div 
        className={`w-full rounded-xl bg-white border ${isOpen ? 'border-indigo-500 ring-2 ring-indigo-100' : 'border-slate-200'} text-sm px-4 py-3 transition-all shadow-sm cursor-pointer flex justify-between items-center`}
        onClick={() => { setIsOpen(!isOpen); setSearchTerm(''); }}
      >
        <span className={`block truncate ${selectedOption ? 'text-slate-900 font-bold' : 'text-slate-500'}`}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown size={18} className={`text-slate-400 transition-transform ${isOpen ? 'rotate-180 text-indigo-500' : ''}`} />
      </div>

      {isOpen && (
        <div className="absolute z-[100] w-full mt-2 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="p-2 border-b border-slate-100 bg-slate-50/50">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                autoFocus
                className="w-full pl-8 pr-3 py-2 text-sm bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400 transition-all shadow-sm"
                placeholder="Search options..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>
          <div className="max-h-60 overflow-y-auto p-1.5 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
            {filteredOptions.length === 0 ? (
              <div className="p-3 text-sm text-center text-slate-500">No results found</div>
            ) : (
              filteredOptions.map((option) => (
                <div
                  key={option.value}
                  className={`px-3 py-2.5 text-sm rounded-lg cursor-pointer flex items-center justify-between transition-colors ${value === option.value ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-slate-700 hover:bg-slate-50 font-medium'}`}
                  onClick={() => {
                    onChange(option.value);
                    setIsOpen(false);
                  }}
                >
                  <span className="truncate pr-4">{option.label}</span>
                  {value === option.value && <Check size={16} className="text-indigo-600 shrink-0" />}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchableSelect;
