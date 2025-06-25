# For running/test new code
import subprocess

class Sandbox:
    def __init__(self):
import os
import logging
import shutil # For checking Dockerfile path more easily

logger = logging.getLogger(__name__)

class Sandbox:
    def __init__(self):
import os
import logging
import shutil # For checking Dockerfile path more easily
import time # For health check delays
import requests # For actual health checks

logger = logging.getLogger(__name__)

# Default settings for validation, can be overridden or made configurable
DEFAULT_HEALTH_CHECK_ENDPOINT = "/health"
DEFAULT_APP_PORT_IN_CONTAINER = 8000 # Assuming the app inside Docker exposes on this
DEFAULT_HOST_PORT_FOR_HEALTH_CHECK = 18765 # Arbitrary host port for temporary mapping
DEFAULT_TEST_COMMAND = ["python", "-m", "unittest", "discover", "-s", "./tests"] # Example

class Sandbox:
    def __init__(self,
                 health_check_endpoint: str = DEFAULT_HEALTH_CHECK_ENDPOINT,
                 app_port_in_container: int = DEFAULT_APP_PORT_IN_CONTAINER,
                 host_port_for_health_check: int = DEFAULT_HOST_PORT_FOR_HEALTH_CHECK,
                 test_command: list[str] = None
                 ):
        logger.info("Sandbox initialized.")
        self.health_check_endpoint = health_check_endpoint
        self.app_port_in_container = app_port_in_container
        self.host_port_for_health_check = host_port_for_health_check
        self.test_command = test_command if test_command is not None else DEFAULT_TEST_COMMAND.copy()


    def _run_docker_command(self, command: list, cwd: str = None, timeout: int = 300) -> tuple[bool, str, str]:
        """
        Helper to run Docker commands with a timeout.
        Returns (success, stdout, stderr).
        """
        try:
            logger.debug(f"Running Docker command: {' '.join(command)} in {cwd or 'current dir'} with timeout {timeout}s")
            process = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout
            )
            if process.returncode == 0:
                logger.debug(f"Docker command successful. STDOUT: {process.stdout[:500]}") # Log more stdout
                return True, process.stdout.strip(), process.stderr.strip()
            else:
                logger.error(f"Docker command failed. RC: {process.returncode}. STDERR: {process.stderr}. STDOUT: {process.stdout}")
                return False, process.stdout.strip(), process.stderr.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"Docker command {' '.join(command)} timed out after {timeout}s.")
            return False, "", f"Command timed out after {timeout}s."
        except FileNotFoundError:
            logger.error("Docker command not found. Is Docker installed and in PATH?")
            return False, "", "Docker command not found."
        except Exception as e:
            logger.error(f"Exception during Docker command {' '.join(command)}: {e}", exc_info=True)
            return False, "", str(e)

    def run_validation_in_docker(self, repo_clone_path: str, proposal_id: str) -> tuple[bool, str]:
        """
        Runs validation (build, service startup, health check, tests) using Docker.
        :param repo_clone_path: Absolute path to the cloned repository with the proposal branch checked out.
        :param proposal_id: A unique identifier for the proposal (used for image/container naming).
        :return: Tuple (success: bool, output_log: str)
        """
        output_log_lines = []
        image_name = f"odyssey-proposal-{proposal_id.replace('_', '-')}-{os.urandom(4).hex()}"
        container_name = f"{image_name}-container"
        overall_success = False # Assume failure until all steps pass
        build_success_flag = False # To track if image should be cleaned up

        def log_and_append(message: str, level: str = "info"):
            if level == "info": logger.info(f"[{proposal_id}] {message}")
            elif level == "warning": logger.warning(f"[{proposal_id}] {message}")
            elif level == "error": logger.error(f"[{proposal_id}] {message}")
            output_log_lines.append(message)

        log_and_append(f"Starting Docker validation for proposal: {proposal_id}", "info")
        dockerfile_path = os.path.join(repo_clone_path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            msg = "Dockerfile not found at the root of the repository clone. Cannot proceed."
            log_and_append(f"ERROR: {msg}", "warning")
            return False, "\n".join(output_log_lines)

        try:
            # 1. Build Docker Image
            log_and_append(f"STEP 1: Building Docker image: {image_name} from path: {repo_clone_path}", "info")
            build_success_flag, stdout, stderr = self._run_docker_command(
                ["docker", "build", "--pull", "-t", image_name, "."], cwd=repo_clone_path, timeout=600 # 10 min build timeout
            )
            log_and_append(f"Docker build STDOUT:\n{stdout}\nDocker build STDERR:\n{stderr}", "debug")
            if not build_success_flag:
                log_and_append(f"ERROR: Docker image build failed for {image_name}.", "error")
                return False, "\n".join(output_log_lines)
            log_and_append(f"Docker image {image_name} built successfully.", "info")

            # 2. Run Docker Container
            log_and_append(f"STEP 2: Running Docker container: {container_name} from image: {image_name}", "info")
            # Map the app port to a host port for health check
            docker_run_cmd = [
                "docker", "run", "--name", container_name, "-d",
                "-p", f"{self.host_port_for_health_check}:{self.app_port_in_container}",
                image_name
            ]
            run_success, stdout, stderr = self._run_docker_command(docker_run_cmd)
            log_and_append(f"Docker run STDOUT:\n{stdout}\nDocker run STDERR:\n{stderr}", "debug")
            if not run_success:
                log_and_append(f"ERROR: Failed to start Docker container {container_name}.", "error")
                return False, "\n".join(output_log_lines)
            log_and_append(f"Docker container {container_name} started.", "info")

            # 3. Health Check
            log_and_append(f"STEP 3: Performing health check on container {container_name}...", "info")
            health_check_url = f"http://localhost:{self.host_port_for_health_check}{self.health_check_endpoint}"
            health_check_passed = False
            max_retries = 12 # e.g., 12 retries * 5 seconds = 60 seconds timeout for health check
            retry_delay = 5  # seconds
            for i in range(max_retries):
                log_and_append(f"Health check attempt {i+1}/{max_retries} at {health_check_url}...", "debug")
                try:
                    response = requests.get(health_check_url, timeout=3) # Short timeout for each attempt
                    if response.status_code >= 200 and response.status_code < 300:
                        health_check_passed = True
                        log_and_append(f"Health check PASSED. Status: {response.status_code}", "info")
                        break
                    else:
                        log_and_append(f"Health check attempt failed. Status: {response.status_code}. Response: {response.text[:100]}", "warning")
                except requests.ConnectionError:
                    log_and_append("Health check attempt failed: Connection error.", "warning")
                except requests.Timeout:
                    log_and_append("Health check attempt failed: Timeout.", "warning")
                time.sleep(retry_delay)

            if not health_check_passed:
                log_and_append("ERROR: Service health check FAILED after multiple retries.", "error")
                # Consider this a fatal error for the validation
                return False, "\n".join(output_log_lines)

            # 4. Execute Tests within the container
            log_and_append(f"STEP 4: Executing tests in container {container_name} with command: {' '.join(self.test_command)}", "info")
            test_exec_success, stdout_test, stderr_test = self._run_docker_command(
                ["docker", "exec", container_name] + self.test_command,
                timeout=600 # 10 min test timeout
            )
            log_and_append(f"Test execution STDOUT:\n{stdout_test}\nTest execution STDERR:\n{stderr_test}", "debug")

            if not test_exec_success:
                log_and_append("ERROR: Tests FAILED inside the Docker container.", "error")
                # overall_success remains False
            else:
                log_and_append("Tests PASSED inside Docker container.", "info")
                overall_success = True # All critical steps passed

        except Exception as e:
            msg = f"Unhandled exception during Docker validation: {e}"
            log_and_append(f"CRITICAL ERROR: {msg}", "error")
            logger.error(f"[{proposal_id}] {msg}", exc_info=True) # Also log with traceback
            overall_success = False
        finally:
            # 5. Cleanup
            log_and_append(f"STEP 5: Cleaning up Docker resources for {proposal_id}...", "info")
            if container_name:
                log_and_append(f"Stopping and removing container: {container_name}", "debug")
                self._run_docker_command(["docker", "stop", container_name], timeout=60) # Give time to stop
                self._run_docker_command(["docker", "rm", container_name], timeout=60)

            if image_name and build_success_flag: # Only remove image if build was successful
                log_and_append(f"Removing image: {image_name}", "debug")
                self._run_docker_command(["docker", "rmi", "-f", image_name], timeout=120) # Force remove if needed

        log_and_append(f"Docker validation finished. Overall success: {overall_success}", "info")
        return overall_success, "\n".join(output_log_lines)

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
