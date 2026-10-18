import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  X, 
  CheckSquare, 
  MessageSquare, 
  GitCommit, 
  Clock, 
  User as UserIcon, 
  Plus, 
  Trash2, 
  Loader2, 
  ChevronRight,
  Send,
  GitBranch,
  Github,
  RefreshCw,
  ExternalLink,
  AlertCircle,
  MoreHorizontal,
  Edit2,
  Reply,
  Smile,
  Paperclip,
  FileText,
  FileCode,
  Image as ImageIcon,
  Check,
  Link as LinkIcon,
  Calendar
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { Task, SubTask, TaskComment, Column, Project, User, CommentReaction, Attachment } from '../types';
import { TASK_TYPES, TASK_TYPE_STYLE } from '../types/taskType';
import { useAuth } from '../context/AuthContext';
import ActivityTimeline from './activity/ActivityTimeline';
import { ActivityItem } from './activity/activityMeta';
import DevCard from './DevCard';

interface TaskDetailModalProps {
  taskId: number;
  columns: Column[];
  onClose: () => void;
  onUpdated: () => void;
}

const EMOJIS = ['👍', '✅', '👀', '🚀', '❤️', '🔥', '😂', '😮'];

const TaskDetailModal: React.FC<TaskDetailModalProps> = ({ taskId, columns, onClose, onUpdated }) => {
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const [task, setTask] = useState<any | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<User[]>([]);
  const [projectTasks, setProjectTasks] = useState<Task[]>([]);
  const [activeTab, setActiveTab] = useState<'general' | 'discussion' | 'development' | 'history'>('general');
  const [isLoading, setIsLoading] = useState(true);
  
  const [newSubtask, setNewSubtask] = useState('');
  const [newComment, setNewComment] = useState('');
  const [isCreatingBranch, setIsCreatingBranch] = useState(false);
  // Проект может иметь несколько репозиториев — показываем выбранный,
  // раньше молча использовался только первый.
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  // Блок «Разработка»: ветки, PR, коммиты, файлы и провенанс связей
  const [devCard, setDevCard] = useState<any>(null);
  const [devCardLoading, setDevCardLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editCommentContent, setEditCommentContent] = useState('');
  const [editingAttachments, setEditingAttachments] = useState<Attachment[]>([]);
  const [attachmentsToRemove, setAttachmentsToRemove] = useState<string[]>([]);
  
  const [activeCommentMenu, setActiveCommentMenu] = useState<number | null>(null);
  const [replyTo, setReplyTo] = useState<TaskComment | null>(null);
  const [activeEmojiPicker, setActiveEmojiPicker] = useState<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  
  const [showMentionSuggestions, setShowMentionSuggestions] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [cursorPos, setCursorPos] = useState(0);

  const [isAddingDependency, setIsAddingDependency] = useState(false);
  const [dependencySearch, setDependencySearch] = useState('');

  const commentsEndRef = useRef<HTMLDivElement>(null);
  const emojiAnchorRef = useRef<HTMLButtonElement | null>(null);
  const menuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchTask();
  }, [taskId]);

  useEffect(() => {
    let interval: any;
    if (activeTab === 'discussion') {
      interval = setInterval(() => {
        fetchTask(true);
      }, 5000);
    }
    return () => clearInterval(interval);
  }, [activeTab, taskId]);

  useEffect(() => {
    if (activeTab === 'discussion') {
      scrollToBottom();
    }
  }, [activeTab, task?.comments?.length]);

  /**
   * Позиция всплывающего окна реакций в координатах экрана (fixed).
   * Панель не может «уехать» за пределы окна: если снизу мало места,
   * открывается вверх, по горизонтали прижимается к краю экрана.
   */
  const computeEmojiPosition = () => {
    const anchor = emojiAnchorRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();

    const PANEL_W = 272;
    const PANEL_H = 88;
    const MARGIN = 8;

    const left = Math.min(
      Math.max(MARGIN, rect.left - PANEL_W + rect.width),
      window.innerWidth - PANEL_W - MARGIN
    );

    const spaceBelow = window.innerHeight - rect.bottom;
    const top =
      spaceBelow >= PANEL_H + MARGIN
        ? rect.bottom + 6
        : Math.max(MARGIN, rect.top - PANEL_H - 6);

    return { top, left };
  };

  const [emojiPos, setEmojiPos] = useState<{ top: number; left: number } | null>(null);

  const toggleEmojiPicker = (commentId: number, anchor: HTMLButtonElement) => {
    if (activeEmojiPicker === commentId) {
      setActiveEmojiPicker(null);
      setEmojiPos(null);
      return;
    }
    emojiAnchorRef.current = anchor;
    setActiveEmojiPicker(commentId);
    setActiveCommentMenu(null);
    setEmojiPos(computeEmojiPosition());
  };

  // Пересчитываем позицию при скролле ленты и ресайзе окна
  useEffect(() => {
    if (activeEmojiPicker === null) return;

    const reposition = () => {
      setEmojiPos(computeEmojiPosition());
    };
    const close = () => {
      setActiveEmojiPicker(null);
      setEmojiPos(null);
    };

    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', close, true);
    };
  }, [activeEmojiPicker]);

  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);

  /** Позиция меню действий комментария (fixed, не обрезается краем окна) */
  const computeMenuPosition = () => {
    const anchor = menuAnchorRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const PANEL_W = 160;
    const PANEL_H = 96;
    const MARGIN = 8;

    const left = Math.min(
      Math.max(MARGIN, rect.right - PANEL_W),
      window.innerWidth - PANEL_W - MARGIN
    );
    const spaceBelow = window.innerHeight - rect.bottom;
    const top =
      spaceBelow >= PANEL_H + MARGIN
        ? rect.bottom + 4
        : Math.max(MARGIN, rect.top - PANEL_H - 4);

    return { top, left };
  };

  const toggleCommentMenu = (commentId: number, anchor: HTMLButtonElement) => {
    if (activeCommentMenu === commentId) {
      setActiveCommentMenu(null);
      setMenuPos(null);
      return;
    }
    menuAnchorRef.current = anchor;
    setActiveCommentMenu(commentId);
    setActiveEmojiPicker(null);
    setEmojiPos(null);
    setMenuPos(computeMenuPosition());
  };

  useEffect(() => {
    if (activeCommentMenu === null) return;

    const reposition = () => setMenuPos(computeMenuPosition());
    const close = () => {
      setActiveCommentMenu(null);
      setMenuPos(null);
    };

    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', close, true);
    };
  }, [activeCommentMenu]);

  const scrollToBottom = () => {
    // Скроллим только контейнер ленты, иначе scrollIntoView дёргал бы
    // и всё окно задачи, и сайдбар
    const el = chatScrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  };

  const loadDevCard = async () => {
    if (activeTab !== 'development') return;
    try {
      const { data } = await api.get(`/git/task/${taskId}/card`);
      setDevCard(data);
    } catch (err: any) {
      console.error('Не удалось загрузить блок «Разработка»', err);
      setDevCard(null);
    }
  };

  useEffect(() => {
    loadDevCard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, activeTab]);

  const fetchTask = async (silent = false) => {
    try {
      if (!silent) setIsLoading(true);
      const { data } = await api.get(`/tasks/${taskId}`);
      setTask(data);
      if (!silent) {
        const [projectRes, membersRes, tasksRes] = await Promise.all([
          api.get(`/projects/${data.project_id}`),
          api.get(`/projects/${data.project_id}/members`),
          api.get(`/tasks/?project_id=${data.project_id}`)
        ]);
        setProject(projectRes.data);
        setMembers(membersRes.data);
        setProjectTasks(tasksRes.data);
      }
    } catch (err) {
      if (!silent) {
        alert(t('tasks.load_error'));
        onClose();
      }
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  const handleUpdateTask = async (updates: any) => {
    try {
      const { data } = await api.patch(`/tasks/${taskId}`, updates);
      setTask(data);
      onUpdated();
    } catch (err: any) {
      alert(err.response?.data?.detail || t('tasks.update_error'));
    }
  };

  /**
   * История задачи: события активности + связанные с задачей git-объекты
   * (ветки, коммиты, pull request'ы). Формат тот же, что у истории проекта,
   * поэтому лента, фильтры и группировка по дням общие.
   */
  const taskHistoryItems: ActivityItem[] = useMemo(() => {
    if (!task) return [];

    const items: ActivityItem[] = (task.activities || []).map((a: any) => ({
      type: 'task' as const,
      id: a.id,
      created_at: a.created_at,
      activity_type: a.activity_type,
      description: a.description,
      old_value: a.old_value,
      new_value: a.new_value,
      user: a.user,
      task_id: task.id,
    }));

    const repoList = project?.repositories || [];
    const repo = repoList.find((r) => r.id === selectedRepoId) || repoList[0];
    const provider = repo?.provider;

    (task.branches || []).forEach((b: any) => {
      items.push({
        type: 'git',
        id: `b${b.id}`,
        created_at: b.created_at,
        event_type: 'branch_created',
        provider,
        payload: { branch: b.name },
      });
    });

    (task.commits || []).forEach((c: any) => {
      items.push({
        type: 'git',
        id: `c${c.id}`,
        created_at: c.timestamp || c.created_at,
        event_type: 'push',
        provider,
        payload: {
          commits: [{ sha: c.sha, message: c.message, author: { name: c.author } }],
        },
      });
    });

    (task.pull_requests || []).forEach((pr: any) => {
      items.push({
        type: 'git',
        id: `p${pr.id}`,
        created_at: pr.created_at,
        event_type: 'pull_request',
        provider,
        payload: {
          pull_request: {
            title: pr.title,
            state: pr.state,
            url: pr.url,
          },
        },
      });
    });

    return items.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }, [task, project, selectedRepoId]);

  const handleAddDependency = async (depId: number) => {
    const currentDeps = task.dependencies || [];
    if (currentDeps.includes(depId)) return;
    
    await handleUpdateTask({
      dependency_ids: [...currentDeps, depId]
    });
    setIsAddingDependency(false);
    setDependencySearch('');
  };

  const handleRemoveDependency = async (depId: number) => {
    const currentDeps = task.dependencies || [];
    await handleUpdateTask({
      dependency_ids: currentDeps.filter((id: number) => id !== depId)
    });
  };

  const projectRepos = project?.repositories || [];
  const activeRepo = projectRepos.find((r) => r.id === selectedRepoId) || projectRepos[0];

  const userRole = project?.user_role || 'observer';
  const isObserver = userRole === 'observer';
  const canAssignOthers = ['project_manager', 'manager'].includes(userRole);
  const canAssignSelf = ['project_manager', 'manager', 'developer', 'tester'].includes(userRole);
  const canDelete = ['project_manager', 'manager'].includes(userRole);

  const handleTakeTask = () => {
    if (currentUser) {
      handleUpdateTask({ assignee_id: currentUser.id });
    }
  };

  const currentAssignee = members.find(m => m.id === task?.assignee_id);

  const handleAddSubtask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubtask.trim()) return;
    try {
      await api.post(`/tasks/${taskId}/subtasks`, { title: newSubtask, task_id: taskId });
      setNewSubtask('');
      fetchTask(true);
      onUpdated();
    } catch (err) {
      alert(t('tasks.add_subtask_error'));
    }
  };

  const toggleSubtask = async (subtask: SubTask) => {
    try {
      await api.patch(`/tasks/subtasks/${subtask.id}`, { ...subtask, is_completed: !subtask.is_completed });
      fetchTask(true);
      onUpdated();
    } catch (err) {
      alert(t('tasks.update_subtask_error'));
    }
  };

  const deleteSubtask = async (subtaskId: number) => {
    if (!window.confirm(t('common.delete_confirm') || 'Are you sure?')) return;
    try {
      await api.delete(`/tasks/subtasks/${subtaskId}`);
      fetchTask(true);
      onUpdated();
    } catch (err) {
      alert(t('tasks.update_subtask_error'));
    }
  };

  const handleDeleteComment = async (commentId: number) => {
    if (!window.confirm(t('tasks.delete_comment_confirm'))) return;
    try {
      await api.delete(`/tasks/comments/${commentId}`);
      setTask((prev: any) => ({
        ...prev,
        comments: prev.comments.filter((c: any) => c.id !== commentId)
      }));
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete comment');
    }
  };

  const handleEditComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCommentId || (!editCommentContent.trim() && editingAttachments.length === 0)) return;
    try {
      const { data } = await api.patch(`/tasks/comments/${editingCommentId}`, { 
        content: editCommentContent,
        attachments_to_remove: attachmentsToRemove
      });
      setTask((prev: any) => ({
        ...prev,
        comments: prev.comments.map((c: any) => c.id === editingCommentId ? data : c)
      }));
      setEditingCommentId(null);
      setEditCommentContent('');
      setEditingAttachments([]);
      setAttachmentsToRemove([]);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update comment');
    }
  };

  const startEditing = (comment: TaskComment) => {
    setEditingCommentId(comment.id);
    setEditCommentContent(comment.content);
    setEditingAttachments(comment.attachments || []);
    setAttachmentsToRemove([]);
    setActiveCommentMenu(null);
  };

  const handleRemoveEditingAttachment = (attachmentId: string) => {
    setAttachmentsToRemove(prev => [...prev, attachmentId]);
    setEditingAttachments(prev => prev.filter(a => a.id !== attachmentId));
  };

  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim() && pendingAttachments.length === 0) return;
    try {
      const content = replyTo 
        ? `> ${replyTo.author?.full_name || replyTo.author?.email}: ${replyTo.content.substring(0, 50)}${replyTo.content.length > 50 ? '...' : ''}\n\n${newComment}`
        : newComment;

      const { data } = await api.post(`/tasks/${taskId}/comments`, { 
        content, 
        task_id: taskId,
        parent_id: replyTo?.id,
        attachment_ids: pendingAttachments.map(a => a.id)
      });
      
      setNewComment('');
      setReplyTo(null);
      setPendingAttachments([]);
      setTask((prev: any) => ({
        ...prev,
        comments: [...prev.comments, data]
      }));
      onUpdated();
    } catch (err) {
      alert(t('tasks.add_comment_error'));
    }
  };

  const toggleReaction = async (commentId: number, emoji: string) => {
    try {
      await api.post(`/tasks/comments/${commentId}/reactions?emoji=${encodeURIComponent(emoji)}`);
      fetchTask(true);
    } catch (err) {
      console.error("Failed to toggle reaction", err);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (pendingAttachments.length + files.length > 5) {
      alert(t('tasks.max_files_error'));
      return;
    }

    setIsUploading(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        
        if (file.size > 25 * 1024 * 1024) {
          alert(`${file.name}: ${t('tasks.file_too_large')}`);
          continue;
        }

        const formData = new FormData();
        formData.append('file', file);

        const { data } = await api.post(`/tasks/${taskId}/attachments`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        
        setPendingAttachments(prev => [...prev, data]);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || t('tasks.upload_error'));
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removePendingAttachment = async (attachmentId: string) => {
    try {
      await api.delete(`/tasks/attachments/${attachmentId}`);
      setPendingAttachments(prev => prev.filter(a => a.id !== attachmentId));
    } catch (err) {
      console.error("Failed to delete attachment", err);
    }
  };

  const handleDownload = async (attachment: Attachment) => {
    try {
      const response = await api.get(`/tasks/attachments/${attachment.id}/download`, {
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', attachment.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed", err);
      alert(t('tasks.download_error') || "Failed to download file");
    }
  };

  const renderCommentContent = (content: string) => {
    if (content.startsWith('> ')) {
      const parts = content.split('\n\n');
      const quote = parts[0].substring(2).trim();
      const rest = parts.slice(1).join('\n\n');
      return (
        <div className="space-y-2">
          <div className="border-l-4 border-blue-200 bg-blue-50/50 p-2 rounded text-xs text-gray-600 italic mb-2">
            {quote}
          </div>
          {rest && renderTextContent(rest)}
        </div>
      );
    }
    return renderTextContent(content);
  };

  const renderTextContent = (text: string) => {
    const codeBlockRegex = /```([\s\S]*?)```/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
      }
      parts.push({ type: 'code', content: match[1] });
      lastIndex = codeBlockRegex.lastIndex;
    }
    if (lastIndex < text.length) {
      parts.push({ type: 'text', content: text.substring(lastIndex) });
    }

    return (
      <div className="whitespace-pre-wrap break-words">
        {parts.map((part, index) => {
          if (part.type === 'code') {
            return (
              <pre key={index} className="bg-gray-100 p-3 rounded-md my-2 font-mono text-xs overflow-x-auto border border-gray-200">
                {part.content}
              </pre>
            );
          }
          return processInlineMarkdown(part.content, index);
        })}
      </div>
    );
  };

  const processInlineMarkdown = (text: string, keyPrefix: number) => {
    return text.split('\n').map((line, i) => (
      <div key={`${keyPrefix}-${i}`} className="min-h-[1.2em]">
        {processLine(line)}
      </div>
    ));
  };

  const processLine = (line: string) => {
    const mdRegex = /(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*.*?\*|`.*?`|\[.*?\]\(.*?\)|@[\w.-]+|#commit\s+[a-f0-9]{7,40})/gi;
    const parts = line.split(mdRegex);
    
    return parts.map((part, idx) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={idx} className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-xs border border-gray-200">{part.replace(/`/g, '')}</code>;
      }
      if (part.startsWith('***') && part.endsWith('***')) {
        return <strong key={idx}><em>{part.replace(/\*\*\*/g, '')}</em></strong>;
      }
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={idx}>{part.replace(/\*\*/g, '')}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return <em key={idx}>{part.replace(/\*/g, '')}</em>;
      }
      if (part.startsWith('[') && part.includes('](')) {
        const match = part.match(/\[(.*?)\]\((.*?)\)/);
        if (match) return <a key={idx} href={match[2]} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline flex items-center gap-1"><Paperclip size={10} />{match[1]}</a>;
      }
      if (part.startsWith('@')) {
        return <span key={idx} className="text-blue-600 font-bold bg-blue-50 px-1 rounded cursor-pointer hover:underline">{part}</span>;
      }
      if (part.toLowerCase().startsWith('#commit')) {
        const sha = part.split(/\s+/)[1];
        return (
          <span key={idx} className="text-[#0969da] font-mono text-[11px] bg-[#ddf4ff] px-1.5 py-0.5 rounded border border-[#0969da20] inline-flex items-center gap-1 mx-1">
            <GitCommit size={10} />
            {sha?.substring(0, 7)}
          </span>
        );
      }
      return part;
    });
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    const pos = e.target.selectionStart;
    setNewComment(val);
    setCursorPos(pos);

    const lastAt = val.lastIndexOf('@', pos - 1);
    if (lastAt !== -1 && !val.substring(lastAt, pos).includes(' ')) {
      setMentionQuery(val.substring(lastAt + 1, pos));
      setShowMentionSuggestions(true);
    } else {
      setShowMentionSuggestions(false);
    }
  };

  const selectMention = (user: User) => {
    const lastAt = newComment.lastIndexOf('@', cursorPos - 1);
    const before = newComment.substring(0, lastAt);
    const after = newComment.substring(cursorPos);
    const name = (user.full_name || user.email).replace(/\s/g, '');
    setNewComment(`${before}@${name} ${after}`);
    setShowMentionSuggestions(false);
  };

  const handleCreateBranch = async () => {
    setIsCreatingBranch(true);
    try {
      await api.post(`/git/branches/${taskId}`);
      fetchTask();
      onUpdated();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create branch');
    } finally {
      setIsCreatingBranch(false);
    }
  };

  if (isLoading || !task) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white p-8 rounded-lg shadow-xl"><Loader2 className="animate-spin text-blue-500" size={32} /></div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] shadow-2xl border border-[#d0d7de] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="text-[#636c76] font-mono text-sm shrink-0">#{task.id}</span>
            {/* max-w-xl обрезал название: «Разбор даты в формате ДД.ММ.ГГГГ»
                не помещалось. Заголовок тянется на всю свободную ширину,
                но не наезжает на кнопку закрытия. */}
            <input
              className="text-lg font-bold bg-transparent border-none focus:ring-2 focus:ring-blue-500 rounded px-1 -ml-1 w-full min-w-0 flex-1"
              defaultValue={task.title}
              onBlur={(e) => handleUpdateTask({ title: e.target.value })}
            />
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded-md hover:bg-gray-200 transition">
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex px-6 bg-[#f6f8fa] border-b border-[#d0d7de] gap-1">
          <button onClick={() => setActiveTab('general')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition ${activeTab === 'general' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}>{t('tasks.tabs.general')}</button>
          <button onClick={() => setActiveTab('discussion')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeTab === 'discussion' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}>{t('tasks.tabs.discussion')} <span className="bg-gray-200 px-1.5 py-0.5 rounded-full text-[10px]">{task.comments.length}</span></button>
          <button onClick={() => setActiveTab('development')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeTab === 'development' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}>{t('tasks.tabs.development')} {(task.commits?.length || 0) + (task.branches?.length || 0) > 0 && <span className="bg-[#dafbe1] text-[#1a7f37] px-1.5 py-0.5 rounded-full text-[10px]">{(task.commits?.length || 0) + (task.branches?.length || 0)}</span>}</button>
          <button onClick={() => setActiveTab('history')} className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeTab === 'history' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}>{t('tasks.tabs.history')}</button>
        </div>

        {/* Body: основная колонка и сайдбар прокручиваются независимо */}
        <div className="flex-1 min-h-0 flex bg-white">
          {/* Main Area */}
          <div className={`flex-1 min-w-0 flex flex-col min-h-0 border-r border-[#d0d7de] ${activeTab === 'discussion' ? '' : 'overflow-y-auto p-6 space-y-8 pb-8'}`}>
              {activeTab === 'general' && (
                <>
                  <div className="space-y-2">
                    <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.description')}</label>
                    <textarea 
                      className="w-full bg-[#f6f8fa] border border-[#d0d7de] rounded-md p-3 text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all min-h-[120px] resize-none"
                      placeholder={t('tasks.description_placeholder')}
                      defaultValue={task.description}
                      onBlur={(e) => handleUpdateTask({ description: e.target.value })}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4 border-y border-[#d0d7de] py-4 bg-[#f6f8fa] -mx-6 px-6">
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center gap-1"><Calendar size={10} /> {t('tasks.created_at').split(' ')[0]}</label>
                      <p className="text-xs font-semibold text-[#1f2328]">{new Date(task.created_at).toLocaleString()}</p>
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center gap-1"><Clock size={10} /> {t('tasks.start_date')}</label>
                      <p className="text-xs font-semibold text-[#1f2328]">{task.start_date ? new Date(task.start_date).toLocaleString() : t('tasks.unassigned')}</p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center justify-between">
                      {t('tasks.checklist')}
                      <span className="text-[10px] font-normal lowercase bg-gray-100 px-2 py-0.5 rounded-full">
                        {t('tasks.done_of', { count: task.subtasks.filter((s: SubTask) => s.is_completed).length, total: task.subtasks.length })}
                      </span>
                    </label>
                    <div className="space-y-2">
                      {task.subtasks
                        .sort((a: SubTask, b: SubTask) => a.id - b.id)
                        .map((sub: SubTask) => (
                        <div key={sub.id} className="flex items-center gap-3 group">
                          <button 
                            onClick={() => toggleSubtask(sub)}
                            className={`shrink-0 w-5 h-5 rounded border flex items-center justify-center transition ${sub.is_completed ? 'bg-[#1f883d] border-[#1f883d] text-white' : 'border-[#d0d7de] bg-white text-transparent group-hover:border-[#0969da]'}`}
                          >
                            <Check size={12} strokeWidth={4} />
                          </button>
                          <span className={`text-sm flex-1 ${sub.is_completed ? 'text-[#636c76] line-through' : 'text-[#1f2328]'}`}>{sub.title}</span>
                          <button onClick={() => deleteSubtask(sub.id)} className="opacity-0 group-hover:opacity-100 text-[#636c76] hover:text-red-600 transition p-1"><Trash2 size={14} /></button>
                        </div>
                      ))}
                      <form onSubmit={handleAddSubtask} className="flex items-center gap-2 mt-4">
                        <input className="flex-1 bg-white border border-[#d0d7de] rounded-md px-3 py-1 text-sm outline-none focus:border-blue-500" placeholder={t('tasks.add_subtask')} value={newSubtask} onChange={(e) => setNewSubtask(e.target.value)} />
                        <button type="submit" className="p-1 text-blue-600 hover:bg-blue-50 rounded transition"><Plus size={18} /></button>
                      </form>
                    </div>
                  </div>

                  {/* Dependencies Section */}
                  <div className="space-y-3">
                    <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center justify-between">
                      {t('tasks.dependencies.title')}
                      {!isAddingDependency && (
                        <button onClick={() => setIsAddingDependency(true)} className="text-blue-600 hover:underline flex items-center gap-1 lowercase text-[10px] font-normal"><Plus size={10} /> {t('tasks.dependencies.add')}</button>
                      )}
                    </label>
                    
                    <div className="space-y-2">
                      {task.dependencies && task.dependencies.length > 0 ? (
                        task.dependencies.map((depId: number) => {
                          const depTask = projectTasks.find(t => t.id === depId);
                          return (
                            <div key={depId} className="flex items-center justify-between p-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md group">
                              <div className="flex items-center gap-2 min-w-0">
                                <LinkIcon size={14} className="text-[#636c76]" />
                                <span className="text-[10px] font-mono text-[#636c76]">#{depId}</span>
                                <span className="text-xs font-semibold truncate">{depTask?.title || 'Unknown Task'}</span>
                              </div>
                              <button onClick={() => handleRemoveDependency(depId)} className="opacity-0 group-hover:opacity-100 text-[#636c76] hover:text-red-600 p-1"><Trash2 size={14} /></button>
                            </div>
                          );
                        })
                      ) : (
                        <p className="text-xs text-[#636c76] italic">{t('tasks.dependencies.none')}</p>
                      )}

                      {isAddingDependency && (
                        <div className="relative">
                          <div className="flex gap-2">
                            <input 
                              autoFocus
                              className="flex-1 bg-white border border-[#d0d7de] rounded-md px-3 py-1 text-sm outline-none focus:border-blue-500"
                              placeholder={t('tasks.dependencies.search_placeholder')}
                              value={dependencySearch}
                              onChange={(e) => setDependencySearch(e.target.value)}
                            />
                            <button onClick={() => { setIsAddingDependency(false); setDependencySearch(''); }} className="px-3 py-1 text-xs font-semibold text-[#636c76]">{t('common.cancel')}</button>
                          </div>
                          {dependencySearch && (
                            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-[#d0d7de] rounded-md shadow-xl z-20 max-h-40 overflow-y-auto">
                              {projectTasks
                                .filter(t => t.id !== taskId && !task.dependencies?.includes(t.id))
                                .filter(t => t.title.toLowerCase().includes(dependencySearch.toLowerCase()) || t.id.toString().includes(dependencySearch))
                                .map(t => (
                                  <button key={t.id} onClick={() => handleAddDependency(t.id)} className="w-full text-left px-3 py-2 text-xs hover:bg-[#f6f8fa] flex items-center justify-between">
                                    <span className="truncate pr-2 font-medium">{t.title}</span>
                                    <span className="text-[10px] font-mono text-[#636c76] shrink-0">#{t.id}</span>
                                  </button>
                                ))
                              }
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
              {activeTab === 'discussion' && (
                <div className="flex flex-col flex-1 min-h-0 relative p-6">
                  {/* Лента сообщений прокручивается независимо от окна задачи */}
                  <div ref={chatScrollRef} className="flex-1 min-h-0 space-y-4 overflow-y-auto overflow-x-hidden px-1 pb-2 scroll-smooth" onClick={() => { setActiveCommentMenu(null); setActiveEmojiPicker(null); setMenuPos(null); setEmojiPos(null); }}>
                    {task.comments.length === 0 ? (
                      <div className="text-center py-12 text-[#636c76]">
                        <MessageSquare size={48} className="mx-auto mb-4 opacity-20" />
                        <p className="text-sm">{t('tasks.no_comments')}</p>
                      </div>
                    ) : (
                      task.comments.sort((a: any, b: any) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()).map((comment: TaskComment) => {
                        const isOwn = comment.user_id === currentUser?.id;
                        const canDeleteComment = isOwn || ['project_manager', 'manager'].includes(userRole);
                        
                        return (
                        <div key={comment.id} className={`flex gap-3 ${comment.user_id === currentUser?.id ? 'flex-row-reverse' : ''} group mb-6`}>
                          <div className="w-8 h-8 rounded-full border border-[#d0d7de] overflow-hidden bg-gray-100 flex items-center justify-center shrink-0">
                              {comment.author?.avatar_url ? <img src={comment.author.avatar_url} className="w-full h-full object-cover" /> : <UserIcon size={14} className="text-gray-400" />}
                          </div>
                          <div className="flex-1 max-w-[85%] min-w-0">
                              <div className={`flex items-center gap-2 mb-1 ${comment.user_id === currentUser?.id ? 'justify-end' : ''}`}>
                                <span className="text-xs font-bold text-[#1f2328]">{comment.author?.full_name || comment.author?.email}</span>
                                <span className="text-[10px] text-[#636c76]">{new Date(comment.created_at).toLocaleString()}</span>
                              </div>
                              <div className={`relative border border-[#d0d7de] rounded-lg shadow-sm ${comment.user_id === currentUser?.id ? 'bg-[#ddf4ff] border-[#0969da20] ml-auto' : 'bg-white'} w-fit max-w-full`}>
                                {editingCommentId === comment.id ? (
                                  <form onSubmit={handleEditComment} className="p-2 space-y-2 min-w-[250px]">
                                    <textarea
                                      autoFocus
                                      className="w-full bg-white border border-[#d0d7de] rounded-md p-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 resize-none min-h-[60px]"
                                      value={editCommentContent}
                                      onChange={(e) => setEditCommentContent(e.target.value)}
                                    />
                                    
                                    {editingAttachments.length > 0 && (
                                      <div className="flex flex-wrap gap-1">
                                        {editingAttachments.map(att => (
                                          <div key={att.id} className="flex items-center gap-1 bg-gray-100 rounded px-1.5 py-0.5 text-[10px]">
                                            <span className="truncate max-w-[80px]">{att.filename}</span>
                                            <button type="button" onClick={() => handleRemoveEditingAttachment(att.id)} className="text-gray-400 hover:text-red-500"><X size={10} /></button>
                                          </div>
                                        ))}
                                      </div>
                                    )}

                                    <div className="flex justify-end gap-2">
                                      <button type="button" onClick={() => setEditingCommentId(null)} className="px-2 py-1 text-[10px] font-bold text-[#636c76] hover:bg-gray-100 rounded transition">{t('common.cancel')}</button>
                                      <button type="submit" className="px-2 py-1 text-[10px] font-bold bg-[#1f883d] text-white rounded hover:bg-[#1a7f37] transition">{t('common.save')}</button>
                                    </div>
                                  </form>
                                ) : (
                                  <>
                                    {comment.content && (
                                      <div className="p-3 text-sm text-[#1f2328] leading-relaxed min-w-[120px]">
                                        {renderCommentContent(comment.content)}
                                      </div>
                                    )}
                                    
                                    {/* Comment Actions */}
                                    <div className={`absolute -top-3 ${comment.user_id === currentUser?.id ? 'left-2' : 'right-2'} opacity-0 group-hover:opacity-100 transition-opacity flex items-center bg-white border border-[#d0d7de] rounded-md shadow-sm overflow-hidden z-10`}>
                                      <button onClick={(e) => { e.stopPropagation(); setReplyTo(comment); }} className="p-1.5 hover:bg-gray-100 text-[#636c76] border-r border-[#d0d7de]"><Reply size={14} /></button>
                                      <button ref={(el) => { if (el && activeEmojiPicker === comment.id) emojiAnchorRef.current = el; }} onClick={(e) => { e.stopPropagation(); toggleEmojiPicker(comment.id, e.currentTarget); }} className="p-1.5 hover:bg-gray-100 text-[#636c76] border-r border-[#d0d7de]"><Smile size={14} /></button>
                                      <button ref={(el) => { if (el && activeCommentMenu === comment.id) menuAnchorRef.current = el; }} onClick={(e) => { e.stopPropagation(); toggleCommentMenu(comment.id, e.currentTarget); }} className="p-1.5 hover:bg-gray-100 text-[#636c76]"><MoreHorizontal size={14} /></button>
                                    </div>

                                    {/* Menus */}
{activeEmojiPicker === comment.id && emojiPos && (
                                       <div
                                         style={{ top: emojiPos.top, left: emojiPos.left }}
                                         className="fixed z-[60] bg-white border border-[#d0d7de] rounded-xl shadow-2xl p-2 w-[272px] max-w-[calc(100vw-16px)]"
                                       >
                                         <div className="grid grid-cols-8 gap-0.5">
                                           {EMOJIS.map(e => (
                                             <button key={e} onClick={(ev) => { ev.stopPropagation(); toggleReaction(comment.id, e); setActiveEmojiPicker(null); }} className="text-lg hover:bg-gray-100 p-1 rounded transition-transform hover:scale-125">{e}</button>
                                           ))}
                                         </div>
                                       </div>
                                     )}

                                    {activeCommentMenu === comment.id && menuPos && (
                                      <div
                                        style={{ top: menuPos.top, left: menuPos.left }}
                                        className="fixed z-[60] w-40 bg-white border border-[#d0d7de] rounded-lg shadow-2xl py-1"
                                      >
                                        {isOwn && (
                                          <button onClick={(ev) => { ev.stopPropagation(); startEditing(comment); }} className="w-full text-left px-3 py-1.5 text-xs hover:bg-[#f6f8fa] flex items-center gap-2"><Edit2 size={12} /> {t('tasks.edit_comment')}</button>
                                        )}
                                        {canDeleteComment && (
                                          <button onClick={(ev) => { ev.stopPropagation(); handleDeleteComment(comment.id); }} className="w-full text-left px-3 py-1.5 text-xs hover:bg-[#ffebe9] text-red-600 flex items-center gap-2"><Trash2 size={12} /> {t('tasks.delete_comment')}</button>
                                        )}
                                      </div>
                                    )}

                                    {/* Attachments Display */}
                                    {comment.attachments && comment.attachments.length > 0 && (
                                      <div className={`flex flex-wrap gap-2 p-2 ${comment.content ? 'pt-0' : ''} ${comment.user_id === currentUser?.id ? 'justify-end' : ''}`}>
                                        {comment.attachments.map(att => (
                                          <button 
                                            key={att.id} 
                                            onClick={() => handleDownload(att)}
                                            className="flex items-center gap-2 p-2 border border-[#d0d7de] rounded bg-[#f6f8fa] hover:border-[#0969da] transition-colors max-w-[200px] text-left"
                                          >
                                            {att.mime_type?.startsWith('image/') ? <ImageIcon size={14} className="text-blue-500 shrink-0" /> : <FileText size={14} className="text-gray-500 shrink-0" />}
                                            <span className="text-[10px] font-medium truncate">{att.filename}</span>
                                          </button>
                                        ))}
                                      </div>
                                    )}

                                    {/* Reactions Display */}
                                    {comment.reactions && comment.reactions.length > 0 && (
                                      <div className={`flex flex-wrap gap-1 p-2 pt-0 ${comment.user_id === currentUser?.id ? 'justify-end' : ''}`}>
                                        {Object.entries(
                                          comment.reactions.reduce((acc: any, r) => {
                                            acc[r.emoji] = (acc[r.emoji] || 0) + 1;
                                            return acc;
                                          }, {})
                                        ).map(([emoji, count]: [string, any]) => (
                                          <button
                                            key={emoji}
                                            onClick={(e) => { e.stopPropagation(); toggleReaction(comment.id, emoji); }}
                                            className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] border transition-colors ${
                                              comment.reactions?.some(r => r.emoji === emoji && r.user_id === currentUser?.id)
                                                ? 'bg-[#ddf4ff] border-[#0969da] text-[#0969da]'
                                                : 'bg-white border-[#d0d7de] text-[#636c76] hover:border-[#0969da]'
                                            }`}
                                          >
                                            <span>{emoji}</span>
                                            <span className="font-bold">{count}</span>
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                    <div ref={commentsEndRef} />
                  </div>

                {/* Поле ввода закреплено: не уезжает при прокрутке ленты */}
                <form onSubmit={handleAddComment} className="shrink-0 border-t border-[#d0d7de] pt-4 mt-4">
                  {replyTo && (
                    <div className="mb-2 flex items-center justify-between bg-blue-50 border border-blue-200 rounded-md px-3 py-2 text-xs">
                      <div className="flex items-center gap-2 text-[#0969da] truncate">
                        <Reply size={12} className="shrink-0" />
                        <span className="font-bold shrink-0">{replyTo.author?.full_name || replyTo.author?.email}:</span>
                        <span className="truncate italic opacity-70">{replyTo.content}</span>
                      </div>
                      <button type="button" onClick={() => setReplyTo(null)} className="text-[#636c76] hover:text-red-500 transition-colors p-1"><X size={14} /></button>
                    </div>
                  )}
                  <div className="bg-[#f6f8fa] border border-[#d0d7de] rounded-md p-1 focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                    <textarea 
                      className="w-full bg-transparent p-2 text-sm outline-none resize-none min-h-[80px]"
                      placeholder={t('tasks.leave_comment')}
                      value={newComment}
                      onChange={handleTextareaChange}
                    />
                    
                    {/* Pending Attachments */}
                    {pendingAttachments.length > 0 && (
                      <div className="px-2 pb-2 flex flex-wrap gap-2">
                        {pendingAttachments.map(att => (
                          <div key={att.id} className="flex items-center gap-2 bg-white border border-[#d0d7de] rounded-full px-2 py-1 text-[10px] text-[#1f2328] group">
                            <Paperclip size={10} className="text-[#636c76]" />
                            <span className="max-w-[120px] truncate">{att.filename}</span>
                            <button 
                              type="button" 
                              onClick={() => removePendingAttachment(att.id)}
                              className="text-[#636c76] hover:text-red-600"
                            >
                              <X size={10} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex justify-between items-center p-1">
                      <button type="button" onClick={() => fileInputRef.current?.click()} className="p-1.5 hover:bg-gray-200 rounded text-[#636c76] transition-colors"><Paperclip size={16} /></button>
                      <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
                      <button type="submit" disabled={!newComment.trim() && pendingAttachments.length === 0} className="bg-[#1f883d] text-white px-3 py-1.5 rounded-md text-xs font-bold hover:bg-[#1a7f37] disabled:opacity-50 flex items-center gap-2 transition-all"><Send size={12} /> {t('tasks.comment_button')}</button>
                    </div>
                  </div>
                </form>
                </div>
              )}

{activeTab === 'development' && (
                <div className="space-y-4">
                  {/* Шапка с репозиторием */}
                  <div className="p-4 bg-[#f6f8fa] border border-[#d0d7de] rounded-xl flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`p-2 rounded-lg shrink-0 ${
                          activeRepo ? 'bg-[#dafbe1] text-[#1a7f37]' : 'bg-[#fff8c5] text-[#9a6700]'
                        }`}
                      >
                        <Github size={20} />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-bold text-[#1f2328] truncate">
                          {t('tasks.dev_history_title')}
                        </h4>
                        <p className="text-xs text-[#636c76] truncate">
                          {activeRepo ? activeRepo.url : t('projects.git.not_configured')}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {/* Несколько репозиториев: даём выбрать нужный */}
                      {projectRepos.length > 1 && (
                        <select
                          value={activeRepo?.id || ''}
                          onChange={(e) => setSelectedRepoId(Number(e.target.value))}
                          className="max-w-[170px] bg-white border border-[#d0d7de] rounded-md px-2 py-1.5 text-xs font-semibold outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          {projectRepos.map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.repo_name || r.url}
                            </option>
                          ))}
                        </select>
                      )}

                      {activeRepo && (
                        <>
                          <button
                            onClick={loadDevCard}
                            className="px-2.5 py-1.5 bg-white border border-[#d0d7de] text-[#1f2328] rounded-md text-xs font-bold hover:bg-white transition flex items-center gap-1.5"
                          >
                            <RefreshCw size={13} />
                            {t('tasks.dev.refresh')}
                          </button>
                          {(['project_manager', 'manager'].includes(userRole) ||
                            task?.assignee_id === currentUser?.id) && (
                            <button
                              onClick={handleCreateBranch}
                              disabled={isCreatingBranch}
                              className="px-2.5 py-1.5 bg-[#1f2328] text-white rounded-md text-xs font-bold hover:bg-black transition flex items-center gap-1.5 disabled:opacity-50"
                            >
                              {isCreatingBranch ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : (
                                <GitBranch size={13} />
                              )}
                              {t('tasks.create_branch')}
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  {!activeRepo && (
                    <div className="p-4 bg-[#fff8c5] border border-[#d4a72c4d] rounded-lg flex gap-3">
                      <AlertCircle className="text-[#9a6700] shrink-0" size={18} />
                      <p className="text-xs text-[#735c0f]">{t('tasks.dev_history_desc')}</p>
                    </div>
                  )}

                  {/* Данные карточки */}
                  {devCardLoading ? (
                    <div className="p-10 text-center">
                      <Loader2 className="animate-spin mx-auto text-blue-500" size={22} />
                    </div>
                  ) : activeRepo && devCard ? (
                    <DevCard
                      card={devCard}
                      repoId={activeRepo?.id}
                      canEdit={userRole !== 'observer' && !isObserver ? true : task?.assignee_id === currentUser?.id || ['project_manager', 'manager'].includes(userRole)}
                      onChanged={() => {
                        loadDevCard();
                        fetchTask(true);
                      }}
                    />
                  ) : activeRepo ? (
                    <div className="p-8 text-center">
                      <Loader2 className="animate-spin mx-auto text-blue-500" size={20} />
                    </div>
                  ) : null}
                </div>
              )}

              {activeTab === 'history' && (
                <ActivityTimeline
                  items={taskHistoryItems}
                  showFilters
                  showTaskLink={false}
                  title={t('history.task_history')}
                  emptyText={t('history.empty_task')}
                />
              )}
            </div>

            {/* Sidebar: собственная прокрутка, содержимое никогда не обрезается */}
            <div className="w-64 shrink-0 bg-[#f6f8fa] overflow-y-auto overscroll-contain">
              <div className="p-6 space-y-6 min-h-full">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.status')}</label>
                <select className="w-full bg-white border border-[#d0d7de] rounded-md px-2 py-1.5 text-xs font-semibold shadow-sm outline-none focus:ring-1 focus:ring-blue-500" value={task.column_id} onChange={(e) => handleUpdateTask({ column_id: Number(e.target.value) })}>
                  {columns.map(col => <option key={col.id} value={col.id}>{col.name}</option>)}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.type')}</label>
                <div className="flex flex-col gap-1">
                  <button onClick={() => handleUpdateTask({ task_type: null })} className={`text-left px-3 py-1.5 rounded-md text-xs font-semibold border flex items-center justify-between ${!task.task_type ? 'bg-white border-[#d0d7de] shadow-sm text-[#1f2328]' : 'border-transparent text-[#636c76] hover:bg-white/50'}`}>
                    <span className="text-[#636c76]">{t('tasks.type_none')}</span>
                    {!task.task_type && <Check size={12} className="text-blue-500" />}
                  </button>
                  {TASK_TYPES.map(k => (
                    <button key={k} onClick={() => handleUpdateTask({ task_type: k })} className={`text-left px-3 py-1.5 rounded-md text-xs font-semibold border flex items-center justify-between ${task.task_type === k ? 'bg-white border-[#d0d7de] shadow-sm text-[#1f2328]' : 'border-transparent text-[#636c76] hover:bg-white/50'}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${TASK_TYPE_STYLE[k].dot}`} />
                        <span title={t(`tasks.type_hint.${k}`)}>{t(`task_type.${k}`)}</span>
                      </div>
                      {task.task_type === k && <Check size={12} className="text-blue-500" />}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.priority')}</label>
                <div className="flex flex-col gap-1">
                  {[1, 2, 3].map(p => (
                    <button key={p} onClick={() => handleUpdateTask({ priority: p })} className={`text-left px-3 py-1.5 rounded-md text-xs font-semibold border flex items-center justify-between ${task.priority === p ? 'bg-white border-[#d0d7de] shadow-sm text-[#1f2328]' : 'border-transparent text-[#636c76] hover:bg-white/50'}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${p === 3 ? 'bg-red-500' : p === 2 ? 'bg-amber-500' : 'bg-blue-400'}`} />
                        {p === 3 ? t('tasks.high') : p === 2 ? t('tasks.medium') : t('tasks.low')}
                      </div>
                      {task.priority === p && <Check size={12} className="text-blue-500" />}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2 pt-2 border-t border-[#d0d7de]">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center gap-1"><Calendar size={10} /> {t('tasks.start_date')}</label>
                <input type="datetime-local" className="w-full bg-white border border-[#d0d7de] rounded-md px-2 py-1.5 text-xs font-semibold shadow-sm outline-none focus:ring-1 focus:ring-blue-500" value={task.start_date ? new Date(task.start_date).toISOString().slice(0, 16) : ''} onChange={(e) => handleUpdateTask({ start_date: e.target.value || null })} />
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider flex items-center gap-1"><Clock size={10} /> {t('tasks.due_date')}</label>
                <input type="datetime-local" className="w-full bg-white border border-[#d0d7de] rounded-md px-2 py-1.5 text-xs font-semibold shadow-sm outline-none focus:ring-1 focus:ring-blue-500" value={task.due_date ? new Date(task.due_date).toISOString().slice(0, 16) : ''} onChange={(e) => handleUpdateTask({ due_date: e.target.value || null })} />
              </div>

              <div className="space-y-2 pt-2 border-t border-[#d0d7de]">
                <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.assignee')}</label>
                <select className="w-full bg-white border border-[#d0d7de] rounded-md px-2 py-1.5 text-xs font-semibold shadow-sm outline-none focus:ring-1 focus:ring-blue-500" value={task.assignee_id || ''} onChange={(e) => handleUpdateTask({ assignee_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">{t('tasks.unassigned')}</option>
                  {members.map(m => <option key={m.id} value={m.id}>{m.full_name || m.email}</option>)}
                </select>
              </div>

              <button onClick={() => { if (window.confirm(t('tasks.delete_confirm'))) { api.delete(`/tasks/${task.id}`).then(() => { onUpdated(); onClose(); }); } }} className="w-full mt-8 flex items-center gap-2 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50 rounded-md transition border border-transparent hover:border-red-200">
                <Trash2 size={14} /> {t('tasks.delete_task')}
              </button>
              </div>
            </div>
          </div>
        </div>
      </div>
  );
};

export default TaskDetailModal;
