import { useNavigate } from 'react-router-dom'
import { Users, Shield, FolderKanban, ChevronRight, UserPlus, Settings, Brain, HardDrive } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function AdminPanel() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const sections = [
    {
      id: 'users',
      title: t('admin.users_management'),
      icon: <Users className="text-blue-500" size={24} />,
      path: '/admin/users',
      desc: t('admin.users_desc')
    },
    {
      id: 'roles',
      title: t('admin.roles_management'),
      icon: <Shield className="text-purple-500" size={24} />,
      path: '/admin/roles',
      desc: t('admin.roles_desc')
    },
    {
      id: 'projects',
      title: t('admin.projects_management'),
      icon: <FolderKanban className="text-orange-500" size={24} />,
      path: '/admin/projects',
      desc: t('admin.projects_desc')
    },
    {
      id: 'models',
      title: t('admin.models_management'),
      icon: <Brain className="text-purple-500" size={24} />,
      path: '/admin/models',
      desc: t('admin.models_desc')
    },
    {
      id: 'storage',
      title: t('admin.storage_management'),
      icon: <HardDrive className="text-teal-600" size={24} />,
      path: '/admin/storage',
      desc: t('admin.storage_desc')
    }
  ]

  return (
    <div className="flex-1 p-8 max-w-5xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#1f2328]">{t('admin.title')}</h1>
        <p className="text-[#636c76]">System-wide administrative controls and monitoring.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {sections.map(section => (
          <button
            key={section.id}
            onClick={() => navigate(section.path)}
            className="flex flex-col items-start p-6 bg-white border border-[#d0d7de] rounded-lg hover:border-blue-500 hover:shadow-md transition-all group text-left"
          >
            <div className="p-3 bg-gray-50 rounded-lg mb-4 group-hover:bg-blue-50 transition-colors">
              {section.icon}
            </div>
            <h3 className="text-lg font-semibold text-[#1f2328] mb-2 flex items-center gap-2">
              {section.title}
              <ChevronRight size={18} className="text-gray-400 group-hover:text-blue-500 transform group-hover:translate-x-1 transition-all" />
            </h3>
            <p className="text-sm text-[#636c76] leading-relaxed">
              {section.desc}
            </p>
          </button>
        ))}
      </div>

      <div className="mt-12 p-6 bg-blue-50 border border-blue-100 rounded-lg flex items-start gap-4">
        <div className="p-2 bg-white rounded-full text-blue-600 border border-blue-100">
          <Settings size={20} />
        </div>
        <div>
          <h4 className="font-semibold text-blue-900 mb-1">Administrative Privileges</h4>
          <p className="text-sm text-blue-800 opacity-80">
            As a superuser, you have unrestricted access to all system data. Changes made here can affect the entire platform and all user projects.
          </p>
        </div>
      </div>
    </div>
  )
}
