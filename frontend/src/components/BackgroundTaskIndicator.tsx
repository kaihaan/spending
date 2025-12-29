/**
 * BackgroundTaskIndicator
 *
 * Navbar component that shows the status of background Celery tasks.
 * Displays a subtle indicator when tasks are running, with a dropdown
 * showing task details on click.
 */

import { useState, useRef, useEffect } from 'react';
import { useBackgroundTasks } from '../contexts/BackgroundTaskContext';

export default function BackgroundTaskIndicator() {
  const { tasks, activeTasks, hasActiveTasks, clearCompletedTasks } = useBackgroundTasks();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Don't render if no tasks (ever)
  if (tasks.length === 0) {
    return null;
  }

  const completedTasks = tasks.filter((t) => t.status === 'completed');
  const failedTasks = tasks.filter((t) => t.status === 'failed');

  return (
    <div className="dropdown dropdown-end" ref={dropdownRef}>
      <button
        type="button"
        className={`btn btn-ghost btn-sm gap-1 ${hasActiveTasks ? 'animate-pulse' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Background tasks"
      >
        {/* Sync icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`h-5 w-5 ${hasActiveTasks ? 'animate-spin' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>

        {/* Badge showing count */}
        {hasActiveTasks && (
          <span className="badge badge-primary badge-xs">{activeTasks.length}</span>
        )}
        {!hasActiveTasks && failedTasks.length > 0 && (
          <span className="badge badge-error badge-xs">{failedTasks.length}</span>
        )}
        {!hasActiveTasks && failedTasks.length === 0 && completedTasks.length > 0 && (
          <span className="badge badge-success badge-xs">{completedTasks.length}</span>
        )}
      </button>

      {isOpen && (
        <div className="dropdown-content mt-2 z-50 p-3 shadow-lg bg-base-200 rounded-box w-72">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-semibold text-sm">Background Tasks</h3>
            {(completedTasks.length > 0 || failedTasks.length > 0) && (
              <button
                type="button"
                className="btn btn-ghost btn-xs"
                onClick={() => {
                  clearCompletedTasks();
                  if (activeTasks.length === 0) setIsOpen(false);
                }}
              >
                Clear
              </button>
            )}
          </div>

          {tasks.length === 0 ? (
            <p className="text-sm text-base-content/60">No tasks</p>
          ) : (
            <ul className="space-y-2">
              {tasks.map((task) => (
                <li
                  key={task.id}
                  className="flex items-center gap-2 text-sm p-2 bg-base-100 rounded-lg"
                >
                  {/* Status indicator */}
                  {task.status === 'queued' && (
                    <span className="loading loading-dots loading-xs text-warning" />
                  )}
                  {task.status === 'running' && (
                    <span className="loading loading-spinner loading-xs text-primary" />
                  )}
                  {task.status === 'completed' && (
                    <svg
                      className="h-4 w-4 text-success"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                  {task.status === 'failed' && (
                    <svg
                      className="h-4 w-4 text-error"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  )}

                  <div className="flex-1 min-w-0">
                    <p className="truncate font-medium">{task.label}</p>
                    {task.progress && (
                      <div className="flex items-center gap-2 mt-1">
                        <progress
                          className="progress progress-primary h-1 flex-1"
                          value={task.progress.current}
                          max={task.progress.total}
                        />
                        <span className="text-xs text-base-content/60">
                          {task.progress.current}/{task.progress.total}
                        </span>
                      </div>
                    )}
                    {task.error && (
                      <p className="text-xs text-error truncate">{task.error}</p>
                    )}
                  </div>

                  {/* Time indicator */}
                  <span className="text-xs text-base-content/50">
                    {formatElapsedTime(task.startedAt, task.completedAt)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function formatElapsedTime(start: Date, end?: Date): string {
  const endTime = end || new Date();
  const elapsed = Math.floor((endTime.getTime() - start.getTime()) / 1000);

  if (elapsed < 60) {
    return `${elapsed}s`;
  }
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  return `${minutes}m ${seconds}s`;
}
