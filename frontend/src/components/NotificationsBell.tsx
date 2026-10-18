import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Loader2, Inbox } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { Notification } from '../types';
import NotificationItem, { NOTIFICATIONS_QUERY_KEY, BELL_LIMIT } from './NotificationItem';

export default function NotificationsBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: notifications, isLoading } = useQuery<Notification[]>({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: async () => {
      const { data } = await api.get('/notifications/', { params: { limit: 100 } });
      return data;
    },
  });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Determine WS protocol and host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // If we're in dev mode (Vite), the backend is likely on :8000
    const isDev = window.location.port === '5173' || window.location.hostname === 'localhost';
    const wsHost = isDev ? 'localhost:8000' : window.location.host;
    // URL construction should be extremely explicit
    const wsUrl = `${protocol}//${wsHost.replace(/\/$/, '')}/ws?token=${token}`;

    let socket: WebSocket | null = null;
    let reconnectTimeout: any;
    let isComponentMounted = true;

    const connect = () => {
      if (!isComponentMounted) return;

      socket = new WebSocket(wsUrl);

      socket.onmessage = (event) => {
        if (!isComponentMounted) return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'notification') {
            queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });

            if (window.Notification && window.Notification.permission === 'granted') {
              new window.Notification(message.data.title, {
                body: message.data.message,
                icon: '/favicon.ico'
              });
            }
          }
        } catch (err) {
          console.error('Error parsing WS message:', err);
        }
      };

      socket.onopen = () => {
        if (isComponentMounted) console.log('WebSocket connected');
      };

      socket.onclose = (event) => {
        // Only reconnect if the closure wasn't intentional (not code 1000)
        // and component is still mounted
        if (isComponentMounted && event.code !== 1000) {
          console.log('WebSocket disconnected, reconnecting...');
          reconnectTimeout = setTimeout(connect, 3000);
        }
      };

      socket.onerror = (err) => {
        // In Strict Mode, closing a connection during handshake triggers this
        if (isComponentMounted) {
          console.error('WebSocket error:', err);
        }
      };
    };

    connect();

    // Request browser notification permission
    if (window.Notification && window.Notification.permission === 'default') {
      window.Notification.requestPermission();
    }

    return () => {
      isComponentMounted = false;
      if (socket) {
        // Use code 1000 (Normal Closure) to signal intentional close
        socket.close(1000);
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [queryClient]);

  const all = notifications ?? [];
  const recent = all.slice(0, BELL_LIMIT);
  const unreadCount = all.filter((n) => !n.is_read).length;
  const hasMore = all.length > BELL_LIMIT;

  const markAllRead = () => {
    api.patch('/notifications/read-all').then(() =>
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY })
    );
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-1.5 hover:bg-[#30363d] rounded-md text-gray-400 hover:text-white transition relative"
        title={t('notifications.title')}
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute top-0 right-0 w-4 h-4 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center border-2 border-[#1f2328]">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-80 bg-white border border-[#d0d7de] rounded-lg shadow-xl z-50 overflow-hidden text-left">
            <div className="px-4 py-3 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
              <h3 className="text-xs font-bold text-[#1f2328]">{t('notifications.title')}</h3>
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-[10px] text-[#0969da] hover:underline font-semibold"
                >
                  {t('notifications.read_all')}
                </button>
              )}
            </div>

            {/* Показываем только 7 последних уведомлений */}
            <div className="max-h-96 overflow-y-auto divide-y divide-[#d0d7de]">
              {isLoading ? (
                <div className="p-8 text-center">
                  <Loader2 className="animate-spin mx-auto text-gray-400" size={24} />
                </div>
              ) : recent.length === 0 ? (
                <div className="p-8 text-center text-xs text-gray-500">{t('notifications.empty')}</div>
              ) : (
                recent.map((n) => <NotificationItem key={n.id} notification={n} />)
              )}
            </div>

            <div className="border-t border-[#d0d7de] bg-[#f6f8fa] px-4 py-2 text-center">
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/dashboard');
                }}
                className="text-[11px] font-semibold text-[#0969da] hover:underline flex items-center justify-center gap-1.5 w-full py-1"
              >
                {hasMore && <Inbox size={12} />}
                {t('notifications.show_all')}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
