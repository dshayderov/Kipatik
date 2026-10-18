import React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  X,
  Loader2,
  Info,
  UserPlus,
  ClipboardList,
  GitPullRequest,
  RefreshCw,
  MessageSquare,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { Notification } from '../types';

/** Общий ключ запроса: колокольчик и панель на главной используют один кэш */
export const NOTIFICATIONS_QUERY_KEY = ['notifications'];

/** Сколько уведомлений показываем в выпадающем списке колокольчика */
export const BELL_LIMIT = 7;

export function formatRelativeTime(date: string, lang: string) {
  const now = new Date();
  const diff = now.getTime() - new Date(date).getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' });

  if (days > 0) return rtf.format(-days, 'day');
  if (hours > 0) return rtf.format(-hours, 'hour');
  if (minutes > 0) return rtf.format(-minutes, 'minute');
  return rtf.format(-seconds, 'second');
}

const ICON_STYLES: Record<string, { icon: React.ReactNode; className: string }> = {
  project_invite: { icon: <UserPlus size={16} />, className: 'text-blue-500' },
  task_assigned: { icon: <ClipboardList size={16} />, className: 'text-green-600' },
  task_updated: { icon: <RefreshCw size={16} />, className: 'text-amber-500' },
  pr_review_requested: { icon: <GitPullRequest size={16} />, className: 'text-purple-500' },
  info: { icon: <Info size={16} />, className: 'text-gray-500' },
};

export function NotificationIcon({ type }: { type: string }) {
  const style = ICON_STYLES[type] ?? ICON_STYLES.info;
  return <span className={style.className}>{style.icon}</span>;
}

interface NotificationItemProps {
  notification: Notification;
  /** Плотный режим для выпадающего списка колокольчика */
  compact?: boolean;
}

export default function NotificationItem({ notification: n, compact = false }: NotificationItemProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
    queryClient.invalidateQueries({ queryKey: ['projects'] });
  };

  const markReadMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.patch(`/notifications/${id}/read`);
    },
    onSuccess: invalidate,
  });

  const acceptInviteMutation = useMutation({
    mutationFn: async (inviteId: number) => {
      await api.post(`/projects/invites/${inviteId}/accept`);
    },
    onSuccess: invalidate,
  });

  const declineInviteMutation = useMutation({
    mutationFn: async (inviteId: number) => {
      await api.post(`/projects/invites/${inviteId}/decline`);
    },
    onSuccess: invalidate,
  });

  const isInvite = n.type === 'project_invite';
  const isPending =
    markReadMutation.isPending || acceptInviteMutation.isPending || declineInviteMutation.isPending;

  const handleMarkRead = () => {
    if (!n.is_read) markReadMutation.mutate(n.id);
  };

  return (
    <div
      onClick={handleMarkRead}
      className={`${compact ? 'p-4' : 'p-4 border-b border-[#f0f2f4] last:border-b-0'} hover:bg-[#f6f8fa] transition-colors ${
        !n.is_read ? 'bg-blue-50/30 cursor-pointer' : ''
      }`}
    >
      <div className="flex gap-3">
        <div className="mt-0.5 shrink-0">
          <NotificationIcon type={n.type} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-bold text-[#1f2328] truncate">{n.title}</p>
            <span className="text-[9px] text-gray-500 shrink-0">
              {formatRelativeTime(n.created_at, i18n.language)}
            </span>
          </div>
          <p className="text-[10px] text-[#636c76] mt-0.5 line-clamp-2">{n.message}</p>

          {isInvite && !n.is_read && n.invite_id && (
            <div className="flex gap-2 mt-3">
              <button
                disabled={isPending}
                onClick={(e) => {
                  e.stopPropagation();
                  acceptInviteMutation.mutate(n.invite_id!);
                }}
                className="flex-1 bg-[#1f883d] text-white py-1 rounded text-[10px] font-bold hover:bg-[#1a7f37] disabled:opacity-60 flex items-center justify-center gap-1"
              >
                <Check size={12} /> {t('notifications.accept')}
              </button>
              <button
                disabled={isPending}
                onClick={(e) => {
                  e.stopPropagation();
                  declineInviteMutation.mutate(n.invite_id!);
                }}
                className="flex-1 bg-white border border-[#d0d7de] text-[#cf222e] py-1 rounded text-[10px] font-bold hover:bg-[#f6f8fa] disabled:opacity-60 flex items-center justify-center gap-1"
              >
                <X size={12} /> {t('notifications.decline')}
              </button>
            </div>
          )}

          {!n.is_read && !isInvite && (
            <button
              disabled={isPending}
              onClick={(e) => {
                e.stopPropagation();
                markReadMutation.mutate(n.id);
              }}
              className="mt-2 text-[10px] text-[#0969da] hover:underline disabled:opacity-60 flex items-center gap-1"
            >
              {isPending ? <Loader2 size={10} className="animate-spin" /> : <MessageSquare size={10} />}
              {t('notifications.mark_read')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
