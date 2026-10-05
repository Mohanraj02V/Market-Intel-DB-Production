import React, { useState } from 'react';
import { useDispatch } from 'react-redux';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { toast } from 'react-toastify';
import { fetchProspects } from '../features/prospects/prospectSlice';
import { ArrowLeft, Upload, CheckCircle, XCircle, AlertTriangle, Download, AlertCircle, Trash2 } from 'lucide-react';

const ImportPreviewPage = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fileHeaders, setFileHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [step, setStep] = useState(1);
  const [previewData, setPreviewData] = useState([]);
  const [importing, setImporting] = useState(false);
  const [verifying, setVerifying] = useState(false);

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
        { key: 'operational_status', label: 'Operational Status', required: true },
        { key: 'status_target', label: 'Target / Surviving Company' },
        { key: 'merger_role', label: 'Owner Sector' },
        { key: 'ownership_sector', label: 'Company Type', required: true },
        { key: 'primary_offering_type', label: 'Primary Offering Type', required: true },
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
    }
  ];

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    setPreviewData([]);
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
      setPreviewData(res.data);
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
        const contact = newData[index].data.key_contacts.find(c => c.contact_name === ev.contact_name);
        if (contact) contact.official_email = newEmail;
      }
      return newData;
    });
  };

  const handleRemoveRow = (indexToRemove) => {
    setPreviewData(prev => prev.filter((_, index) => index !== indexToRemove));
  };

  const handleConfirmImport = async () => {
    const invalidRows = previewData.filter(row => {
      if (row.validation_status !== 'VALID') return true;
      if (row.emails_to_verify && row.emails_to_verify.some(ev => ev.status !== 'VALID')) return true;
      return false;
    });
    
    if (invalidRows.length > 0) {
      toast.error('Please fix all errors and verify emails before importing.');
      return;
    }

    setImporting(true);
    try {
      const res = await api.post('/prospects/import/commit/', { rows: previewData });
      toast.success(`Successfully imported ${res.data.imported_count} prospects.`);
      dispatch(fetchProspects({ page: 1 }));
      navigate('/prospects');
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.error || 'Import failed.');
    } finally {
      setImporting(false);
    }
  };

  const totalRows = previewData.length;
  const validRows = previewData.filter(r => r.validation_status === 'VALID').length;
  const invalidRows = previewData.filter(r => r.validation_status === 'INVALID').length;
  
  let totalEmails = 0;
  let emailsVerified = 0;
  let emailsInvalid = 0;
  let allEmailsValid = true;
  
  previewData.forEach(row => {
    if (row.emails_to_verify) {
      row.emails_to_verify.forEach(ev => {
        totalEmails++;
        if (ev.status === 'VALID') emailsVerified++;
        if (ev.status === 'INVALID') emailsInvalid++;
        if (ev.status !== 'VALID') allEmailsValid = false;
      });
    }
  });

  const canImport = totalRows > 0 && invalidRows === 0 && allEmailsValid;

  const handleDownloadBlueprint = async () => {
    try {
      const res = await api.get('/prospects/import/blueprint/', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'prospect_import_blueprint.xlsx');
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (err) {
      console.error('Download error:', err);
      toast.error('Failed to download blueprint.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Link to="/prospects" className="text-slate-400 hover:text-slate-600">
              <ArrowLeft size={24} />
            </Link>
            Import Prospects
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            Upload a CSV or XLSX file to bulk import prospects.
          </p>
        </div>
        <div className="mt-4 sm:mt-0">
          <button
            onClick={handleDownloadBlueprint}
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 shadow-sm transition-all"
          >
            <Download size={16} /> Download Blueprint
          </button>
        </div>
      </div>

      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <div className="flex gap-4 items-center">
          <input type="file" accept=".csv, .xlsx" onChange={handleFileChange} className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100" />
        </div>
      </div>

      {step >= 2 && fileHeaders.length > 0 && (
        <div className="bg-white p-0 rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="p-6 border-b border-slate-200 bg-slate-50/50">
            <h2 className="text-xl font-bold text-slate-800">Map Fields</h2>
            <p className="text-sm text-slate-500 mt-1">Map the columns in your file to the corresponding database fields.</p>
          </div>
          
          <div className="p-6 space-y-8">
            {FIELD_GROUPS.map((group, idx) => (
              <div key={idx} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
                  <h3 className="text-sm font-bold text-indigo-900 uppercase tracking-wider">{group.title}</h3>
                </div>
                <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-4">
                  {group.fields.map(field => (
                    <div key={field.key} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3 last:border-0 last:pb-0">
                      <label className="text-sm font-medium text-slate-700 flex items-center min-w-[200px]">
                        {field.label} {field.required && <span className="text-red-500 ml-1">*</span>}
                      </label>
                      <select
                        value={mapping[field.key] || ''}
                        onChange={(e) => setMapping(prev => ({ ...prev, [field.key]: e.target.value }))}
                        className="w-full sm:w-64 text-sm bg-slate-50 border-slate-300 rounded-lg shadow-sm focus:border-indigo-500 focus:ring-indigo-500 transition-colors"
                      >
                        <option value="">-- Ignore --</option>
                        {fileHeaders.map(h => (
                          <option key={h} value={h}>{h}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          
          <div className="p-6 border-t border-slate-200 bg-slate-50 flex justify-end">
            <button onClick={handlePreview} disabled={loading} className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-lg shadow-sm hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-2">
              {loading ? 'Processing...' : 'Preview Import'}
            </button>
          </div>
        </div>
      )}

      {step === 3 && previewData.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex gap-6 text-sm">
              <div className="font-semibold text-slate-700">Total: {totalRows}</div>
              <div className="text-emerald-600">Valid: {validRows}</div>
              <div className="text-red-600">Invalid: {invalidRows}</div>
              <div className="text-emerald-600">Verified Emails: {emailsVerified}</div>
              <div className="text-red-600">Invalid Emails: {emailsInvalid}</div>
            </div>
            <div className="flex gap-3">
              <button onClick={handleVerifyAll} disabled={verifying} className="px-4 py-2 bg-white border border-indigo-200 text-indigo-700 rounded-lg hover:bg-indigo-50 disabled:opacity-50 text-sm font-medium">
                {verifying ? 'Verifying...' : 'Verify All Emails'}
              </button>
              <button onClick={handleConfirmImport} disabled={!canImport || importing} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium">
                {importing ? 'Importing...' : 'Confirm Import'}
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">Row</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">Status</th>
                  
                  {Object.keys(mapping).filter(k => mapping[k] !== '').map(key => {
                    const field = FIELD_GROUPS.flatMap(g => g.fields).find(f => f.key === key);
                    return (
                      <th key={key} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">
                        {field ? field.label : key}
                      </th>
                    );
                  })}
                  
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">Email Verification</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">Errors</th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-slate-500 uppercase whitespace-nowrap">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-200">
                {previewData.map((row, index) => (
                  <tr key={index} className={row.validation_status === 'INVALID' || row.email_verification_status === 'INVALID' ? 'bg-red-50' : ''}>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-slate-500">{row.row_number}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      {row.validation_status === 'VALID' ? (
                        <span className="flex items-center text-emerald-600"><CheckCircle size={16} className="mr-1" /> VALID</span>
                      ) : (
                        <span className="flex items-center text-red-600"><XCircle size={16} className="mr-1" /> INVALID</span>
                      )}
                    </td>
                    
                    {Object.keys(mapping).filter(k => mapping[k] !== '').map(key => {
                      const field = FIELD_GROUPS.flatMap(g => g.fields).find(f => f.key === key);
                      const isMissingRequired = field?.required && !row.data[key];
                      const isDuplicate = key === 'company_name' && row.errors?.some(e => e.includes('Duplicate'));
                      
                      let cellClass = "px-4 py-3 whitespace-nowrap text-sm font-medium max-w-[200px] truncate ";
                      if (isMissingRequired) cellClass += "bg-red-50/50 ";
                      else if (isDuplicate) cellClass += "bg-amber-50/50 ";
                      else cellClass += "text-slate-900 ";

                      return (
                        <td key={key} className={cellClass} title={row.data[key]}>
                          {key === 'official_email_address' ? (
                            <input type="email" value={row.emails_to_verify?.find(e => e.type === 'company')?.email || ''} onChange={(e) => {
                              const evIdx = row.emails_to_verify?.findIndex(ev => ev.type === 'company');
                              if (evIdx !== -1) handleEmailChange(index, evIdx, e.target.value);
                            }} className="border border-slate-300 rounded px-2 py-1 text-sm w-48 font-normal bg-white text-slate-900 focus:ring-1 focus:ring-indigo-500" />
                          ) : key === 'contact_email' ? (
                            <div className="space-y-2">
                               {row.emails_to_verify?.filter(e => e.type === 'contact').map((ev, evIdxObj) => {
                                  const actualEvIdx = row.emails_to_verify.indexOf(ev);
                                  return (
                                    <input key={actualEvIdx} type="email" value={ev.email} onChange={(e) => handleEmailChange(index, actualEvIdx, e.target.value)} className="border border-slate-300 rounded px-2 py-1 text-sm w-48 font-normal block bg-white text-slate-900 focus:ring-1 focus:ring-indigo-500" title={`Contact: ${ev.contact_name}`} />
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
                          ) : isMissingRequired ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded-md border border-red-200">
                              <AlertCircle size={12} /> REQUIRED
                            </span>
                          ) : isDuplicate ? (
                            <div className="flex items-center gap-1.5 text-amber-700 font-semibold">
                              <AlertCircle size={14} className="text-amber-500 shrink-0" />
                              <span className="truncate">{row.data[key]}</span>
                            </div>
                          ) : row.data[key] ? (
                            row.data[key]
                          ) : (
                            <span className="text-slate-300">-</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 text-sm">
                      <div className="space-y-2">
                      {row.emails_to_verify?.map((ev, i) => (
                        <div key={i} className="flex flex-col items-start">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500 font-medium w-16">{ev.type === 'company' ? 'Company' : 'Contact'}:</span>
                            {ev.status === 'VALID' && <span className="text-emerald-600 font-medium bg-emerald-100 px-2 py-1 rounded text-xs">VALID</span>}
                            {ev.status === 'INVALID' && <span className="text-red-600 font-medium bg-red-100 px-2 py-1 rounded text-xs">INVALID</span>}
                            {ev.status === 'UNVERIFIED' && <span className="text-slate-500 bg-slate-100 px-2 py-1 rounded text-xs">UNVERIFIED</span>}
                            {ev.status === 'UNKNOWN' && <span className="text-amber-600 font-medium bg-amber-100 px-2 py-1 rounded text-xs">UNKNOWN</span>}
                          </div>
                          {ev.status === 'INVALID' && <p className="text-xs text-red-500 mt-1 pl-18">{ev.reason}</p>}
                        </div>
                      ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-red-600">
                      {row.errors.map((err, i) => <div key={i}>• {err}</div>)}
                    </td>
                    <td className="px-4 py-3 text-center whitespace-nowrap">
                      <button
                        onClick={() => handleRemoveRow(index)}
                        className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                        title="Remove Row"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImportPreviewPage;
