import React, { useState, useEffect, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { toast } from 'react-toastify';
import { fetchProspects } from '../features/prospects/prospectSlice';
import { ArrowLeft, Upload, CheckCircle, XCircle, AlertTriangle, Download, AlertCircle, Trash2, History, ChevronDown, ChevronRight, CornerDownRight, Info, RefreshCw, FileText } from 'lucide-react';

const MAX_IMPORT_ROWS = 100;

const formatRows = (rows) => (rows && rows.length ? rows.join(', ') : '-');

const historyStatusClass = (s) => (
  s === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
  s === 'PARTIAL' ? 'bg-amber-50 text-amber-700 border-amber-200' :
  'bg-red-50 text-red-700 border-red-200'
);

const ImportedTable = ({ rows }) => (
  <div className="max-h-[400px] overflow-y-auto overflow-x-auto rounded-b-xl">
    <table className="min-w-full divide-y divide-slate-200 text-sm">
      <thead className="bg-slate-50 sticky top-0 z-10 shadow-sm">
        <tr>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Excel Row</th>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Company</th>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Prospect</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 bg-white">
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{formatRows(r.source_row_numbers)}</td>
            <td className="px-3 py-2 font-medium text-slate-800">{r.company_name}</td>
            <td className="px-3 py-2">
              {r.prospect_id ? <Link to={`/prospects/${r.prospect_id}`} className="text-indigo-600 hover:underline">View</Link> : '-'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const NotImportedTable = ({ rows }) => (
  <div className="max-h-[400px] overflow-y-auto overflow-x-auto rounded-b-xl">
    <table className="min-w-full divide-y divide-slate-200 text-sm">
      <thead className="bg-slate-50 sticky top-0 z-10 shadow-sm">
        <tr>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Excel Row</th>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Company</th>
          <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Reason</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 bg-white">
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{formatRows(r.source_row_numbers)}</td>
            <td className="px-3 py-2 font-medium text-slate-800">{r.company_name || <span className="text-slate-400">(no name)</span>}</td>
            <td className="px-3 py-2 text-red-600">{r.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ImportPreviewPage = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fileHeaders, setFileHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [step, setStep] = useState(1);
  const [previewData, setPreviewData] = useState([]);
  const [previewMeta, setPreviewMeta] = useState(null);
  const [importing, setImporting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [expandedHistory, setExpandedHistory] = useState(null);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get('/prospects/import/history/');
      setHistory(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Failed to load import history', err);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const FIELD_GROUPS = [
    {
      title: 'General Information',
      fields: [
        { key: 'company_name', label: 'Company Name', required: true },
        { key: 'country_head_office', label: 'Country', required: true },
        { key: 'complete_address', label: 'Complete Address' },
        { key: 'primary_industries', label: 'Primary Industries' },
        { key: 'official_phone_number', label: 'Official Phone Number' },
        { key: 'official_email_address', label: 'Official Email Address' },
        { key: 'official_website_url', label: 'Official Website URL' },
        { key: 'linkedin_company_page', label: 'LinkedIn Company Page' },
        { key: 'company_structure', label: 'Company Structure', required: true },
        { key: 'parent_company_names', label: 'Parent Company / Parent Companies' },
        { key: 'operational_status', label: 'Operational Status', required: true },
        { key: 'status_target', label: 'Target / Surviving Company' },
        { key: 'ownership_sector', label: 'Company Type', required: true },
        { key: 'primary_offering_type', label: 'Primary Offering Type', required: true },
      ]
    },
    {
      title: 'Company Relationships & Ownership',
      fields: [
        { key: 'merging_companies', label: 'Merging Companies' },
        { key: 'dissolved_companies', label: 'Dissolved Companies' },
        { key: 'acquiring_company', label: 'Acquiring Company' },
        { key: 'acquired_shares', label: 'Acquired Shares (%)' },
        { key: 'acquired_companies', label: 'Acquired Companies' },
        { key: 'shareholders', label: 'Stakeholders / Shareholders' },
      ]
    },
    {
      title: 'Key Contacts / Personnel',
      fields: [
        { key: 'contact_name', label: 'Contact Name' },
        { key: 'contact_designation', label: 'Designation / Role' },
        { key: 'contact_email', label: 'Official Email' },
        { key: 'contact_phone', label: 'Phone Number' },
      ]
    },
    {
      title: 'Market Offerings',
      fields: [
        { key: 'product', label: 'Products Offered' },
        { key: 'service', label: 'Services Provided' },
        { key: 'solution', label: 'Solutions Provided' },
      ]
    },
    {
      title: 'Market Events',
      fields: [
        { key: 'market_events', label: 'Associated Market Events' },
      ]
    }
  ];

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    setPreviewData([]);
    setPreviewMeta(null);
    setImportResult(null);
    setStep(1);

    const formData = new FormData();
    formData.append('file', selectedFile);

    setLoading(true);
    try {
      const res = await api.post('/prospects/import/headers/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setFileHeaders(res.data.headers);

      const autoMapping = {};
      const lowerHeaders = res.data.headers.map(h => h.toLowerCase().trim());
      const allFields = FIELD_GROUPS.flatMap(g => g.fields.map(f => ({ ...f, groupTitle: g.title })));
      
      const aliases = {
        company_name: ['company', 'organization', 'account'],
        country_head_office: ['country', 'nation'],
        complete_address: ['address', 'location', 'hq', 'city', 'state'],
        primary_industries: ['industry', 'sector', 'domain', 'vertical'],
        official_phone_number: ['phone', 'telephone', 'mobile', 'contact number', 'tel'],
        official_email_address: ['email', 'e-mail'],
        official_website_url: ['website', 'url', 'site', 'web', 'link'],
        company_structure: ['structure', 'company type', 'entity type'],
        parent_company_names: ['parent company', 'parent companies', 'parent company name', 'parent'],
        operational_status: ['operational status', 'status', 'operating status'],
        status_target: ['target company', 'surviving company', 'merged with', 'acquired by'],
        merger_role: ['merger role', 'role in merger', 'role', 'owner sector'],
        ownership_sector: ['company type', 'ownership sector', 'ownership', 'public', 'private', 'sector'],
        primary_offering_type: ['primary offering', 'offering type', 'main offering'],
        contact_name: ['contact name', 'person', 'executive', 'first name', 'last name', 'name'],
        contact_designation: ['designation', 'role', 'title', 'job title', 'position'],
        contact_email: ['contact email', 'personal email', 'direct email'],
        contact_phone: ['contact phone', 'direct number', 'mobile'],
        product: ['product', 'software', 'hardware'],
        service: ['service', 'consulting'],
        solution: ['solution', 'platform']
      };

      // Pass 1: Exact matches
      allFields.forEach(f => {
        const exactMatch = lowerHeaders.findIndex(h => {
          const hNorm = h.replace(/\s+/g, ' ');
          return hNorm === f.key.toLowerCase() || 
                 hNorm === f.label.toLowerCase() || 
                 hNorm === `${f.groupTitle} ${f.label}`.toLowerCase() ||
                 hNorm === `${f.groupTitle} - ${f.label}`.toLowerCase();
        });
        if (exactMatch !== -1) {
          autoMapping[f.key] = res.data.headers[exactMatch];
        }
      });
      
      // Pass 2: Fuzzy matching
      allFields.forEach(f => {
        if (autoMapping[f.key]) return; 
        
        const fieldAliases = aliases[f.key] || [];
        const fuzzyMatch = lowerHeaders.findIndex((h, idx) => {
           // Skip if this header is already mapped to something else
           if (Object.values(autoMapping).includes(res.data.headers[idx])) return false;
           
           const hNorm = h.replace(/\s+/g, ' ');
           
           // Headers mentioning 'parent' belong only to the Parent Company field
           if ((f.key === 'parent_company_names') !== hNorm.includes('parent')) return false;
           
           // Ensure 'email' goes to company email unless it explicitly says 'contact'
           if (f.key === 'official_email_address' && hNorm.includes('email') && hNorm.includes('contact')) return false;
           if (f.key === 'contact_email' && hNorm.includes('email') && !hNorm.includes('contact')) return false;
           
           return fieldAliases.some(alias => hNorm.includes(alias) || hNorm === alias);
        });
        
        if (fuzzyMatch !== -1) {
           autoMapping[f.key] = res.data.headers[fuzzyMatch];
        }
      });
      
      setMapping(autoMapping);
      setStep(2);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to parse file headers.');
      setFile(null);
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = async () => {
    if (!file) {
      toast.error('Please select a file.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const backendMapping = {};
    Object.keys(mapping).forEach(dbKey => {
      const fileHeader = mapping[dbKey];
      if (fileHeader) {
        backendMapping[fileHeader] = dbKey;
      }
    });
    
    formData.append('mapping', JSON.stringify(backendMapping));

    setLoading(true);
    try {
      const res = await api.post('/prospects/import/preview/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      // Preview returns { rows, meta }
      setPreviewData(Array.isArray(res.data) ? res.data : (res.data.rows || []));
      setPreviewMeta(Array.isArray(res.data) ? null : (res.data.meta || null));
      setImportResult(null);
      setStep(3);
      toast.success('File parsed successfully.');
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.error || 'Failed to parse file.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyAll = async () => {
    let emailsToVerify = [];
    previewData.forEach(row => {
      if (row.validation_status === 'VALID') {
        row.emails_to_verify?.forEach(ev => {
          if (ev.status !== 'VALID') {
            emailsToVerify.push(ev.email);
          }
        });
      }
    });

    if (emailsToVerify.length === 0) {
      toast.info('No emails to verify.');
      return;
    }

    setVerifying(true);
    try {
      const res = await api.post('/email-verifications/bulk-verify/', { emails: emailsToVerify });
      const results = res.data;

      setPreviewData(prev => prev.map(row => {
        if (!row.emails_to_verify || row.emails_to_verify.length === 0) return row;
        
        const updatedEmails = row.emails_to_verify.map(ev => {
          const result = results.find(r => r.email === ev.email);
          if (result) {
            return {
              ...ev,
              status: result.verification_status,
              reason: result.reason
            };
          }
          return ev;
        });

        return { ...row, emails_to_verify: updatedEmails };
      }));
      toast.success('Emails verified.');
    } catch (err) {
      console.error(err);
      toast.error('Failed to verify emails.');
    } finally {
      setVerifying(false);
    }
  };

  const handleEmailChange = (index, evIndex, newEmail) => {
    setPreviewData(prev => {
      const newData = [...prev];
      const ev = newData[index].emails_to_verify[evIndex];
      ev.email = newEmail;
      ev.status = 'UNVERIFIED';
      ev.reason = '';
      
      // Sync back to data
      if (ev.type === 'company') {
        newData[index].data.official_email_address = newEmail;
      } else if (ev.type === 'contact') {
        const cIndex = ev.contact_index;
        if (cIndex !== undefined && newData[index].data.key_contacts[cIndex]) {
          newData[index].data.key_contacts[cIndex].official_email = newEmail;
        } else {
          // Fallback if index missing for some reason
          const contact = newData[index].data.key_contacts.find(c => c.contact_name === ev.contact_name);
          if (contact) contact.official_email = newEmail;
        }
      }
      return newData;
    });
  };

  const handleRemoveRow = (indexToRemove) => {
    setPreviewData(prev => prev.filter((_, index) => index !== indexToRemove));
  };

  const isRowImportable = (row) => (
    row.validation_status === 'VALID' &&
    !(row.emails_to_verify && row.emails_to_verify.some(ev => ev.status !== 'VALID'))
  );

  const handleConfirmImport = async () => {
    const importable = previewData.filter(isRowImportable);
    if (importable.length === 0) {
      toast.error('There are no valid, fully verified rows to import.');
      return;
    }

    setImporting(true);
    try {
      // Only send rows that are fully valid and verified.
      const res = await api.post('/prospects/import/commit/', {
        rows: importable,
        file_name: file?.name || '',
        limit_reached: !!previewMeta?.limit_reached,
      });
      const result = res.data;
      setImportResult(result);
      setStep(4);
      if (result.imported_count > 0 && result.not_imported_count === 0) {
        toast.success(`Successfully imported ${result.imported_count} prospects.`);
      } else if (result.imported_count > 0) {
        toast.warning(`Imported ${result.imported_count} prospects; ${result.not_imported_count} not imported.`);
      } else {
        toast.error('No rows were imported. See the reasons below.');
      }
      if (result.imported_count > 0) dispatch(fetchProspects({ page: 1 }));
      fetchHistory();
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.error || 'Import failed.');
    } finally {
      setImporting(false);
    }
  };

  const handleStartOver = () => {
    setFile(null);
    setFileHeaders([]);
    setMapping({});
    setPreviewData([]);
    setPreviewMeta(null);
    setImportResult(null);
    setStep(1);
  };

  const totalRows = previewData.length;
  const validRows = previewData.filter(r => r.validation_status === 'VALID').length;
  const invalidRows = previewData.filter(r => r.validation_status === 'INVALID').length;
  
  let totalEmails = 0;
  let emailsVerified = 0;
  let emailsInvalid = 0;
  
  previewData.forEach(row => {
    if (row.emails_to_verify) {
      row.emails_to_verify.forEach(ev => {
        totalEmails++;
        if (ev.status === 'VALID') emailsVerified++;
        if (ev.status === 'INVALID') emailsInvalid++;
      });
    }
  });

  // Invalid rows no longer block valid ones; only rows that are valid AND fully verified are importable.
  const importableCount = previewData.filter(isRowImportable).length;
  const pendingVerificationCount = previewData.filter(r => r.validation_status === 'VALID' && !isRowImportable(r)).length;
  const canImport = importableCount > 0;

  const handleDownloadBlueprint = async () => {
    try {
      const res = await api.get('/prospects/import/blueprint/', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'prospect_blueprint.xlsx');
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (err) {
      console.error('Download error:', err);
      toast.error('Failed to download blueprint.');
    }
  };

  return (
    <div className="space-y-8 pb-12 max-w-[1600px] mx-auto">
      {/* Header Area */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-white p-6 rounded-xl shadow-[0_2px_12px_rgba(0,0,0,0.04)] border border-slate-200">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
            <Link to="/prospects" className="p-1.5 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
              <ArrowLeft size={20} />
            </Link>
            Data Import
          </h1>
          <p className="mt-1.5 text-sm text-slate-500 ml-11">
            Bulk import prospects, update existing records, and map relationships seamlessly.
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <button
            onClick={handleDownloadBlueprint}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm font-semibold text-slate-700 hover:bg-slate-50 hover:text-indigo-600 transition-all shadow-sm"
          >
            <Download size={16} /> Download Template
          </button>
        </div>
      </div>

      {/* Workflow Stepper */}
      <div className="bg-white rounded-xl shadow-[0_2px_12px_rgba(0,0,0,0.04)] border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-8 relative">
          <div className="absolute top-1/2 left-0 w-full h-0.5 bg-slate-100 -z-10 -translate-y-1/2"></div>
          {[
            { num: 1, label: 'Upload File', active: step >= 1, current: step === 1 },
            { num: 2, label: 'Map Fields', active: step >= 2, current: step === 2 },
            { num: 3, label: 'Preview & Verify', active: step >= 3, current: step === 3 },
            { num: 4, label: 'Import Results', active: step === 4, current: step === 4 }
          ].map((s) => (
            <div key={s.num} className="flex flex-col items-center gap-2 bg-white px-4">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm border-2 transition-colors ${s.current ? 'border-indigo-600 bg-indigo-600 text-white shadow-md' : s.active ? 'border-indigo-600 bg-indigo-50 text-indigo-600' : 'border-slate-200 bg-white text-slate-400'}`}>
                {s.active && !s.current ? <CheckCircle size={16} /> : s.num}
              </div>
              <span className={`text-xs font-semibold ${s.current ? 'text-indigo-600' : s.active ? 'text-slate-800' : 'text-slate-400'}`}>{s.label}</span>
            </div>
          ))}
        </div>

        {/* Step 1: Upload */}
        {step === 1 && (
          <div className="border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 hover:bg-indigo-50/50 hover:border-indigo-300 transition-all p-16 flex flex-col items-center justify-center text-center relative group">
            <input type="file" accept=".csv, .xlsx" onChange={handleFileChange} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" />
            <div className="w-16 h-16 bg-white rounded-full shadow-sm flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Upload size={28} className="text-indigo-500" />
            </div>
            <div className="text-lg font-bold text-slate-800 mb-1">Drag and drop your file here</div>
            <div className="text-sm text-slate-500">or click to browse from your computer</div>
            <div className="mt-6 flex items-center gap-4 text-xs font-medium text-slate-400">
              <span className="bg-white px-3 py-1 rounded-full border border-slate-200 shadow-sm">CSV</span>
              <span className="bg-white px-3 py-1 rounded-full border border-slate-200 shadow-sm">XLSX</span>
            </div>
          </div>
        )}

        {/* Step 2: Mapping */}
        {step === 2 && fileHeaders.length > 0 && (
          <div className="animate-fade-in">
            <div className="mb-6 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-bold text-slate-800">Map Columns</h3>
                <p className="text-sm text-slate-500">Match your uploaded file columns to the system fields.</p>
              </div>
              <button onClick={handlePreview} disabled={loading} className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-lg shadow-[0_4px_12px_rgba(79,70,229,0.3)] hover:bg-indigo-700 hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0 transition-all flex items-center gap-2">
                {loading ? 'Processing...' : 'Continue to Preview'} <ChevronRight size={18} />
              </button>
            </div>
            
            <div className="columns-1 xl:columns-2 gap-6">
              {FIELD_GROUPS.map((group, idx) => (
                <div key={idx} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden break-inside-avoid mb-6">
                  <div className="bg-slate-50/80 px-5 py-3.5 border-b border-slate-200">
                    <h4 className="text-xs font-bold text-indigo-900/80 uppercase tracking-wider flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-indigo-400"></div>
                      {group.title}
                    </h4>
                  </div>
                  <div className="p-0 divide-y divide-slate-100">
                    {group.fields.map(field => {
                      const isMapped = !!mapping[field.key];
                      return (
                        <div key={field.key} className={`flex items-center justify-between p-4 transition-colors ${isMapped ? 'bg-white' : 'bg-slate-50/50'}`}>
                          <div className="flex-1">
                            <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                              {field.label} {field.required && <span className="text-red-500">*</span>}
                            </label>
                          </div>
                          <div className="w-64 shrink-0 relative">
                            <select
                              value={mapping[field.key] || ''}
                              onChange={(e) => setMapping(prev => ({ ...prev, [field.key]: e.target.value }))}
                              className={`w-full text-sm rounded-lg shadow-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors appearance-none pr-10 ${
                                isMapped ? 'bg-indigo-50/50 border-indigo-200 text-indigo-900 font-medium' : 'bg-white border-slate-300 text-slate-500'
                              }`}
                            >
                              <option value="">-- Ignore Field --</option>
                              {fileHeaders.map(h => (
                                <option key={h} value={h}>{h}</option>
                              ))}
                            </select>
                            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-400">
                              <ChevronDown size={14} />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 3: Preview */}
        {step === 3 && previewData.length > 0 && (
          <div className="animate-fade-in space-y-6">
            {previewMeta?.limit_reached && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800 flex items-start gap-3 shadow-sm">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-500" />
                <div>
                  <strong className="font-semibold block mb-1">Row Limit Exceeded</strong>
                  Only the first {previewMeta.max_rows || MAX_IMPORT_ROWS} rows were processed. Rows beyond the limit will not be imported.
                </div>
              </div>
            )}

            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
              <div className="flex flex-wrap gap-8">
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-slate-500 uppercase">Valid Rows</span>
                  <span className="text-2xl font-bold text-emerald-600">{validRows}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-slate-500 uppercase">Invalid Rows</span>
                  <span className="text-2xl font-bold text-red-600">{invalidRows}</span>
                </div>
                <div className="w-px bg-slate-200 hidden lg:block"></div>
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-slate-500 uppercase">Emails Verified</span>
                  <span className="text-2xl font-bold text-indigo-600">{emailsVerified} / {totalEmails}</span>
                </div>
              </div>
              
              <div className="flex flex-wrap gap-3">
                <button onClick={handleStartOver} className="px-5 py-2.5 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 text-sm font-semibold transition-colors shadow-sm">
                  Start Over
                </button>
                <button onClick={handleVerifyAll} disabled={verifying} className="px-5 py-2.5 bg-white border border-indigo-200 text-indigo-700 rounded-lg hover:bg-indigo-50 disabled:opacity-50 text-sm font-semibold shadow-sm transition-colors flex items-center gap-2">
                  {verifying ? <RefreshCw size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                  Verify Emails
                </button>
                <button onClick={handleConfirmImport} disabled={!canImport || importing} className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-bold shadow-[0_4px_12px_rgba(79,70,229,0.3)] transition-all flex items-center gap-2">
                  {importing ? <RefreshCw size={16} className="animate-spin" /> : <Upload size={16} />}
                  Import {importableCount} Rows
                </button>
              </div>
            </div>

            {(!canImport || pendingVerificationCount > 0 || invalidRows > 0) && (
              <div className="px-4 py-3 bg-indigo-50/50 border border-indigo-100 rounded-xl text-sm text-indigo-800 flex items-center gap-2">
                <Info size={16} className="text-indigo-500 shrink-0" />
                <span>
                  {!canImport
                    ? (validRows === 0
                        ? 'No rows can be imported: every row has validation errors. Fix the file and preview again.'
                        : 'No rows are ready yet: verify the emails of valid rows (all emails in a row must be VALID).')
                    : `Only valid rows with all emails verified will be imported. ${invalidRows} invalid row(s) and ${pendingVerificationCount} row(s) awaiting email verification will be skipped.`}
                </span>
              </div>
            )}

            <div className="border border-slate-200 rounded-xl overflow-hidden shadow-sm bg-white">
              <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50 sticky top-0 z-20">
                    <tr>
                      <th className="px-5 py-3.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50 sticky left-0 z-30 shadow-[1px_0_0_rgba(226,232,240,1)]">Row</th>
                      <th className="px-5 py-3.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50">Status</th>
                      
                      {Object.keys(mapping).filter(k => mapping[k] !== '').map(key => {
                        const field = FIELD_GROUPS.flatMap(g => g.fields).find(f => f.key === key);
                        return (
                          <th key={key} className="px-5 py-3.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50">
                            {field ? field.label : key}
                          </th>
                        );
                      })}
                      
                      <th className="px-5 py-3.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap bg-slate-50">Verification</th>
                      <th className="px-5 py-3.5 text-left text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap min-w-[400px] bg-slate-50">Errors</th>
                      <th className="px-5 py-3.5 text-center text-xs font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap sticky right-0 bg-slate-50 z-30 shadow-[-1px_0_0_rgba(226,232,240,1)]">Action</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-100">
                    {previewData.map((row, index) => (
                      <tr key={index} className={`hover:bg-slate-50/50 transition-colors ${row.validation_status === 'INVALID' || row.email_verification_status === 'INVALID' ? 'bg-red-50/30' : ''}`}>
                        <td className="px-5 py-4 whitespace-nowrap text-sm font-semibold text-slate-600 bg-white sticky left-0 z-10 shadow-[1px_0_0_rgba(226,232,240,1)] group-hover:bg-slate-50/50" title="Original Excel row(s)">
                          {row.source_row_numbers?.length ? formatRows(row.source_row_numbers) : row.row_number}
                        </td>
                        <td className="px-5 py-4 whitespace-nowrap">
                          {row.validation_status === 'VALID' ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700">
                              <CheckCircle size={14} /> VALID
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700">
                              <XCircle size={14} /> INVALID
                            </span>
                          )}
                        </td>
                        
                        {Object.keys(mapping).filter(k => mapping[k] !== '').map(key => {
                          const field = FIELD_GROUPS.flatMap(g => g.fields).find(f => f.key === key);
                          const isMissingRequired = field?.required && !row.data[key];
                          const isDuplicate = key === 'company_name' && row.errors?.some(e => e.includes('Duplicate'));
                          
                          return (
                            <td key={key} className="px-5 py-4 text-sm text-slate-800" title={row.data[key]}>
                              {key === 'official_email_address' ? (
                                <input type="email" value={row.emails_to_verify?.find(e => e.type === 'company')?.email || ''} onChange={(e) => {
                                  const evIdx = row.emails_to_verify?.findIndex(ev => ev.type === 'company');
                                  if (evIdx !== -1) handleEmailChange(index, evIdx, e.target.value);
                                }} className="border border-slate-200 rounded-md px-3 py-1.5 text-sm w-48 shadow-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" />
                              ) : key === 'contact_email' ? (
                                <div className="space-y-2">
                                   {row.emails_to_verify?.filter(e => e.type === 'contact').map((ev, evIdxObj) => {
                                      const actualEvIdx = row.emails_to_verify.indexOf(ev);
                                      return (
                                        <input key={actualEvIdx} type="email" value={ev.email} onChange={(e) => handleEmailChange(index, actualEvIdx, e.target.value)} className="border border-slate-200 rounded-md px-3 py-1.5 text-sm w-48 shadow-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" title={`Contact: ${ev.contact_name}`} />
                                      );
                                   })}
                                </div>
                              ) : key === 'company_structure' && row.data[key] ? (
                                <span className="px-2.5 py-1 rounded-md text-[11px] font-bold bg-indigo-50 text-indigo-600 border border-indigo-100">{row.data[key]}</span>
                              ) : key === 'operational_status' && row.data[key] ? (
                                <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold border ${
                                  ['Active', 'Operating'].includes(row.data[key]) ? 'bg-emerald-50 text-emerald-600 border-emerald-100' :
                                  ['Merged', 'Acquired'].includes(row.data[key]) ? 'bg-amber-50 text-amber-600 border-amber-100' :
                                  'bg-slate-50 text-slate-600 border-slate-200'
                                }`}>{row.data[key]}</span>
                              ) : key === 'parent_company_names' ? (
                                row.parent_resolution?.length ? (
                                  <div className="space-y-2">
                                    {row.parent_resolution.map((pr, i) => (
                                      <div key={i} className="text-xs bg-slate-50 rounded-md p-2 border border-slate-100">
                                        <div className="font-semibold text-slate-800 mb-0.5">{pr.name}</div>
                                        {pr.status === 'EXISTS_IN_DB' && (
                                          <span className="flex items-center gap-1 text-emerald-600 font-medium"><CheckCircle size={12} /> Found in DB</span>
                                        )}
                                        {pr.status === 'FOUND_IN_FILE' && (
                                          <span className="flex items-center gap-1 text-indigo-600 font-medium"><CornerDownRight size={12} /> Excel row {pr.source_row}</span>
                                        )}
                                        {pr.status === 'MISSING' && (
                                          <span className="flex items-center gap-1 text-red-600 font-medium"><XCircle size={12} /> Missing</span>
                                        )}
                                        {pr.status === 'CIRCULAR_DEPENDENCY' && (
                                          <span className="flex items-center gap-1 text-amber-600 font-medium"><AlertTriangle size={12} /> Circular ref</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-slate-300">-</span>
                                )
                              ) : isMissingRequired ? (
                                <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-red-600 bg-red-50 px-2 py-1 rounded border border-red-200">
                                  <AlertCircle size={12} /> Required
                                </span>
                              ) : isDuplicate ? (
                                <div className="flex items-center gap-1.5 text-amber-700 font-semibold bg-amber-50 px-2.5 py-1 rounded border border-amber-200 w-max">
                                  <AlertCircle size={14} className="text-amber-500 shrink-0" />
                                  <span className="truncate max-w-[150px]">{row.data[key]}</span>
                                </div>
                              ) : row.data[key] ? (
                                <div className="truncate max-w-[200px] font-medium">{row.data[key]}</div>
                              ) : (
                                <span className="text-slate-300">-</span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-5 py-4 text-sm">
                          <div className="space-y-2">
                          {row.emails_to_verify?.map((ev, i) => (
                            <div key={i} className="flex items-center justify-between gap-3 bg-slate-50 px-2 py-1.5 rounded border border-slate-100 min-w-[160px]">
                              <span className="text-xs text-slate-500 font-semibold">{ev.type === 'company' ? 'Company' : 'Contact'}</span>
                              {ev.status === 'VALID' && <span className="text-emerald-600 font-bold text-[10px] tracking-wide bg-emerald-100 px-2 py-0.5 rounded">VALID</span>}
                              {ev.status === 'INVALID' && <span className="text-red-600 font-bold text-[10px] tracking-wide bg-red-100 px-2 py-0.5 rounded">INVALID</span>}
                              {ev.status === 'UNVERIFIED' && <span className="text-slate-500 font-bold text-[10px] tracking-wide bg-slate-200 px-2 py-0.5 rounded">PENDING</span>}
                            </div>
                          ))}
                          {(!row.emails_to_verify || row.emails_to_verify.length === 0) && <span className="text-slate-300">-</span>}
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm min-w-[400px]">
                          {(row.errors.length > 0 || (row.emails_to_verify && row.emails_to_verify.some(ev => ev.status === 'INVALID'))) ? (
                            <ul className="list-disc pl-4 text-red-600 text-xs space-y-1 font-medium">
                              {row.errors.map((err, i) => <li key={i}>{err}</li>)}
                              {row.emails_to_verify?.filter(ev => ev.status === 'INVALID').map((ev, i) => (
                                <li key={`ev-${i}`}>Email verification failed ({ev.type}): {ev.reason || 'Invalid email'}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-emerald-500 flex items-center gap-1 text-xs font-bold"><CheckCircle size={14}/> NO ERRORS</span>
                          )}
                        </td>
                        <td className="px-5 py-4 text-center sticky right-0 bg-white shadow-[-1px_0_0_rgba(226,232,240,1)] group-hover:bg-slate-50/50 transition-colors z-10">
                          <button
                            onClick={() => handleRemoveRow(index)}
                            className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                            title="Remove Row"
                          >
                            <Trash2 size={18} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Results */}
        {step === 4 && importResult && (
          <div className="animate-fade-in space-y-8">
            <div className="text-center pb-6 border-b border-slate-100">
              <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle size={32} />
              </div>
              <h2 className="text-2xl font-bold text-slate-800">Import Complete</h2>
              <p className="text-slate-500 mt-2">Your data import process has finished. Check the summary below.</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200 shadow-sm flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
                  <FileText size={24} />
                </div>
                <div>
                  <div className="text-sm font-bold text-slate-500 uppercase tracking-wider">Processed</div>
                  <div className="text-3xl font-black text-slate-800">{importResult.processed_source_rows}</div>
                </div>
              </div>
              <div className="bg-emerald-50 rounded-2xl p-6 border border-emerald-200 shadow-sm flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-emerald-200/50 flex items-center justify-center text-emerald-700 shrink-0">
                  <CheckCircle size={24} />
                </div>
                <div>
                  <div className="text-sm font-bold text-emerald-600 uppercase tracking-wider">Imported</div>
                  <div className="text-3xl font-black text-emerald-800">{importResult.imported_count}</div>
                </div>
              </div>
              <div className="bg-red-50 rounded-2xl p-6 border border-red-200 shadow-sm flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-red-200/50 flex items-center justify-center text-red-700 shrink-0">
                  <XCircle size={24} />
                </div>
                <div>
                  <div className="text-sm font-bold text-red-600 uppercase tracking-wider">Failed</div>
                  <div className="text-3xl font-black text-red-800">{importResult.not_imported_count}</div>
                </div>
              </div>
            </div>
            
            <div className="flex justify-center pt-4">
              <button onClick={handleStartOver} className="px-8 py-3 bg-indigo-600 text-white font-bold rounded-xl shadow-[0_4px_12px_rgba(79,70,229,0.3)] hover:bg-indigo-700 hover:-translate-y-0.5 transition-all flex items-center gap-2">
                <RefreshCw size={18} /> Start New Import
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Zoho Creator Style Import History */}
      <div className="bg-white rounded-2xl shadow-[0_4px_20px_rgba(0,0,0,0.03)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-white">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
              <History size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-800 leading-tight">Import History</h2>
              <p className="text-xs text-slate-500 font-medium">Log of all previously imported data files</p>
            </div>
          </div>
          <button onClick={fetchHistory} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors">
             <RefreshCw size={18} className={historyLoading ? "animate-spin" : ""} />
          </button>
        </div>
        
        {historyLoading && history.length === 0 ? (
          <div className="p-12 text-center text-slate-500 font-medium flex flex-col items-center gap-3">
            <RefreshCw size={24} className="animate-spin text-indigo-400" />
            Loading History...
          </div>
        ) : history.length === 0 ? (
          <div className="p-12 text-center text-slate-500 font-medium">
            <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-3">
              <History size={24} className="text-slate-300" />
            </div>
            No import history found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-slate-50/80">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">File Details</th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">Status</th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-slate-500 uppercase tracking-wider w-1/3 border-b border-slate-200">Progress</th>
                  <th className="px-6 py-4 text-right text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">Total</th>
                  <th className="px-6 py-4 text-right text-xs font-bold text-emerald-600 uppercase tracking-wider border-b border-slate-200">Success</th>
                  <th className="px-6 py-4 text-right text-xs font-bold text-red-600 uppercase tracking-wider border-b border-slate-200">Failed</th>
                  <th className="px-6 py-4 w-10 border-b border-slate-200"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((hist) => {
                  const total = hist.processed_source_rows || 1;
                  const successPct = Math.round((hist.imported_count / total) * 100);
                  const failedPct = Math.round((hist.not_imported_count / total) * 100);
                  
                  return (
                    <React.Fragment key={hist.id}>
                      <tr 
                        onClick={() => setExpandedHistory(expandedHistory === hist.id ? null : hist.id)}
                        className="hover:bg-slate-50/50 transition-colors cursor-pointer group"
                      >
                        <td className="px-6 py-5">
                          <div className="font-bold text-slate-800 group-hover:text-indigo-600 transition-colors flex items-center gap-2">
                            <FileText size={16} className="text-slate-400" />
                            {hist.file_name || 'Unnamed file'}
                          </div>
                          <div className="text-xs font-medium text-slate-500 mt-1 flex items-center gap-2 ml-6">
                            <span>{new Date(hist.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                            <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                            <span>{hist.created_by?.name || hist.created_by?.email || 'Unknown User'}</span>
                          </div>
                        </td>
                        <td className="px-6 py-5">
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-extrabold uppercase tracking-wide border ${historyStatusClass(hist.status)}`}>
                            {hist.status === 'COMPLETED' && <CheckCircle size={12} />}
                            {hist.status === 'FAILED' && <XCircle size={12} />}
                            {hist.status === 'PARTIAL' && <AlertTriangle size={12} />}
                            {hist.status.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="px-6 py-5">
                          <div className="w-full flex h-2 rounded-full overflow-hidden bg-slate-100">
                            <div style={{ width: `${successPct}%` }} className="bg-emerald-500 transition-all duration-1000"></div>
                            <div style={{ width: `${failedPct}%` }} className="bg-red-500 transition-all duration-1000"></div>
                          </div>
                          <div className="flex justify-between mt-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            <span>{successPct}%</span>
                            <span>{failedPct}%</span>
                          </div>
                        </td>
                        <td className="px-6 py-5 text-right font-bold text-slate-700">{hist.processed_source_rows}</td>
                        <td className="px-6 py-5 text-right font-bold text-emerald-600">{hist.imported_count}</td>
                        <td className="px-6 py-5 text-right font-bold text-red-600">{hist.not_imported_count}</td>
                        <td className="px-6 py-5 text-slate-400">
                          <div className={`p-1.5 rounded-md transition-colors flex items-center justify-center ${expandedHistory === hist.id ? 'bg-indigo-100 text-indigo-600' : 'group-hover:bg-slate-200 text-slate-400'}`}>
                            {expandedHistory === hist.id ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                          </div>
                        </td>
                      </tr>
                      {expandedHistory === hist.id && (
                        <tr>
                          <td colSpan="7" className="p-0 bg-slate-50/30">
                            <div className="p-8 border-t border-slate-100 shadow-inner">
                              {hist.limit_reached && (
                                <div className="mb-6 text-sm text-amber-800 bg-amber-50 p-4 rounded-xl border border-amber-200 flex items-start gap-3 shadow-sm">
                                  <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-500" />
                                  <div>
                                    <strong className="block font-bold mb-1">Limit Reached</strong>
                                    This import exceeded the maximum row limit. Only the first {hist.processed_source_rows} rows were processed.
                                  </div>
                                </div>
                              )}
                              
                              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                                {hist.imported_rows?.length > 0 && (
                                  <div>
                                    <h4 className="text-sm font-bold text-emerald-800 mb-3 flex items-center gap-2 uppercase tracking-wider">
                                      <CheckCircle size={16} className="text-emerald-500" />
                                      Imported Successfully ({hist.imported_count})
                                    </h4>
                                    <div className="border border-emerald-100 rounded-xl bg-white shadow-sm overflow-hidden">
                                      <ImportedTable rows={hist.imported_rows} />
                                    </div>
                                  </div>
                                )}

                                {hist.not_imported_rows?.length > 0 && (
                                  <div>
                                    <h4 className="text-sm font-bold text-red-800 mb-3 flex items-center gap-2 uppercase tracking-wider">
                                      <XCircle size={16} className="text-red-500" />
                                      Failed to Import ({hist.not_imported_count})
                                    </h4>
                                    <div className="border border-red-100 rounded-xl bg-white shadow-sm overflow-hidden">
                                      <NotImportedTable rows={hist.not_imported_rows} />
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ImportPreviewPage;
