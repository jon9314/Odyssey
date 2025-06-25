/**
 * LLMTestInterface component: Allows sending prompts to the LLM and viewing responses.
 */
import React, { useState } from 'react';
import { askLLM } from '../api'; // Assuming api.js is in src/

const LLMTestInterface = () => {
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('auto'); // 'auto' or specific model tag
  const [isSafe, setIsSafe] = useState(true); // For the 'safe' routing hint
  const [systemPrompt, setSystemPrompt] = useState('');
  const [options, setOptions] = useState(''); // JSON string for Ollama options

  const [response, setResponse] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError('Prompt cannot be empty.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setResponse(null);

    let parsedOptions = null;
    if (options.trim()) {
      try {
        parsedOptions = JSON.parse(options);
      } catch (parseError) {
        setError('Invalid JSON in options field.');
        setIsLoading(false);
        return;
      }
    }

    try {
      const apiResponse = await askLLM(
        prompt,
        model.trim() || 'auto',
        isSafe,
        systemPrompt.trim() || null,
        parsedOptions
      );

      if (apiResponse.data.error) {
        setError(`LLM Error: ${apiResponse.data.error}`);
        setResponse({ ...apiResponse.data, response: null }); // Keep other info like model_used
      } else {
        setResponse(apiResponse.data);
      }

    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to get LLM response.';
      setError(errorMsg);
      console.error("LLMTestInterface error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="llm-test-interface">
      <h2>Test LLM Interaction</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="prompt">Prompt:</label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Enter your prompt for the LLM"
            rows="5"
            disabled={isLoading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="model">Model:</label>
          <input
            type="text"
            id="model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g., phi3, llama3:latest, or 'auto'"
            disabled={isLoading}
          />
          <small>Use 'auto' or specify a model tag available on your Ollama instance(s).</small>
        </div>

        <div className="form-group">
          <label htmlFor="systemPrompt">System Prompt (Optional):</label>
          <textarea
            id="systemPrompt"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="e.g., You are a helpful assistant."
            rows="2"
            disabled={isLoading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="options">Ollama Options (JSON, Optional):</label>
          <input
            type="text"
            id="options"
            value={options}
            onChange={(e) => setOptions(e.target.value)}
            placeholder='e.g., {"temperature": 0.7, "top_p": 0.9}'
            disabled={isLoading}
          />
           <small>See Ollama API for available generation options.</small>
        </div>

        <div className="form-group-checkbox">
          <input
            type="checkbox"
            id="isSafe"
            checked={isSafe}
            onChange={(e) => setIsSafe(e.target.checked)}
            disabled={isLoading}
          />
          <label htmlFor="isSafe" title="Prefers local/CPU model if True, remote/GPU if False (if both configured and model available).">
            Safe Mode (Prefer Local/CPU)
          </label>
        </div>

        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Asking LLM...' : 'Send Prompt'}
        </button>
      </form>

      {error && <p className="error-message">{error}</p>}

      {response && (
        <div className="llm-response-area">
          <h3>LLM Response:</h3>
          {response.model_used && <p><strong>Model Used:</strong> {response.model_used}</p>}
          {response.instance_used && <p><strong>Instance Used:</strong> {response.instance_used}</p>}
          {response.response && <pre className="llm-output">{response.response}</pre>}
          {response.error && <p className="error-message"><strong>Error from LLM Client:</strong> {response.error}</p>}
        </div>
      )}
    </div>
  );
};

export default LLMTestInterface;
