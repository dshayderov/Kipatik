import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { GitBranch, Loader2, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const Register: React.FC = () => {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await register(email, password, fullName);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || t('auth.register.error'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f6f8fa] flex flex-col items-center justify-center p-4">
      <div className="mb-8 flex flex-col items-center">
        <GitBranch size={48} className="text-[#1f2328] mb-4" />
        <h1 className="text-2xl font-light text-[#1f2328]">{t('auth.register.title')}</h1>
      </div>

      <div className="bg-white border border-[#d0d7de] rounded-md p-6 w-full max-w-[340px] shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-[#ffebe9] border border-[#ff8182] text-[#cf222e] px-4 py-2 rounded-md text-sm">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-[#1f2328] mb-2">{t('auth.register.full_name')}</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-1.5 border border-[#d0d7de] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0969da] focus:border-transparent text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#1f2328] mb-2">{t('auth.register.email')}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-1.5 border border-[#d0d7de] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0969da] focus:border-transparent text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#1f2328] mb-2">{t('admin.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                maxLength={72}
                minLength={8}
                className="w-full px-3 py-1.5 pr-10 border border-[#d0d7de] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0969da] focus:border-transparent text-sm"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-[10px] text-gray-500 mt-1">At least 8 characters, max 72.</p>
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-[#1f883d] hover:bg-[#1a7f37] text-white font-semibold py-1.5 rounded-md transition duration-200 text-sm flex justify-center items-center gap-2 shadow-sm"
          >
            {isLoading && <Loader2 size={16} className="animate-spin" />}
            {t('auth.register.sign_up')}
          </button>
        </form>
      </div>

      <div className="mt-4 border border-[#d0d7de] rounded-md p-4 w-full max-w-[340px] text-center text-sm">
        {t('auth.register.already_have_account')} <Link to="/login" className="text-[#0969da] hover:underline">{t('auth.register.sign_in')}</Link>.
      </div>
    </div>
  );
};

export default Register;
