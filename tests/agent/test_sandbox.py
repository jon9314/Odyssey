import unittest
from unittest.mock import patch, MagicMock, call # import call
import os

from odyssey.agent.sandbox import Sandbox

class TestSandboxDockerValidation(unittest.TestCase):

    @patch('odyssey.agent.sandbox.os.path.exists')
    @patch('odyssey.agent.sandbox.subprocess.run') # Mock subprocess.run used by _run_docker_command
    def test_run_validation_in_docker_success(self, mock_subprocess_run, mock_os_path_exists):
        sandbox = Sandbox()
        repo_clone_path = "/test/repo_clone"
        proposal_id = "prop_docker_001"

        mock_os_path_exists.return_value = True # Assume Dockerfile exists

        # Mock Docker command results
        mock_build_result = MagicMock()
        mock_build_result.returncode = 0
        mock_build_result.stdout = "Image built successfully"
        mock_build_result.stderr = ""

        mock_run_result = MagicMock()
        mock_run_result.returncode = 0
        # docker run -d returns container ID
        mock_run_result.stdout = "containerid1234567890abcdef"
        mock_run_result.stderr = ""

        # This is where the actual test execution inside Docker would be mocked.
        # Since it's simulated in Sandbox.run_validation_in_docker with random.choice,
        # we don't need to mock a `docker exec` here unless we change that simulation.
        # For this test, we rely on the internal simulation of test success.
        # To make it deterministic, we can patch `random.choice`.

        mock_stop_result = MagicMock()
        mock_stop_result.returncode = 0
        mock_rm_result = MagicMock()
        mock_rm_result.returncode = 0
        mock_rmi_result = MagicMock()
        mock_rmi_result.returncode = 0

        mock_subprocess_run.side_effect = [
            mock_build_result,  # docker build
            mock_run_result,    # docker run
            # Health check and test execution are simulated internally for now.
            # If they used _run_docker_command, they would be here.
            mock_stop_result,   # docker stop
            mock_rm_result,     # docker rm
            mock_rmi_result     # docker rmi
        ]

        # Patch random.choice if relying on its simulation for pass/fail
        with patch('odyssey.agent.sandbox.random.choice', return_value=True): # Force simulated test pass
            success, output_log = sandbox.run_validation_in_docker(repo_clone_path, proposal_id)

        self.assertTrue(success)
        self.assertIn("Image built successfully", output_log)
        self.assertIn("containerid1234567890abcdef", output_log) # Check if container ID from run is in log
        self.assertIn("(Simulated) Tests passed inside Docker container", output_log)
        self.assertIn("Cleaning up container", output_log)
        self.assertIn("Cleaning up image", output_log)

        expected_image_name_part = f"odyssey-proposal-{proposal_id.replace('_', '-')}"

        # Check calls to subprocess_run (indirectly via _run_docker_command)
        self.assertGreaterEqual(mock_subprocess_run.call_count, 4) # build, run, stop, rm, rmi (at least 4, maybe 5 if rmi is distinct)

        # Example of checking a specific call more carefully:
        build_call = call(['docker', 'build', '-t', unittest.mock.ANY, '.'], cwd=repo_clone_path, capture_output=True, text=True, check=False)
        # Check if ANY of the calls to subprocess_run matches this.
        # This is a bit tricky because the image name has a random hex.
        # A more robust check would be to capture the image name from the call.
        # For now, check essential parts.
        # Check that a build command was made
        found_build_call = False
        for c in mock_subprocess_run.call_args_list:
            args, kwargs = c
            if args[0][0] == 'docker' and args[0][1] == 'build' and args[0][3].startswith(expected_image_name_part) and kwargs.get('cwd') == repo_clone_path:
                found_build_call = True
                break
        self.assertTrue(found_build_call, "Docker build command not called as expected.")


    @patch('odyssey.agent.sandbox.os.path.exists')
    def test_run_validation_no_dockerfile(self, mock_os_path_exists):
        sandbox = Sandbox()
        repo_clone_path = "/test/repo_clone_no_dockerfile"
        proposal_id = "prop_docker_002"
        mock_os_path_exists.return_value = False # Dockerfile does not exist

        success, output_log = sandbox.run_validation_in_docker(repo_clone_path, proposal_id)

        self.assertFalse(success)
        self.assertIn("Dockerfile not found", output_log)
        mock_os_path_exists.assert_called_once_with(os.path.join(repo_clone_path, "Dockerfile"))

    @patch('odyssey.agent.sandbox.os.path.exists')
    @patch('odyssey.agent.sandbox.subprocess.run')
    def test_run_validation_docker_build_fails(self, mock_subprocess_run, mock_os_path_exists):
        sandbox = Sandbox()
        repo_clone_path = "/test/repo_clone_build_fails"
        proposal_id = "prop_docker_003"
        mock_os_path_exists.return_value = True

        mock_build_fail_result = MagicMock()
        mock_build_fail_result.returncode = 1
        mock_build_fail_result.stdout = "Build stdout with error"
        mock_build_fail_result.stderr = "Docker build failed miserably"

        # Only mock the build call, as it should fail and return
        mock_subprocess_run.return_value = mock_build_fail_result

        success, output_log = sandbox.run_validation_in_docker(repo_clone_path, proposal_id)

        self.assertFalse(success)
        self.assertIn("Docker image build failed", output_log)
        self.assertIn("Docker build failed miserably", output_log)
        # Ensure cleanup for image isn't attempted if build failed (though image name might not be set for rmi)
        # The `finally` block in `run_validation_in_docker` has `if image_name and build_success:`. This is correct.
        # So, rmi should not be called. We can check call_count for subprocess_run.
        mock_subprocess_run.assert_called_once() # Only build should be called

    # TODO: Add tests for:
    # - Docker run fails
    # - Simulated test execution fails (patch random.choice to return False)
    # - Cleanup commands failing (e.g., docker stop/rm/rmi fail, check logs but overall success might depend on main task)

if __name__ == '__main__':
    unittest.main()
