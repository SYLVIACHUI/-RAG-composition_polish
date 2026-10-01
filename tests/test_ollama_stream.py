import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import rag


class OllamaStreamTests(unittest.TestCase):
    def response(self, chunks):
        return io.BytesIO(b''.join(json.dumps(c).encode() + b'\n' for c in chunks))

    def test_stream_joins_content_excludes_thinking_and_reports_progress(self):
        chunks = [{'message': {'thinking': 'private analysis'}},
                  {'message': {'content': '{"title":'}},
                  {'message': {'content': '"test"}'}, 'done': True, 'done_reason': 'stop'}]
        progress = []
        with patch.object(rag, 'urlopen', return_value=self.response(chunks)) as request, \
             patch.object(rag.time, 'monotonic', side_effect=[0, 4, 5, 6]):
            result = rag.ollama('/api/chat', {'stream': False}, on_progress=progress.append)
        self.assertTrue(json.loads(request.call_args.args[0].data)['stream'])
        self.assertEqual(json.loads(result['message']['content']), {'title': 'test'})
        self.assertEqual(result['done_reason'], 'stop')
        self.assertEqual(progress, [4])

    def test_incomplete_and_server_error_are_rejected(self):
        for chunks, message in [([{'message': {'content': 'partial'}}], '中途断开'),
                                ([{'error': 'out of memory'}], 'out of memory')]:
            with patch.object(rag, 'urlopen', return_value=self.response(chunks)):
                with self.assertRaisesRegex(rag.RagError, message):
                    rag.ollama('/api/chat', {})

    def test_timeout_and_connection_errors_are_distinct(self):
        for error, message in [(TimeoutError(), '连续 7 秒未响应'),
                               (URLError(TimeoutError()), '连续 7 秒未响应'),
                               (URLError(ConnectionRefusedError()), '无法连接')]:
            with patch.object(rag, 'urlopen', side_effect=error):
                with self.assertRaisesRegex(rag.RagError, message):
                    rag.ollama('/api/chat', {}, timeout=7)

    def test_total_time_limit(self):
        with patch.object(rag, 'urlopen', return_value=self.response([{'message': {}}])), \
             patch.object(rag.time, 'monotonic', side_effect=[0, 901]):
            with self.assertRaisesRegex(rag.RagError, '15 分钟'):
                rag.ollama('/api/chat', {})
