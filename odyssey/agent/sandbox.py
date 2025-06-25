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
        logger.info("Sandbox initialized.")

    def _run_docker_command(self, command: list, cwd: str = None) -> tuple[bool, str, str]:
        """
        Helper to run Docker commands.
        Returns (success, stdout, stderr).
        """
        try:
            logger.debug(f"Running Docker command: {' '.join(command)} in {cwd or 'current dir'}")
            process = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False
            )
            if process.returncode == 0:
                logger.debug(f"Docker command successful. STDOUT: {process.stdout[:200]}")
                return True, process.stdout.strip(), process.stderr.strip()
            else:
                logger.error(f"Docker command failed. RC: {process.returncode}. STDERR: {process.stderr}. STDOUT: {process.stdout}")
                return False, process.stdout.strip(), process.stderr.strip()
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
        output_log = []
        image_name = f"odyssey-proposal-{proposal_id.replace('_', '-')}-{os.urandom(4).hex()}"
        container_name = f"{image_name}-container"
        success = False

        dockerfile_path = os.path.join(repo_clone_path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            msg = "Dockerfile not found at the root of the repository clone. Cannot proceed with Docker validation."
            logger.warning(f"[{proposal_id}] {msg}")
            output_log.append(f"ERROR: {msg}")
            return False, "\n".join(output_log)

        try:
            # 1. Build Docker Image
            output_log.append(f"Attempting to build Docker image: {image_name} from path: {repo_clone_path}")
            logger.info(f"[{proposal_id}] Building Docker image: {image_name}")
            build_success, stdout, stderr = self._run_docker_command(
                ["docker", "build", "-t", image_name, "."], cwd=repo_clone_path
            )
            output_log.append(f"Docker build STDOUT:\n{stdout}")
            output_log.append(f"Docker build STDERR:\n{stderr}")
            if not build_success:
                msg = f"Docker image build failed for {image_name}."
                logger.error(f"[{proposal_id}] {msg}")
                output_log.append(f"ERROR: {msg}")
                return False, "\n".join(output_log)
            logger.info(f"[{proposal_id}] Docker image {image_name} built successfully.")

            # 2. Run Docker Container (example: detached mode for a service)
            # This part is highly dependent on what the Docker image does.
            # Assuming it starts a service that needs to be health-checked, then tests run via `docker exec`.
            output_log.append(f"Attempting to run Docker container: {container_name} from image: {image_name}")
            logger.info(f"[{proposal_id}] Running Docker container: {container_name}")
            run_success, stdout, stderr = self._run_docker_command(
                ["docker", "run", "--name", container_name, "-d", image_name] # Basic run, adjust ports/volumes as needed
            )
            output_log.append(f"Docker run STDOUT:\n{stdout}")
            output_log.append(f"Docker run STDERR:\n{stderr}")
            if not run_success:
                msg = f"Failed to start Docker container {container_name}."
                logger.error(f"[{proposal_id}] {msg}")
                output_log.append(f"ERROR: {msg}")
                return False, "\n".join(output_log) # Cleanup of image will happen in finally
            logger.info(f"[{proposal_id}] Docker container {container_name} started.")

            # 3. Health Check (simulated)
            # In a real scenario, ping an endpoint, check logs, etc.
            output_log.append("Simulating health check for service in container...")
            logger.info(f"[{proposal_id}] Simulating health check for {container_name}...")
            time.sleep(5) # Give container time to start
            health_check_passed = True # Placeholder
            if not health_check_passed:
                msg = "Service health check failed."
                logger.warning(f"[{proposal_id}] {msg}")
                output_log.append(f"WARNING: {msg}")
                # Decide if this is a hard failure or if tests should still run
            else:
                output_log.append("Health check passed (simulated).")
                logger.info(f"[{proposal_id}] Health check passed for {container_name} (simulated).")


            # 4. Execute Tests within the container
            # This assumes a test command is known (e.g., defined in project or a standard command)
            # For example: `pytest`, `npm test`, or a custom script `run_tests_in_container.sh`
            test_command_in_container = ["python", "-m", "unittest", "discover", "-s", "./tests"] # Example Python tests
            # test_command_in_container = ["./scripts/run_container_tests.sh"] # Example custom script

            output_log.append(f"Attempting to execute tests in container: {' '.join(test_command_in_container)}")
            logger.info(f"[{proposal_id}] Executing tests in {container_name}: {' '.join(test_command_in_container)}")

            # Simulating test execution for now as actual command depends on project structure
            # In a real scenario:
            # test_exec_success, stdout_test, stderr_test = self._run_docker_command(
            #     ["docker", "exec", container_name] + test_command_in_container
            # )
            # output_log.append(f"Test execution STDOUT:\n{stdout_test}")
            # output_log.append(f"Test execution STDERR:\n{stderr_test}")
            # if not test_exec_success:
            #     msg = "Tests failed inside the Docker container."
            #     logger.warning(f"[{proposal_id}] {msg}")
            #     output_log.append(f"ERROR: {msg}")
            #     # success remains False (from initialization)
            # else:
            #     logger.info(f"[{proposal_id}] Tests passed inside Docker container.")
            #     output_log.append("Tests passed inside Docker container.")
            #     success = True # Tests passed!

            # Simulated test outcome:
            import random
            import time # Ensure time is imported
            time.sleep(5) # Simulate test execution time
            if random.choice([True, True, False]): # Higher chance of success for demo
                logger.info(f"[{proposal_id}] (Simulated) Tests passed inside Docker container.")
                output_log.append("(Simulated) Tests passed inside Docker container.")
                success = True
            else:
                logger.warning(f"[{proposal_id}] (Simulated) Tests failed inside the Docker container.")
                output_log.append("(Simulated) ERROR: Tests failed inside Docker container. Check logs for details.")
                # success remains False

        except Exception as e:
            msg = f"Unhandled exception during Docker validation: {e}"
            logger.error(f"[{proposal_id}] {msg}", exc_info=True)
            output_log.append(f"CRITICAL ERROR: {msg}")
            success = False
        finally:
            # 5. Cleanup
            if container_name: # Check if container was attempted to be named/run
                logger.info(f"[{proposal_id}] Cleaning up container: {container_name}")
                stop_success, _, _ = self._run_docker_command(["docker", "stop", container_name])
                if stop_success: logger.debug(f"[{proposal_id}] Stopped container {container_name}")
                else: logger.warning(f"[{proposal_id}] Failed to stop container {container_name} (it might not have been running).")

                rm_success, _, _ = self._run_docker_command(["docker", "rm", container_name])
                if rm_success: logger.debug(f"[{proposal_id}] Removed container {container_name}")
                else: logger.warning(f"[{proposal_id}] Failed to remove container {container_name} (it might have already been removed).")

            if image_name and build_success: # Only remove image if build was successful and name is known
                logger.info(f"[{proposal_id}] Cleaning up image: {image_name}")
                rmi_success, _, _ = self._run_docker_command(["docker", "rmi", image_name])
                if rmi_success: logger.debug(f"[{proposal_id}] Removed image {image_name}")
                else: logger.warning(f"[{proposal_id}] Failed to remove image {image_name}.")

        return success, "\n".join(output_log)

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
