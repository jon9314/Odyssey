import unittest
from unittest.mock import patch, MagicMock, call # import call
import os

from odyssey.agent.sandbox import Sandbox

class TestSandboxDockerValidation(unittest.TestCase):

    @patch('odyssey.agent.sandbox.requests.get') # Mock requests for health check
    @patch('odyssey.agent.sandbox.os.path.exists')
    @patch('odyssey.agent.sandbox.subprocess.run')
    def test_run_validation_in_docker_success(self, mock_subprocess_run, mock_os_path_exists, mock_requests_get):
        # Configure sandbox with specific test values
        test_health_endpoint = "/custom/health"
        test_app_port = 8080
        test_host_port = 12345
        test_cmd_list = ["custom_test_runner", "--verbose"]
        test_mem_limit = "512m"
        test_cpu_limit = "0.5"
        test_network = "none" # Test with a non-default network
        test_no_new_priv = False # Test with a non-default

        sandbox = Sandbox(
            health_check_endpoint=test_health_endpoint,
            app_port_in_container=test_app_port,
            host_port_for_health_check=test_host_port,
            test_command=test_cmd_list,
            docker_memory_limit=test_mem_limit,
            docker_cpu_limit=test_cpu_limit,
            docker_network=test_network,
            docker_no_new_privileges=test_no_new_priv
        )
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

        # Mock for `docker exec` (test execution)
        mock_exec_result = MagicMock()
        mock_exec_result.returncode = 0
        mock_exec_result.stdout = "Tests executed, all good."
        mock_exec_result.stderr = ""

        mock_subprocess_run.side_effect = [
            mock_build_result,    # docker build
            mock_run_result,      # docker run
            mock_exec_result,     # docker exec (for tests)
            mock_stop_result,     # docker stop
            mock_rm_result,       # docker rm
            mock_rmi_result       # docker rmi
        ]

        # Mock requests.get for health check
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200
        mock_requests_get.return_value = mock_health_response

        success, output_log = sandbox.run_validation_in_docker(repo_clone_path, proposal_id)

        self.assertTrue(success)
        self.assertIn("Image built successfully", output_log)
        self.assertIn("containerid1234567890abcdef", output_log)
        self.assertIn(f"Health check PASSED. Status: 200", output_log)
        self.assertIn("Tests PASSED inside Docker container.", output_log)
        self.assertIn("Test execution STDOUT:\nTests executed, all good.", output_log)
        self.assertIn("Cleaning up container", output_log)
        self.assertIn("Cleaning up image", output_log)

        expected_image_name_part = f"odyssey-proposal-{proposal_id.replace('_', '-')}"

        # Check calls
        self.assertEqual(mock_subprocess_run.call_count, 6) # build, run, exec, stop, rm, rmi

        # Check docker run includes correct port mapping
        run_cmd_found = False
        for c_args, c_kwargs in mock_subprocess_run.call_args_list:
            cmd_list = c_args[0]
            if "docker" in cmd_list and "run" in cmd_list:
                if test_network == "none":
                    self.assertNotIn("-p", cmd_list, "Port mapping should NOT be present if network is 'none'")
                else:
                    self.assertIn("-p", cmd_list)
                    self.assertIn(f"{test_host_port}:{test_app_port}", cmd_list)
                # Security and Resource options
                self.assertIn("--read-only", cmd_list)
                self.assertIn("--cap-drop=ALL", cmd_list)
                self.assertIn("--memory", cmd_list)
                self.assertIn(test_mem_limit, cmd_list)
                self.assertIn("--cpus", cmd_list)
                self.assertIn(test_cpu_limit, cmd_list)
                # self.assertIn("--security-opt=no-new-privileges", cmd_list) # This was set to False for test
                self.assertNotIn("--security-opt=no-new-privileges", cmd_list) # Check it's NOT there
                self.assertIn("--network", cmd_list)
                self.assertIn(test_network, cmd_list)
                run_cmd_found = True
                break
        self.assertTrue(run_cmd_found, "Docker run command did not include expected options.")

        # Check health check call - it should NOT be called if network is 'none'
        # as port mapping would not work for localhost access from host.
        # The current Sandbox logic adds -p if network is not 'none'.
        # If network IS 'none', health check via localhost:host_port is problematic.
        # For this test, network is 'none', so port mapping is skipped by current Sandbox logic.
        # Thus, requests.get should not be called.
        if test_network == "none":
            mock_requests_get.assert_not_called()
            self.assertIn("Health check attempt failed", output_log) # Health check will fail as it can't connect
        else: # If we were testing with bridge network
            mock_requests_get.assert_called_once_with(f"http://localhost:{test_host_port}{test_health_endpoint}", timeout=3)

        # Check docker exec uses the configured test_command
        exec_cmd_found = False
        for c_args, c_kwargs in mock_subprocess_run.call_args_list:
            cmd_list = c_args[0]
            if "docker" in cmd_list and "exec" in cmd_list:
                self.assertEqual(cmd_list[-len(test_cmd_list):], test_cmd_list)
                exec_cmd_found = True
                break
        self.assertTrue(exec_cmd_found, "Docker exec command did not use the configured test_command.")


    @patch('odyssey.agent.sandbox.os.path.exists')
    def test_run_validation_no_dockerfile(self, mock_os_path_exists):
        sandbox = Sandbox() # Uses default constructor values
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
