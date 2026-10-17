"""Real terminal color startup and bounded, local original artwork rendering."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class TerminalGraphicsTests(unittest.TestCase):
    def test_startup_corrects_inherited_agent_terminal_environment(self):
        import aim_terminal
        with patch.dict(os.environ,{'NO_COLOR':'1','TERM':'dumb','COLORTERM':''}):
            aim_terminal.configure_terminal_colors()
            app=aim_terminal.TerminalApp(ROOT)
            self.assertFalse(app.no_color)
            self.assertEqual(app.console.color_system,'truecolor')

    def test_nova_uses_colored_cells_for_each_mood_without_fake_activity(self):
        from terminal_presentation import nova_panel
        from rich.console import Console
        from io import StringIO
        for state in ('WORKING','WAITING','ERROR','IDLE','UNKNOWN','Last: WORKING'):
            stream=StringIO();console=Console(file=stream,width=34,color_system='truecolor',force_terminal=True)
            console.print(nova_panel([dict(state=state)],image_rows=5))
            value=stream.getvalue()
            self.assertIn('▀',value)
            self.assertIn('\x1b[',value)
            self.assertIn('NOVA',value)
            if state.startswith('Last:'):self.assertIn('No fresh events',value)


if __name__=='__main__':unittest.main()
