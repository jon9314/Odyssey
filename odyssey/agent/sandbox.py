# For running/test new code
import subprocess

class Sandbox:
    def __init__(self):
        print("Sandbox initialized.")

    def run_code(self, code_string, language="python"):
        """
        Runs a string of code in a sandboxed environment.
        For simplicity, this uses subprocess. More robust sandboxing is needed for production.
        """
        print(f"Running {language} code in sandbox...")
        try:
            if language == "python":
                # WARNING: Running arbitrary code like this is insecure.
                # A proper sandbox (e.g., Docker container, gVisor) is crucial.
                result = subprocess.run(['python', '-c', code_string], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return result.stdout
                else:
                    return f"Error: {result.stderr}"
            else:
                return f"Unsupported language: {language}"
        except subprocess.TimeoutExpired:
            return "Error: Code execution timed out."
        except Exception as e:
            return f"Error: {str(e)}"

    def test_code(self, test_script_path):
        """
        Runs a test script in a sandboxed environment.
        """
        print(f"Testing code using script: {test_script_path}")
        try:
            # Similar security concerns as run_code
            result = subprocess.run(['python', test_script_path], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return f"Tests passed:\n{result.stdout}"
            else:
                return f"Tests failed:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error: Test execution timed out."
        except Exception as e:
            return f"Error: {str(e)}"
