/**
 * BackgroundTaskContext
 *
 * Global context for tracking background Celery tasks across the application.
 * Provides a centralized way to show task status in the navbar regardless
 * of which page the user is viewing.
 */

import type { ReactNode } from 'react';
import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import apiClient from '../api/client';

export type TaskType = 'sync' | 'match' | 'enrich' | 'import' | 'gmail';

export interface BackgroundTask {
  id: string;
  type: TaskType;
  label: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress?: {
    current: number;
    total: number;
  };
  startedAt: Date;
  completedAt?: Date;
  error?: string;
}

interface BackgroundTaskContextType {
  tasks: BackgroundTask[];
  activeTasks: BackgroundTask[];
  registerTask: (id: string, type: TaskType, label: string) => void;
  updateTask: (id: string, updates: Partial<BackgroundTask>) => void;
  removeTask: (id: string) => void;
  clearCompletedTasks: () => void;
  hasActiveTasks: boolean;
}

const BackgroundTaskContext = createContext<BackgroundTaskContextType | undefined>(undefined);

// How long to keep completed tasks visible (ms)
const COMPLETED_TASK_RETENTION = 5000;

// Poll interval for checking task status
const POLL_INTERVAL = 2000;

export function BackgroundTaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const pollIntervals = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Clean up polling intervals on unmount
  useEffect(() => {
    return () => {
      pollIntervals.current.forEach((interval) => clearInterval(interval));
    };
  }, []);

  const registerTask = useCallback((id: string, type: TaskType, label: string) => {
    const newTask: BackgroundTask = {
      id,
      type,
      label,
      status: 'queued',
      startedAt: new Date(),
    };

    setTasks((prev) => {
      // Don't add duplicate tasks
      if (prev.some((t) => t.id === id)) {
        return prev;
      }
      return [...prev, newTask];
    });

    // Start polling for this task's status
    const pollStatus = async () => {
      try {
        // Determine the correct endpoint based on task type
        let endpoint: string;
        switch (type) {
          case 'sync':
            endpoint = `/truelayer/jobs/${id}`;
            break;
          case 'gmail':
            endpoint = `/gmail/jobs/${id}`;
            break;
          case 'match':
          case 'enrich':
          case 'import':
            endpoint = `/jobs/${id}`;
            break;
          default:
            endpoint = `/jobs/${id}`;
        }

        const response = await apiClient.get(endpoint);
        const data = response.data;

        // Map backend status to our status
        let status: BackgroundTask['status'] = 'running';
        if (data.status === 'completed') status = 'completed';
        else if (data.status === 'failed') status = 'failed';
        else if (data.status === 'queued' || data.status === 'pending') status = 'queued';

        setTasks((prev) =>
          prev.map((t) =>
            t.id === id
              ? {
                  ...t,
                  status,
                  progress: data.total_accounts
                    ? { current: data.accounts_processed || 0, total: data.total_accounts }
                    : data.transactions_synced
                    ? { current: data.transactions_synced, total: data.transactions_synced }
                    : undefined,
                  completedAt: status === 'completed' || status === 'failed' ? new Date() : undefined,
                  error: status === 'failed' ? data.error : undefined,
                }
              : t
          )
        );

        // Stop polling if task is done
        if (status === 'completed' || status === 'failed') {
          const interval = pollIntervals.current.get(id);
          if (interval) {
            clearInterval(interval);
            pollIntervals.current.delete(id);
          }

          // Auto-remove completed tasks after retention period
          if (status === 'completed') {
            setTimeout(() => {
              setTasks((prev) => prev.filter((t) => t.id !== id));
            }, COMPLETED_TASK_RETENTION);
          }
        }
      } catch (err) {
        console.error(`Failed to poll task ${id}:`, err);
        // On error, mark task as failed and stop polling
        setTasks((prev) =>
          prev.map((t) =>
            t.id === id
              ? { ...t, status: 'failed', error: 'Failed to check status', completedAt: new Date() }
              : t
          )
        );
        const interval = pollIntervals.current.get(id);
        if (interval) {
          clearInterval(interval);
          pollIntervals.current.delete(id);
        }
      }
    };

    // Initial poll
    void pollStatus();

    // Set up interval polling
    const interval = setInterval(pollStatus, POLL_INTERVAL);
    pollIntervals.current.set(id, interval);
  }, []);

  const updateTask = useCallback((id: string, updates: Partial<BackgroundTask>) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, ...updates } : t))
    );
  }, []);

  const removeTask = useCallback((id: string) => {
    const interval = pollIntervals.current.get(id);
    if (interval) {
      clearInterval(interval);
      pollIntervals.current.delete(id);
    }
    setTasks((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearCompletedTasks = useCallback(() => {
    setTasks((prev) => prev.filter((t) => t.status !== 'completed' && t.status !== 'failed'));
  }, []);

  const activeTasks = tasks.filter((t) => t.status === 'queued' || t.status === 'running');
  const hasActiveTasks = activeTasks.length > 0;

  return (
    <BackgroundTaskContext.Provider
      value={{
        tasks,
        activeTasks,
        registerTask,
        updateTask,
        removeTask,
        clearCompletedTasks,
        hasActiveTasks,
      }}
    >
      {children}
    </BackgroundTaskContext.Provider>
  );
}

export function useBackgroundTasks() {
  const context = useContext(BackgroundTaskContext);
  if (!context) {
    throw new Error('useBackgroundTasks must be used within a BackgroundTaskProvider');
  }
  return context;
}
