import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import ActivityTimeline from './activity/ActivityTimeline';
import { ActivityItem } from './activity/activityMeta';

interface ProjectActivityViewProps {
  projectId: number;
  onTaskClick?: (taskId: number) => void;
}

const ProjectActivityView: React.FC<ProjectActivityViewProps> = ({ projectId, onTaskClick }) => {
  const { t } = useTranslation();

  const { data: activities, isLoading, refetch, isFetching } = useQuery<ActivityItem[]>({
    queryKey: ['project-activity', projectId],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/activity`);
      return data;
    },
  });

  return (
    <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full py-4 px-2">
      <ActivityTimeline
        items={activities ?? []}
        isLoading={isLoading}
        isFetching={isFetching}
        onRefresh={() => refetch()}
        onTaskClick={onTaskClick}
        showTaskLink
        title={t('history.project_history')}
        emptyText={t('history.empty_project')}
      />
    </div>
  );
};

export default ProjectActivityView;
