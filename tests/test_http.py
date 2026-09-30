import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import app


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_invalid_input_returns_400(self):
        request = Request(self.base + '/api/polish', data=b'{"essay":"short"}', headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)

    def test_stage_and_result_stream_reaches_client(self):
        data = {'essay': '测试作文' * 20, 'grade': app.rag.GRADES[4], 'focus': app.rag.FOCUSES[0]}

        def fake_polish(payload, emit):
            emit({'type': 'stage', 'step': 0, 'message': 'test'})
            emit({'type': 'result', 'result': {'title': 'test'}})

        with patch.object(app.rag, 'polish', side_effect=fake_polish):
            request = Request(self.base + '/api/polish', data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                events = [json.loads(line) for line in response]
            self.assertEqual([event['type'] for event in events], ['stage', 'result'])

    def test_feedback_endpoint(self):
        data = {'run_id': 'test', 'reviewer': 'A', 'faithfulness': 4, 'fluency': 4, 'grade_fit': 4}
        with patch.object(app.evaluation, 'save_feedback', return_value={'message': 'saved'}) as save:
            request = Request(self.base + '/api/feedback', data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                self.assertEqual(json.load(response), {'message': 'saved'})
            save.assert_called_once_with(data)


if __name__ == '__main__':
    unittest.main()
