/**
 * LogViewer component: Fetches and displays logs from the backend.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { getLogs } from '../api'; // Assuming api.js is in src/

const LogViewer = () => {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [levelFilter, setLevelFilter] = useState(''); // e.g., INFO, ERROR
  const [limit, setLimit] = useState(100);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getLogs(levelFilter || null, limit); // Pass null if levelFilter is empty
      setLogs(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not fetch logs.');
      console.error("LogViewer fetchLogs error:", err);
      setLogs([]);
    } finally {
      setIsLoading(false);
    }
  }, [levelFilter, limit]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleRefresh = () => {
    fetchLogs();
  };

  return (
    <div className="log-viewer-container">
      <h2>Agent Logs (from Memory)</h2>
      <div className="log-filters">
        <label htmlFor="levelFilter">Filter by Level: </label>
        <select
          id="levelFilter"
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
        >
          <option value="">ALL</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="DEBUG">DEBUG</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <label htmlFor="limit" style={{ marginLeft: '10px' }}>Limit: </label>
        <input
          type="number"
          id="limit"
          value={limit}
          onChange={(e) => setLimit(parseInt(e.target.value, 10) || 100)}
          min="1"
          max="500"
        />
        <button onClick={handleRefresh} disabled={isLoading} style={{ marginLeft: '10px' }}>
          {isLoading ? 'Refreshing...' : 'Refresh Logs'}
        </button>
      </div>

      {isLoading && <p>Loading logs...</p>}
      {error && <p className="error-message">Error fetching logs: {error}</p>}

      {!isLoading && !error && logs.length === 0 && <p>No logs found matching criteria.</p>}

      {!isLoading && !error && logs.length > 0 && (
        <table className="log-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Timestamp</th>
              <th>Level</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className={`log-level-${log.level?.toLowerCase()}`}>
                <td>{log.id}</td>
                <td>{new Date(log.timestamp).toLocaleString()}</td>
                <td>{log.level}</td>
                <td><pre>{log.message}</pre></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default LogViewer;
