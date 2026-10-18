import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import { Board, Task } from '../types';

export const useBoard = (projectId: number | null) => {
  return useQuery<Board>({
    queryKey: ['board', projectId],
    queryFn: async () => {
      const { data } = await api.get(`/boards/${projectId}`);
      return data;
    },
    enabled: !!projectId, // Запрос пойдет только если есть ID
  });
};

export const useTasks = (projectId: number | null) => {
  return useQuery<Task[]>({
    queryKey: ['tasks', projectId],
    queryFn: async () => {
      const { data } = await api.get(`/tasks/`, { params: { project_id: projectId } });
      return data;
    },
    enabled: !!projectId, // Запрос пойдет только если есть ID
  });
};
