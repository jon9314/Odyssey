import unittest
import sys
import os
import shutil # For cleaning up test files/dirs

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# Attempt to import plugin classes
try:
    from odyssey.plugins.calendar import CalendarTool
    from odyssey.plugins.ocr import OCRTool
    from odyssey.plugins.file_ops import FileOpsTool
except ImportError as e:
    print(f"Error importing plugin classes for tests: {e}")
    # Define dummy classes if imports fail, to allow test structure to be seen
    class CalendarTool: pass
    class OCRTool: pass
    class FileOpsTool: pass


class TestCalendarTool(unittest.TestCase):
    def setUp(self):
        try:
            self.calendar_tool = CalendarTool() # Uses mock service by default
        except NameError:
            self.skipTest("CalendarTool class not available due to import error.")

    def test_calendar_list_events_mock(self):
        if not hasattr(self, 'calendar_tool') or not isinstance(self.calendar_tool, CalendarTool):
             self.skipTest("CalendarTool not properly initialized.")
        action = "list_events"
        params = {"max_results": 2}
        result = self.calendar_tool.execute(action, params)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) <= 2)
        if len(result) > 0:
            self.assertIn("summary", result[0])

    def test_calendar_create_event_mock(self):
        if not hasattr(self, 'calendar_tool') or not isinstance(self.calendar_tool, CalendarTool):
             self.skipTest("CalendarTool not properly initialized.")
        action = "create_event"
        params = {
            "summary": "Plugin Test Event",
            "start_datetime": "2024-12-01T10:00:00Z",
            "end_datetime": "2024-12-01T11:00:00Z"
        }
        result = self.calendar_tool.execute(action, params)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("summary"), params["summary"])
        self.assertIn("id", result)


class TestOCRTool(unittest.TestCase):
    def setUp(self):
        try:
            self.ocr_tool = OCRTool()
            self.dummy_image_path = "test_ocr_image.png"
            with open(self.dummy_image_path, "w") as f:
                f.write("dummy image content for ocr test")
        except NameError:
            self.skipTest("OCRTool class not available due to import error.")
        except Exception as e:
            self.fail(f"OCRTool setUp failed: {e}")


    def tearDown(self):
        if os.path.exists(self.dummy_image_path):
            os.remove(self.dummy_image_path)

    def test_ocr_extract_text_mock(self):
        if not hasattr(self, 'ocr_tool') or not isinstance(self.ocr_tool, OCRTool):
             self.skipTest("OCRTool not properly initialized.")
        action = "extract_text"
        params = {"image_path": self.dummy_image_path}
        result = self.ocr_tool.execute(action, params)
        self.assertIsInstance(result, str)
        self.assertIn("Mock OCR Text", result)

    def test_ocr_file_not_found(self):
        if not hasattr(self, 'ocr_tool') or not isinstance(self.ocr_tool, OCRTool):
            self.skipTest("OCRTool not properly initialized.")
        action = "extract_text"
        params = {"image_path": "non_existent_image.png"}
        result = self.ocr_tool.execute(action, params)
        self.assertIn("Error: Image file not found", result)


class TestFileOpsTool(unittest.TestCase):
    def setUp(self):
        self.test_workspace = "test_file_ops_workspace"
        # Clean up before test, then create
        if os.path.exists(self.test_workspace):
            shutil.rmtree(self.test_workspace)
        os.makedirs(self.test_workspace, exist_ok=True)
        try:
            self.file_ops = FileOpsTool(base_directory=self.test_workspace)
        except NameError:
            self.skipTest("FileOpsTool class not available due to import error.")
        except Exception as e:
            self.fail(f"FileOpsTool setUp failed: {e}")

    def tearDown(self):
        if os.path.exists(self.test_workspace):
            shutil.rmtree(self.test_workspace)

    def test_fileops_write_read_delete(self):
        if not hasattr(self, 'file_ops') or not isinstance(self.file_ops, FileOpsTool):
            self.skipTest("FileOpsTool not properly initialized.")

        file_path = "my_test_file.txt"
        content = "Hello, FileOps! This is a test."

        # Write
        write_result = self.file_ops.execute("write_file", {"path": file_path, "content": content})
        self.assertIn("written successfully", write_result)
        self.assertTrue(os.path.exists(os.path.join(self.test_workspace, file_path)))

        # Read
        read_result = self.file_ops.execute("read_file", {"path": file_path})
        self.assertEqual(read_result, content)

        # Delete
        delete_result = self.file_ops.execute("delete_file", {"path": file_path})
        self.assertIn("deleted successfully", delete_result)
        self.assertFalse(os.path.exists(os.path.join(self.test_workspace, file_path)))

    def test_fileops_list_directory(self):
        if not hasattr(self, 'file_ops') or not isinstance(self.file_ops, FileOpsTool):
            self.skipTest("FileOpsTool not properly initialized.")

        self.file_ops.execute("write_file", {"path": "file1.txt", "content": "1"})
        os.makedirs(os.path.join(self.test_workspace, "subdir1"), exist_ok=True)
        self.file_ops.execute("write_file", {"path": "subdir1/file2.txt", "content": "2"})

        # List base
        list_result = self.file_ops.execute("list_directory", {"path": "."})
        self.assertIsInstance(list_result, list)
        found_file1 = any(item['name'] == 'file1.txt' and item['type'] == 'file' for item in list_result)
        found_subdir1 = any(item['name'] == 'subdir1' and item['type'] == 'dir' for item in list_result)
        self.assertTrue(found_file1)
        self.assertTrue(found_subdir1)

        # List subdir
        list_sub_result = self.file_ops.execute("list_directory", {"path": "subdir1"})
        found_file2 = any(item['name'] == 'file2.txt' and item['type'] == 'file' for item in list_sub_result)
        self.assertTrue(found_file2)

    def test_fileops_path_traversal_prevention(self):
        if not hasattr(self, 'file_ops') or not isinstance(self.file_ops, FileOpsTool):
            self.skipTest("FileOpsTool not properly initialized.")

        # Attempt to write outside the workspace
        # The FileOpsTool's _resolve_path should prevent this.
        # ../../ is relative to self.test_workspace
        naughty_path = "../../outside_file_ops_test.txt"
        write_result = self.file_ops.execute("write_file", {"path": naughty_path, "content": "naughty"})
        self.assertIn("Error: Path", write_result) # Check for the error message from _resolve_path
        self.assertIn("is outside the allowed base directory", write_result)

        # Ensure the file was NOT created outside
        # This relative path is from the test script's location (odyssey/tests/)
        self.assertFalse(os.path.exists(os.path.join(PROJECT_ROOT, "outside_file_ops_test.txt")))


if __name__ == '__main__':
    unittest.main()
