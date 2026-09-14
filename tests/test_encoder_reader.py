from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from input.encoder_reader import EncoderReader, _default_serial_factory


class FakeSerial:
    def __init__(self, lines):
        self.lines = list(lines)
        self.closed = False

    def readline(self):
        return self.lines.pop(0) if self.lines else b''

    def close(self):
        self.closed = True


class EncoderReaderTests(unittest.TestCase):
    def test_default_factory_is_available_without_a_pyserial_serial_class(self):
        self.assertTrue(callable(_default_serial_factory()))

    def test_protocol_accepts_only_expected_events(self):
        good = ('{"type":"encoder","delta":1}',
                '{"type":"encoder","delta":-1}',
                '{"type":"encoder","press":"short"}',
                '{"type":"encoder","press":"long"}',
                '{"type":"encoder","status":"ready"}')
        for line in good:
            with self.subTest(line=line):
                self.assertIsNotNone(EncoderReader.parse(line))
        for line in ('', 'not json', '[]', '{"type":"other"}',
                     '{"type":"encoder","delta":2}',
                     '{"type":"encoder","press":"hold"}',
                     '{"type":"encoder","delta":1,"extra":true}'):
            with self.subTest(line=line):
                self.assertIsNone(EncoderReader.parse(line))

    def test_reader_decodes_lines_and_closes(self):
        fake = FakeSerial([b'bad\n', b'{"type":"encoder","delta":1}\r\n'])
        reader = EncoderReader('unused', serial_factory=lambda *args, **kw: fake)
        self.assertIsNone(reader.read())
        self.assertEqual(reader.read(), {'type': 'encoder', 'delta': 1})
        reader.close()
        self.assertTrue(fake.closed)


if __name__ == '__main__':
    unittest.main()
