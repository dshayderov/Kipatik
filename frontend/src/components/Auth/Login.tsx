import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { GitBranch, Loader2, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const Login: React.FC = () => {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || t('auth.login.error'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f6f8fa] flex flex-col items-center justify-center p-4">
      <div className="mb-8 flex flex-col items-center">
        <GitBranch size={48} className="text-[#1f2328] mb-4" />
        <h1 className="text-2xl font-light text-[#1f2328]">{t('auth.login.title')}</h1>
      </div>

      <div className="bg-white border border-[#d0d7de] rounded-md p-6 w-full max-w-[340px] shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-[#ffebe9] border border-[#ff8182] text-[#cf222e] px-4 py-2 rounded-md text-sm">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-[#1f2328] mb-2">{t('auth.login.email')}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-1.5 border border-[#d0d7de] rounded-md focus:outline-none focus:ring-2 focus:ring-[#0969da] focus:border-transparent text-sm"
              required
            />
          </div>
          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="block text-sm font-medium text-[#1f2328]">{t('auth.login.password')}</label>
              <a href="#" className="text-xs text-[#0969da] hover:underline">{t('auth.login.forgot_password')}</a>
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-[#1f883d] hover:bg-[#1a7f37] text-white font-semibold py-1.5 rounded-md transition duration-200 text-sm flex justify-center items-center gap-2 shadow-sm"
          >
            {isLoading && <Loader2 size={16} className="animate-spin" />}
            {t('auth.login.sign_in')}
          </button>
        </form>
      </div>

      <div className="mt-4 border border-[#d0d7de] rounded-md p-4 w-full max-w-[340px] text-center text-sm">
        {t('auth.login.new_to_system')} <Link to="/register" className="text-[#0969da] hover:underline">{t('auth.login.create_account')}</Link>.
      </div>
    </div>
  );
};

export default Login;
