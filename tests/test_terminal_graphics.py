"""Real terminal color startup and bounded, local original artwork rendering."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))


class TerminalGraphicsTests(unittest.TestCase):
    def test_console_helper_routes_nova_mode_before_host_arguments(self):
        import aim_control
        with patch('aim_terminal.main',return_value=0) as terminal:
            self.assertEqual(aim_control.main(['--terminal','--check']),0)
            terminal.assert_called_once_with(['--check'])

    def test_frozen_art_reads_extracted_resource_instead_of_source_location(self):
        import base64,json,tempfile,zlib
        from terminal_art import pixels
        raw=bytes([1,2,3])*(40*26)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'assets/terminal').mkdir(parents=True)
            (root/'assets/terminal/nova.json').write_text(json.dumps(dict(width=40,height=26,
                frames={'work':base64.b85encode(zlib.compress(raw)).decode('ascii')})))
            try:
                with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',directory,create=True):
                    pixels.cache_clear();self.assertEqual(pixels('work')[2],raw)
            finally:pixels.cache_clear()

    def test_startup_corrects_inherited_agent_terminal_environment(self):
        import aim_terminal
        with patch.dict(os.environ,{'NO_COLOR':'1','TERM':'dumb','COLORTERM':''}):
            aim_terminal.configure_terminal_colors()
            app=aim_terminal.TerminalApp(ROOT)
            self.assertFalse(app.no_color)
            self.assertIn(app.console.color_system,('256','truecolor'))

    @unittest.skipUnless(os.name=='nt','Windows launcher')
    def test_actual_launcher_uses_truecolor_with_inherited_no_color(self):
        import subprocess
        env=dict(os.environ,NO_COLOR='1',TERM='dumb',AI_MONITOR_PYTHON=sys.executable)
        result=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/c',str(ROOT/'AI-Monitor-Terminal.bat'),'--check'],
                              capture_output=True,text=True,timeout=20,env=env,cwd=ROOT)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Color: truecolor',result.stdout)

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
