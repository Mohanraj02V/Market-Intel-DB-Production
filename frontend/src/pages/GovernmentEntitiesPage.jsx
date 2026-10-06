import React, { useEffect, useState } from 'react';
import { Building2, Plus, Edit2, Search } from 'lucide-react';
import api from '../services/api';
import GovernmentEntityForm from '../components/prospects/GovernmentEntityForm';

const GovernmentEntitiesPage = () => {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isFormOpen, setIsFormOpen] = useState(() => {
    return sessionStorage.getItem(`govEntityFormOpen`) === 'true';
  });
  const [editingEntity, setEditingEntity] = useState(() => {
    const saved = sessionStorage.getItem(`govEntityEditing`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });
  const [searchTerm, setSearchTerm] = useState(() => {
    return sessionStorage.getItem(`govEntitySearch`) || '';
  });

  useEffect(() => {
    sessionStorage.setItem(`govEntitySearch`, searchTerm);
    sessionStorage.setItem(`govEntityFormOpen`, isFormOpen);
    if (editingEntity) {
      sessionStorage.setItem(`govEntityEditing`, JSON.stringify(editingEntity));
    } else {
      sessionStorage.removeItem(`govEntityEditing`);
    }
  }, [searchTerm, isFormOpen, editingEntity]);

  const fetchEntities = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/government-entities/?search=${searchTerm}`);
      setEntities(res.data.results || res.data);
    } catch (err) {
      console.error('Failed to fetch government entities:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEntities();
  }, [searchTerm]);

  const handleAddClick = () => {
    setEditingEntity(null);
    setIsFormOpen(true);
  };

  const handleEditClick = (entity) => {
    setEditingEntity(entity);
    setIsFormOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="h-6 w-6 text-indigo-600" />
            Government Entities
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            Manage your public sector entities and hierarchy.
          </p>
        </div>
        <div className="mt-4 sm:mt-0 flex gap-3">
          <button
            onClick={handleAddClick}
            className="inline-flex items-center px-4 py-2 border border-transparent rounded-xl shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
          >
            <Plus className="-ml-1 mr-2 h-5 w-5" aria-hidden="true" />
            Add Entity
          </button>
        </div>
      </div>

      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200">
        <div className="relative max-w-md">
          <div className="pointer-events-none absolute inset-y-0 left-0 pl-3 flex items-center">
            <Search className="h-5 w-5 text-slate-400" />
          </div>
          <input
            type="text"
            className="block w-full rounded-xl border-slate-200 pl-10 focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm py-2.5 outline-none border"
            placeholder="Search by name or country..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="bg-white shadow-sm ring-1 ring-slate-200 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="p-10 text-center text-slate-500">Loading...</div>
        ) : entities.length === 0 ? (
          <div className="p-10 text-center text-slate-500">No entities found.</div>
        ) : (
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="py-3.5 pl-4 pr-3 text-left text-xs font-semibold text-slate-900 sm:pl-6">Name</th>
                <th className="px-3 py-3.5 text-left text-xs font-semibold text-slate-900">Country</th>
                <th className="px-3 py-3.5 text-left text-xs font-semibold text-slate-900">Level</th>
                <th className="px-3 py-3.5 text-left text-xs font-semibold text-slate-900">Parent Govt</th>
                <th className="relative py-3.5 pl-3 pr-4 sm:pr-6"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {entities.map((entity) => (
                <tr key={entity.id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-slate-900 sm:pl-6">
                    {entity.name}
                  </td>
                  <td className="whitespace-nowrap px-3 py-4 text-sm text-slate-500">{entity.country}</td>
                  <td className="whitespace-nowrap px-3 py-4 text-sm text-slate-500">
                    <span className={`inline-flex rounded-full px-2 text-xs font-semibold leading-5 ${entity.is_state_government ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                      {entity.is_state_government ? `State${entity.state_name ? ` (${entity.state_name})` : ''}` : 'Central'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-4 text-sm text-slate-500">
                    {entity.central_government_detail?.name || '-'}
                  </td>
                  <td className="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-6">
                    <button
                      onClick={() => handleEditClick(entity)}
                      className="text-indigo-600 hover:text-indigo-900 bg-indigo-50 p-2 rounded-lg"
                      title="Edit"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <GovernmentEntityForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        entity={editingEntity}
        onSuccess={fetchEntities}
      />
    </div>
  );
};

export default GovernmentEntitiesPage;
