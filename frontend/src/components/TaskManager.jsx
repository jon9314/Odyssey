/**
 * TaskManager component: Handles displaying a list of tasks
 * and a form to add new tasks.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { getTasks, addTask, updateTask } from '../api'; // Assuming api.js is in src/

const AddTaskForm = ({ onTaskAdded }) => {
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!description.trim()) {
      setError('Task description cannot be empty.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      await addTask(description);
      setDescription(''); // Clear input
      if (onTaskAdded) {
        onTaskAdded(); // Notify parent to refresh task list
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add task. Please try again.');
      console.error("AddTaskForm error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="add-task-form">
      <h3>Add New Task</h3>
      <div>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Enter task description"
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Adding...' : 'Add Task'}
        </button>
      </div>
      {error && <p className="error-message">{error}</p>}
    </form>
  );
};

const TaskList = ({ tasks, onTaskStatusChange, loading, error }) => {
  if (loading) return <p>Loading tasks...</p>;
  if (error) return <p className="error-message">Error fetching tasks: {error}</p>;
  if (!tasks || tasks.length === 0) return <p>No tasks found.</p>;

  // Example: In a real app, status options would be more dynamic or defined
  const availableStatuses = ["pending", "in_progress", "completed", "failed"];

  return (
    <div className="task-list">
      <h3>Task List</h3>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Description</th>
            <th>Status</th>
            <th>Timestamp</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id}>
              <td>{task.id}</td>
              <td>{task.description}</td>
              <td>{task.status}</td>
              <td>{new Date(task.timestamp).toLocaleString()}</td>
              <td>
                <select
                  value={task.status}
                  onChange={(e) => onTaskStatusChange(task.id, e.target.value)}
                  className="task-status-select"
                >
                  {availableStatuses.map(status => (
                    <option key={status} value={status}>{status.replace('_', ' ').toUpperCase()}</option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TaskManager = () => {
  const [tasks, setTasks] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTasks = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getTasks();
      setTasks(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not fetch tasks.');
      console.error("TaskManager fetchTasks error:", err);
      setTasks([]); // Clear tasks on error
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const handleTaskAdded = () => {
    fetchTasks(); // Refresh task list after a new task is added
  };

  const handleTaskStatusChange = async (taskId, newStatus) => {
    try {
      await updateTask(taskId, newStatus);
      // Optimistically update UI or refetch
      setTasks(prevTasks =>
        prevTasks.map(task =>
          task.id === taskId ? { ...task, status: newStatus } : task
        )
      );
      // Or simply call fetchTasks() for a full refresh:
      // fetchTasks();
    } catch (err) {
      console.error(`Error updating task ${taskId} to status ${newStatus}:`, err);
      // Optionally show an error message to the user
      setError(`Failed to update task ${taskId}. ${err.response?.data?.detail || ''}`);
    }
  };

  return (
    <div className="task-manager-container">
      <AddTaskForm onTaskAdded={handleTaskAdded} />
      <TaskList tasks={tasks} onTaskStatusChange={handleTaskStatusChange} loading={isLoading} error={error} />
    </div>
  );
};

export default TaskManager;
