"""Wrong-interpreter launches must retain isolation and preview-only arguments."""
from pathlib import Path
import unittest
from unittest.mock import patch
import uat_launch

ROOT=Path(__file__).resolve().parents[1]


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_global_launcher_redirects_before_preflight_with_preview_flag(self):
        with patch.object(uat_launch.sys,'prefix',str(ROOT.parent)), patch.object(uat_launch.os,'execv',side_effect=SystemExit(0)) as execute, patch.object(uat_launch,'preflight') as preflight:
            with self.assertRaises(SystemExit):
                uat_launch.main(['--launch','--preview-only'])
            expected=str(ROOT/'.venv/Scripts/python.exe')
            self.assertEqual(execute.call_args.args,(expected,[expected,'-I','-B',str(ROOT/'uat_launch.py'),'--launch','--preview-only']))
            preflight.assert_not_called()

    def test_project_environment_offline_check_does_not_launch_server(self):
        with patch.object(uat_launch.sys,'prefix',str(ROOT/'.venv')), patch.object(uat_launch.os,'execv') as execute, patch.object(uat_launch,'preflight'), patch.object(uat_launch.runpy,'run_path') as server:
            self.assertEqual(uat_launch.main([]),0)
            execute.assert_not_called()
            server.assert_not_called()
