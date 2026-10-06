import React, { useState, useEffect, useRef } from 'react';
import { X, Building } from 'lucide-react';
import api from '../../services/api';
import { toast } from 'react-toastify';
import SearchableSelect from '../common/SearchableSelect';
import { COUNTRIES } from '../../utils/countries';

const GovernmentEntityForm = ({ isOpen, onClose, entity = null, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const wasEditingRef = useRef(false);
  const initialEmptyState = {
    name: '',
    country: '',
    is_state_government: false,
    state_name: '',
    central_government: '',
    official_website: '',
    official_email: '',
    phone_number: '',
    complete_address: '',
  };

  const [formData, setFormData] = useState(() => {
    const saved = sessionStorage.getItem(`govEntityFormData`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return initialEmptyState;
  });

  useEffect(() => {
    sessionStorage.setItem(`govEntityFormData`, JSON.stringify(formData));
  }, [formData]);

  const [centralGovOptions, setCentralGovOptions] = useState([]);

  useEffect(() => {
    if (isOpen) {
      if (entity) {
        wasEditingRef.current = true;
        setFormData({
          name: entity.name || '',
          country: entity.country || '',
          is_state_government: entity.is_state_government || false,
          state_name: entity.state_name || '',
          central_government: entity.central_government || '',
          official_website: entity.official_website || '',
          official_email: entity.official_email || '',
          phone_number: entity.phone_number || '',
          complete_address: entity.complete_address || '',
        });
      } else {
        if (wasEditingRef.current) {
          setFormData(initialEmptyState);
          wasEditingRef.current = false;
        }
      }
      fetchCentralGovs();
    }
  }, [isOpen, entity]);

  const fetchCentralGovs = async () => {
    try {
      const res = await api.get('/government-entities/?is_state_government=false');
      const results = res.data.results || res.data;
      setCentralGovOptions(
        results.map(gov => ({
          value: gov.id,
          label: `${gov.name} (${gov.country})`
        }))
      );
    } catch (err) {
      console.error('Failed to fetch central governments:', err);
    }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const payload = { ...formData };
      if (!payload.is_state_government) {
        payload.central_government = null;
        payload.state_name = '';
      } else if (!payload.central_government) {
        payload.central_government = null;
      }
      
      if (entity) {
        await api.put(`/government-entities/${entity.id}/`, payload);
        toast.success('Government Entity updated successfully!');
      } else {
        await api.post('/government-entities/', payload);
        toast.success('Government Entity created successfully!');
        setFormData(initialEmptyState);
      }
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      const errMsg = err.response?.data?.error || 'Operation failed';
      toast.error(errMsg);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <Building className="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">
                {entity ? 'Edit Government Entity' : 'Add New Government Entity'}
              </h2>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-500 hover:bg-slate-100 rounded-full transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">
          <form id="govEntityForm" onSubmit={handleSubmit} className="space-y-6">
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Entity Name *</label>
                <input required type="text" name="name" value={formData.name} onChange={handleChange} className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Country *</label>
                <SearchableSelect
                  options={COUNTRIES}
                  value={formData.country}
                  onChange={(val) => setFormData({ ...formData, country: val })}
                  placeholder="Select country"
                />
              </div>
            </div>

            <div className="bg-white p-5 rounded-xl border border-slate-200 space-y-4">
              <h3 className="font-semibold text-slate-800 text-sm">Hierarchy Options</h3>
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_state_government"
                  name="is_state_government"
                  checked={formData.is_state_government}
                  onChange={handleChange}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                />
                <label htmlFor="is_state_government" className="ml-2 block text-sm text-gray-900 font-medium">
                  This is a State Government Entity
                </label>
              </div>

              {formData.is_state_government && (
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">State Name *</label>
                    <input required type="text" name="state_name" value={formData.state_name} onChange={handleChange} placeholder="e.g. Tamil Nadu, California" className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1.5">Belongs to Central Government</label>
                    <SearchableSelect
                      options={centralGovOptions}
                      value={formData.central_government}
                      onChange={(val) => setFormData({ ...formData, central_government: val })}
                      placeholder="Select corresponding Central Government"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Official Website</label>
                <input type="url" name="official_website" value={formData.official_website} onChange={handleChange} className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Official Email</label>
                <input type="email" name="official_email" value={formData.official_email} onChange={handleChange} className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Phone Number</label>
                <input type="text" name="phone_number" value={formData.phone_number} onChange={handleChange} className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-700 mb-1.5">Complete Address</label>
                <textarea rows={2} name="complete_address" value={formData.complete_address} onChange={handleChange} className="w-full rounded-xl shadow-sm text-sm px-4 py-3 text-slate-900 bg-white outline-none border border-slate-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"></textarea>
              </div>
            </div>

          </form>
        </div>

        <div className="px-6 py-4 border-t border-slate-100 bg-gray-50 flex justify-end gap-3 rounded-b-2xl">
          <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 hover:text-slate-900 transition-colors">
            Cancel
          </button>
          <button type="submit" form="govEntityForm" disabled={loading} className="px-5 py-2.5 text-sm font-medium text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 focus:ring-4 focus:ring-indigo-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            {loading ? 'Saving...' : (entity ? 'Save Changes' : 'Create Entity')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default GovernmentEntityForm;
