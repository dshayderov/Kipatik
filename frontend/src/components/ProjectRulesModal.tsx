import React, { useState } from 'react';
import { 
  X, 
  ShieldCheck, 
  UserPlus, 
  Lock, 
  Calendar, 
  CheckCircle2, 
  AlertCircle,
  Save,
  Check,
  Database,
  Play,
  Trash2,
  Plus
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { Project, Column } from '../types';

interface ProjectRulesModalProps {
  project: Project;
  columns: Column[];
  onClose: () => void;
  onUpdated: () => void;
}

const ProjectRulesModal: React.FC<ProjectRulesModalProps> = ({ project, columns, onClose, onUpdated }) => {
  const { t } = useTranslation();
  const [isSaving, setIsSaving] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [sqlStatus, setSqlValid] = useState<{ status: 'idle' | 'valid' | 'invalid', message?: string }>({ status: 'idle' });
  const [newSqlQuery, setNewSqlQuery] = useState('');
  
  const [rules, setRules] = useState(project.rules || {
    required_fields: ['title'],
    auto_assign_on_move: false,
    column_role_locks: {},
    start_date_logic: 'created_at',
    custom_sql_rules: []
  });

  const availableFields = [
    { id: 'description', label: t('tasks.description') },
    { id: 'due_date', label: t('tasks.due_date') },
    { id: 'assignee_id', label: t('tasks.assignee') },
    { id: 'priority', label: t('tasks.priority') }
  ];

  const roles = [
    { id: 'project_manager', label: t('roles.project_manager') },
    { id: 'manager', label: t('roles.manager') },
    { id: 'developer', label: t('roles.developer') },
    { id: 'tester', label: t('roles.tester') },
    { id: 'observer', label: t('roles.observer') }
  ];

  const handleToggleField = (fieldId: string) => {
    const current = [...rules.required_fields];
    if (current.includes(fieldId)) {
      setRules({ ...rules, required_fields: current.filter(f => f !== fieldId) });
    } else {
      setRules({ ...rules, required_fields: [...current, fieldId] });
    }
  };

  const handleToggleColumnRole = (columnId: number, roleId: string) => {
    const currentLocks = { ...rules.column_role_locks };
    const colIdStr = columnId.toString();
    const currentRoles = currentLocks[colIdStr] || [];

    if (currentRoles.includes(roleId)) {
      currentLocks[colIdStr] = currentRoles.filter(r => r !== roleId);
      if (currentLocks[colIdStr].length === 0) {
        delete currentLocks[colIdStr];
      }
    } else {
      currentLocks[colIdStr] = [...currentRoles, roleId];
    }

    setRules({ ...rules, column_role_locks: currentLocks });
  };

  const handleVerifySql = async () => {
    if (!newSqlQuery.trim()) return;
    setIsVerifying(true);
    try {
      const { data } = await api.post(`/projects/${project.id}/verify-sql`, { query: newSqlQuery });
      if (data.status === 'valid') {
        setSqlValid({ status: 'valid' });
      } else {
        setSqlValid({ status: 'invalid', message: data.error });
      }
    } catch (err) {
      setSqlValid({ status: 'invalid', message: 'Connection error' });
    } finally {
      setIsVerifying(false);
    }
  };

  const handleAddSqlRule = () => {
    if (sqlStatus.status !== 'valid' || !newSqlQuery.trim()) return;
    const currentSqlRules = rules.custom_sql_rules || [];
    setRules({
      ...rules,
      custom_sql_rules: [...currentSqlRules, { id: Date.now(), query: newSqlQuery }]
    });
    setNewSqlQuery('');
    setSqlValid({ status: 'idle' });
  };

  const handleRemoveSqlRule = (id: number) => {
    setRules({
      ...rules,
      custom_sql_rules: (rules.custom_sql_rules || []).filter((r: any) => r.id !== id)
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await api.patch(`/projects/${project.id}`, { rules });
      onUpdated();
      onClose();
    } catch (err) {
      alert(t('projects.update_error'));
    } finally {
      setIsSaving(false);
    }
  };

  const RuleSection = ({ icon: Icon, title, children, colorClass }: any) => (
    <div className="bg-white border border-[#d0d7de] rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      <div className={`px-4 py-3 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center gap-3 ${colorClass}`}>
        <Icon size={18} />
        <h4 className="font-bold text-sm text-[#1f2328]">{title}</h4>
      </div>
      <div className="p-5">
        {children}
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-6 border-b border-[#d0d7de] flex items-center justify-between bg-[#f6f8fa] rounded-t-xl">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 text-white rounded-lg shadow-inner">
              <ShieldCheck size={24} />
            </div>
            <div>
              <h3 className="text-xl font-bold text-[#1f2328]">{t('projects.rules.title')}</h3>
              <p className="text-sm text-[#636c76] font-medium">{project.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-200 rounded-full transition-colors">
            <X size={20} className="text-[#636c76]" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-[#f6f8fa]/30">
          
          <RuleSection icon={CheckCircle2} title={t('projects.rules.required_fields')} colorClass="text-blue-600">
            <div className="grid grid-cols-2 gap-3">
              {availableFields.map(field => (
                <button
                  key={field.id}
                  onClick={() => handleToggleField(field.id)}
                  className={`flex items-center justify-between p-3 rounded-lg border transition-all text-left ${
                    rules.required_fields.includes(field.id)
                      ? 'bg-blue-50 border-blue-200 text-blue-700 ring-1 ring-blue-100'
                      : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-gray-50'
                  }`}
                >
                  <span className="text-xs font-bold">{field.label}</span>
                  {rules.required_fields.includes(field.id) && <Check size={14} strokeWidth={3} />}
                </button>
              ))}
            </div>
          </RuleSection>

          <RuleSection icon={UserPlus} title={t('projects.rules.auto_assign')} colorClass="text-green-600">
            <label className="flex items-start gap-3 p-4 bg-white border border-[#d0d7de] rounded-lg cursor-pointer hover:border-green-300 transition-colors">
              <input
                type="checkbox"
                className="mt-1 w-4 h-4 text-green-600 rounded border-gray-300 focus:ring-green-500"
                checked={rules.auto_assign_on_move}
                onChange={(e) => setRules({ ...rules, auto_assign_on_move: e.target.checked })}
              />
              <div>
                <span className="text-sm font-bold text-[#1f2328] block">{t('projects.rules.auto_assign')}</span>
                <span className="text-xs text-[#636c76] font-medium">{t('projects.rules.auto_assign_desc')}</span>
              </div>
            </label>
          </RuleSection>

          <RuleSection icon={Calendar} title={t('projects.rules.start_date_logic')} colorClass="text-purple-600">
            <div className="space-y-2">
              {[
                { id: 'created_at', label: t('projects.rules.start_date_created') },
                { id: 'manual_pm', label: t('projects.rules.start_date_pm') },
                { id: 'manual_assignee', label: t('projects.rules.start_date_assignee') }
              ].map(logic => (
                <button
                  key={logic.id}
                  onClick={() => setRules({ ...rules, start_date_logic: logic.id as any })}
                  className={`w-full flex items-center justify-between p-3 rounded-lg border transition-all ${
                    rules.start_date_logic === logic.id
                      ? 'bg-purple-50 border-purple-200 text-purple-700 ring-1 ring-purple-100'
                      : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-gray-50'
                  }`}
                >
                  <span className="text-sm font-bold">{logic.label}</span>
                  {rules.start_date_logic === logic.id && <Check size={14} strokeWidth={3} />}
                </button>
              ))}
            </div>
          </RuleSection>

          <RuleSection icon={Lock} title={t('projects.rules.column_locks')} colorClass="text-amber-600">
            <p className="text-[11px] text-[#636c76] font-medium mb-4">{t('projects.rules.column_locks_desc')}</p>
            <div className="space-y-4">
              {columns.map(column => (
                <div key={column.id} className="p-3 border border-[#d0d7de] rounded-lg bg-white">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                    <span className="text-xs font-bold text-[#1f2328] uppercase tracking-wider">{column.name}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {roles.map(role => (
                      <button
                        key={role.id}
                        onClick={() => handleToggleColumnRole(column.id, role.id)}
                        className={`px-3 py-1 rounded-full text-[10px] font-bold border transition-all ${
                          (rules.column_role_locks[column.id.toString()] || []).includes(role.id)
                            ? 'bg-amber-100 border-amber-300 text-amber-800'
                            : 'bg-gray-50 border-[#d0d7de] text-[#636c76] hover:bg-white'
                        }`}
                      >
                        {role.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </RuleSection>

          <RuleSection icon={Database} title={t('projects.rules.sql_rules')} colorClass="text-red-600">
            <p className="text-[11px] text-[#636c76] font-medium mb-4">{t('projects.rules.sql_rules_desc')}</p>
            
            <div className="space-y-4">
              <div className="relative">
                <textarea
                  value={newSqlQuery}
                  onChange={(e) => { setNewSqlQuery(e.target.value); setSqlValid({ status: 'idle' }); }}
                  className="w-full bg-[#0d1117] text-[#e6edf3] font-mono text-xs p-4 rounded-lg border border-[#30363d] focus:ring-2 focus:ring-blue-500 outline-none min-h-[100px]"
                  placeholder={t('projects.rules.sql_query_placeholder')}
                />
                <div className="absolute bottom-3 right-3 flex gap-2">
                  <button
                    onClick={handleVerifySql}
                    disabled={isVerifying || !newSqlQuery.trim()}
                    className={`px-3 py-1 rounded text-[10px] font-bold flex items-center gap-1.5 transition-all ${
                      sqlStatus.status === 'valid' ? 'bg-green-600 text-white' : 
                      sqlStatus.status === 'invalid' ? 'bg-red-600 text-white' : 
                      'bg-blue-600 text-white hover:bg-blue-500'
                    }`}
                  >
                    {isVerifying ? <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Play size={12} />}
                    {isVerifying ? t('projects.rules.verifying') : t('projects.rules.verify')}
                  </button>
                  {sqlStatus.status === 'valid' && (
                    <button
                      onClick={handleAddSqlRule}
                      className="px-3 py-1 bg-green-600 text-white rounded text-[10px] font-bold flex items-center gap-1.5 hover:bg-green-500 transition-all"
                    >
                      <Plus size={12} />
                      {t('projects.rules.add_rule')}
                    </button>
                  )}
                </div>
              </div>

              {sqlStatus.status === 'invalid' && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                  <AlertCircle className="text-red-600 shrink-0" size={14} />
                  <p className="text-[10px] text-red-700 font-mono leading-tight">{sqlStatus.message}</p>
                </div>
              )}

              {/* Saved SQL Rules */}
              {(rules.custom_sql_rules || []).length > 0 && (
                <div className="space-y-2 mt-4 pt-4 border-t border-[#d0d7de]">
                  <h5 className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">Saved Rules</h5>
                  {(rules.custom_sql_rules || []).map((rule: any) => (
                    <div key={rule.id} className="group relative bg-[#f6f8fa] border border-[#d0d7de] rounded-lg p-3">
                      <pre className="text-[10px] font-mono text-[#1f2328] overflow-x-auto whitespace-pre-wrap">{rule.query}</pre>
                      <button 
                        onClick={() => handleRemoveSqlRule(rule.id)}
                        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1 text-[#636c76] hover:text-red-600 transition-all"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </RuleSection>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-[#d0d7de] flex justify-end gap-3 bg-[#f6f8fa] rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-bold text-[#636c76] hover:bg-gray-200 rounded-lg transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-6 py-2 bg-[#1f883d] text-white text-sm font-bold rounded-lg hover:bg-[#1a7f37] transition-all flex items-center gap-2 shadow-md hover:shadow-lg disabled:opacity-50"
          >
            {isSaving ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Save size={18} />
            )}
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProjectRulesModal;
