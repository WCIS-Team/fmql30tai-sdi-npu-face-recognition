"""Safety properties for the offline clock-tree pruning tool."""
import importlib.util
from pathlib import Path
import tempfile
import tkinter
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prune_clock_routes.py'
spec = importlib.util.spec_from_file_location('clock_pruning', SCRIPT)
pruning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pruning)


class ClockTreeSafety(unittest.TestCase):
    def setUp(self):
        self.tcl = tkinter.Tcl()

    def graph(self, edges, sinks=('static',), nodes=('source', 'shared', 'static', 'retired')):
        return dict(nodes=self.tcl.call('list', *nodes),
                    source_nodes=self.tcl.call('list', 'source'),
                    static_sink_nodes=self.tcl.call('list', *sinks),
                    static_pin_count=str(len(sinks)),
                    edges=self.tcl.call('list', *[self.tcl.call('list', *e) for e in edges]))

    def test_shared_trunk_survives_and_old_exclusive_branch_is_removed(self):
        g = self.graph([('p0', 'source', 'shared', '1'),
                        ('p1', 'shared', 'static', '1'),
                        ('p2', 'shared', 'retired', '1')])
        route, nodes, sinks, stats = pruning.prune_tree(self.tcl, g)
        self.assertEqual(set(nodes), {'source', 'shared', 'static'})
        self.assertEqual(sinks, ('static',))
        self.assertNotIn('retired', route)
        self.assertEqual(stats['removed_exclusive_nodes'], 1)

    def test_bidirectional_pip_can_be_traversed_from_the_unique_source(self):
        g = self.graph([('p0', 'shared', 'source', '0'),
                        ('p1', 'shared', 'static', '1'),
                        ('p2', 'shared', 'retired', '1')])
        self.assertEqual(set(pruning.prune_tree(self.tcl, g)[1]), {'source', 'shared', 'static'})

    def test_directional_pip_cannot_be_reversed(self):
        g = self.graph([('p0', 'shared', 'source', '1'),
                        ('p1', 'shared', 'static', '1'),
                        ('p2', 'shared', 'retired', '1')])
        with self.assertRaises(ValueError):
            pruning.prune_tree(self.tcl, g)

    def test_cycle_and_disconnected_source_are_rejected(self):
        g = self.graph([('p0', 'shared', 'static', '0'),
                        ('p1', 'static', 'retired', '0'),
                        ('p2', 'retired', 'shared', '0')])
        with self.assertRaises(ValueError):
            pruning.prune_tree(self.tcl, g)

    def test_unrouted_static_load_is_rejected(self):
        g = self.graph([('p0', 'source', 'shared', '1'),
                        ('p1', 'shared', 'static', '1'),
                        ('p2', 'shared', 'retired', '1')], sinks=('missing',))
        with self.assertRaises(ValueError):
            pruning.prune_tree(self.tcl, g)

    def test_exported_data_is_parsed_without_executing_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.tcl'
            path.write_text('set value {[set ::unexpected 1]}\n', encoding='utf-8')
            self.assertEqual(pruning.read_sets(self.tcl, path)['value'], '[set ::unexpected 1]')
            self.assertEqual(self.tcl.call('info', 'exists', '::unexpected'), 0)
            path.write_text('exec echo dangerous\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                pruning.read_sets(self.tcl, path)


if __name__ == '__main__':
    unittest.main()
