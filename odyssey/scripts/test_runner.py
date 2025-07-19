# Runs code validation in sandbox
import os
import sys
import subprocess
import importlib

# Add project root to sys.path to allow importing odyssey modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

# Attempt to import the sandbox; handle if it's not found or has issues
try:
    from odyssey.agent.sandbox import Sandbox
except ImportError:
    print("Error: Could not import Sandbox from odyssey.agent.sandbox.")
    print("Ensure the agent module and Sandbox class are correctly defined.")
    sys.exit(1)

class TestRunner:
    def __init__(self):
        self.sandbox = Sandbox()
        self.test_dir = os.path.join(PROJECT_ROOT, "tests")
        print(f"TestRunner initialized. Looking for tests in: {self.test_dir}")

    def discover_and_run_tests(self):
        """
        Discovers and runs tests using pytest if available,
        otherwise falls back to a simple unittest discovery.
        """
        if not os.path.exists(self.test_dir):
            print(f"Test directory not found: {self.test_dir}")
            return

        # Prefer pytest if installed
        try:
            importlib.import_module("pytest")
            print("Pytest found. Running tests with pytest...")
            # Note: This runs pytest in a subprocess.
            # For more integrated sandbox testing, pytest plugins or custom collectors might be better.
            # This basic runner executes pytest against the tests directory.
            # The sandbox's test_code method might be used if you want to run each test file
            # in a more isolated manner, but pytest handles its own environment well.
            process = subprocess.run(
                [sys.executable, "-m", "pytest", self.test_dir],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT
            )
            print("--- Pytest Output ---")
            print(process.stdout)
            if process.stderr:
                print("--- Pytest Errors ---")
                print(process.stderr)
            print("--- End Pytest ---")
            if process.returncode == 0:
                print("All pytest tests passed.")
            else:
                print(f"Pytest run failed with exit code {process.returncode}.")
            return process.returncode == 0
        except ImportError:
            print("Pytest not found. Consider installing it (`pip install pytest`).")
            print("Falling back to basic unittest discovery (not implemented in this example).")
            # TODO: Implement basic unittest discovery if pytest is not available
            # For example, using unittest.TestLoader().discover()
            # For each test file found, you could use self.sandbox.test_code(filepath)
            # but that would require each test file to be executable and self-contained
            # in terms of outputting success/failure in a parseable way.
            print("Basic unittest discovery is not yet implemented.")
            return False
        except Exception as e:
            print(f"An error occurred while trying to run tests with pytest: {e}")
            return False

    def run_specific_test_file_in_sandbox(self, file_path):
        """
        Runs a specific test file using the sandbox's test_code method.
        This is a more granular approach.
        """
        if not os.path.isabs(file_path):
            full_path = os.path.join(self.test_dir, file_path)
        else:
            full_path = file_path

        if not os.path.exists(full_path):
            print(f"Test file not found: {full_path}")
            return False

        print(f"\nRunning specific test file in sandbox: {full_path}")
        result = self.sandbox.test_code(full_path) # Assumes test_code can take a path
        print(result)
        # Crude check for success, adapt based on sandbox.test_code output format
        if "Tests passed" in result and "Tests failed" not in result:
            print(f"Sandbox test successful for {file_path}")
            return True
        else:
            print(f"Sandbox test failed or had errors for {file_path}")
            return False

if __name__ == "__main__":
    runner = TestRunner()
    print("Starting test run...")

    # Option 1: Discover and run all tests (tries pytest first)
    success = runner.discover_and_run_tests()

    # Option 2: Example of running a specific test file through the sandbox
    # This assumes you have a 'test_agent.py' that can be run directly and prints parseable output.
    # success_specific = runner.run_specific_test_file_in_sandbox("test_agent.py")
    # print(f"Specific test file run success: {success_specific}")

    if success:
        print("\nAll tests completed successfully.")
        sys.exit(0)
    else:
        print("\nSome tests failed.")
        sys.exit(1)
