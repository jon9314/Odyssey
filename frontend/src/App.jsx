import React, { useState } from 'react';
import './App.css'; // Basic styling
import TaskManager from './components/TaskManager'; // Combined TaskList and AddTaskForm
import LogViewer from './components/LogViewer';
import LLMTestInterface from './components/LLMTestInterface';

function App() {
  const [activeView, setActiveView] = useState('tasks'); // 'tasks', 'logs', 'llm'

  let currentView;
  if (activeView === 'tasks') {
    currentView = <TaskManager />;
  } else if (activeView === 'logs') {
    currentView = <LogViewer />;
  } else if (activeView === 'llm') {
    currentView = <LLMTestInterface />;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>Odyssey Agent UI</h1>
        <nav>
          <button onClick={() => setActiveView('tasks')} className={activeView === 'tasks' ? 'active' : ''}>Tasks</button>
          <button onClick={() => setActiveView('logs')} className={activeView === 'logs' ? 'active' : ''}>Logs</button>
          <button onClick={() => setActiveView('llm')} className={activeView === 'llm' ? 'active' : ''}>LLM Test</button>
        </nav>
      </header>
      <main>
        {currentView}
      </main>
      <footer>
        <p>Odyssey Agent Interface</p>
      </footer>
    </div>
  );
}

export default App;
