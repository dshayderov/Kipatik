import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import i18n from '../i18n';
import api from '../api/client';
import { User, AuthState, AuthToken } from '../types';

/** Поддерживаемые языки интерфейса */
export const SUPPORTED_LANGUAGES = ['en', 'ru'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/**
 * Приводит значение языка к поддерживаемому.
 * Защищает от мусора в БД ('zh', 'ru-RU', '') — такие значения
 * приводили к «некорректно отображаемому» языку в профиле.
 */
export function normalizeLanguage(value?: string | null): SupportedLanguage {
  if (!value) return 'en';
  const v = String(value).toLowerCase().trim();
  if (v.startsWith('ru')) return 'ru';
  if (v.startsWith('en')) return 'en';
  return 'en';
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  /** Перечитывает профиль с сервера (после изменения языка/имени и т.п.) */
  refreshUser: () => Promise<User | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: localStorage.getItem('token'),
    isAuthenticated: false,
    isLoading: true,
  });

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const { data: user } = await api.get<User>('/users/me');
          // Язык из профиля приоритетнее определения браузера
          if (user.language) {
            i18n.changeLanguage(normalizeLanguage(user.language));
          }
          setState({
            user,
            token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          localStorage.removeItem('token');
          setState({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
      } else {
        setState(prev => ({ ...prev, isLoading: false }));
      }
    };

    initAuth();
  }, []);

  const refreshUser = async (): Promise<User | null> => {
    const token = localStorage.getItem('token');
    if (!token) return null;
    try {
      const { data: user } = await api.get<User>('/users/me');
      setState((prev) => ({ ...prev, user, isAuthenticated: true }));
      return user;
    } catch (error) {
      return null;
    }
  };

  const login = async (email: string, password: string) => {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);

    const { data } = await api.post<AuthToken>('/auth/login', formData);
    localStorage.setItem('token', data.access_token);

    const { data: user } = await api.get<User>('/users/me');

    if (user.language) {
      i18n.changeLanguage(normalizeLanguage(user.language));
    }

    setState({
      user,
      token: data.access_token,
      isAuthenticated: true,
      isLoading: false,
    });
  };

  const register = async (email: string, password: string, fullName: string) => {
    await api.post('/auth/register', {
      email,
      password,
      full_name: fullName,
    });
    // After registration, we can either auto-login or redirect to login
    await login(email, password);
  };

  const logout = () => {
    localStorage.removeItem('token');
    setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
    });
  };

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
