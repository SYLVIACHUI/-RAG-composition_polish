import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import socket
import time
import uvicorn

import app


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.base = f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(app.app, log_level='error', lifespan='off'))
        cls.thread = threading.Thread(target=lambda: cls.server.run(sockets=[cls.sock]), daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError('Uvicorn startup timed out')
            time.sleep(0.01)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        cls.sock.close()

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

    def test_openapi_documents_typed_requests(self):
        with urlopen(self.base + '/openapi.json') as response:
            schema = json.load(response)
        self.assertIn('/api/polish', schema['paths'])
        self.assertEqual(schema['components']['schemas']['PolishRequest']['properties']['essay']['maxLength'], 2000)
        with urlopen(self.base + '/') as response:
            self.assertIn('语你一起', response.read().decode())

    def test_request_guards(self):
        for body, headers, expected in [
            (b'{}', {'Content-Type':'text/plain'}, 415),
            (b'{}', {'Content-Type':'application/json', 'Origin':'https://example.com'}, 403),
            (b'x' * 24001, {'Content-Type':'application/json'}, 400),
            (b'{', {'Content-Type':'application/json'}, 400),
        ]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.base+'/api/polish', data=body, headers=headers), timeout=5)
            self.assertEqual(caught.exception.code, expected)

    def test_error_event_releases_model_lock(self):
        data = {'essay': '测试作文'*20, 'grade': app.rag.GRADES[4], 'focus': app.rag.FOCUSES[0]}
        with patch.object(app.rag, 'polish', side_effect=app.rag.RagError('test failure')):
            request = Request(self.base+'/api/polish', data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
            with urlopen(request, timeout=5) as response:
                events = [json.loads(line) for line in response]
        self.assertEqual(events[0]['type'], 'error')
        self.assertFalse(app.MODEL_LOCK.locked())

    def test_progress_is_live_and_other_requests_remain_responsive(self):
        finish = threading.Event()
        data = {'essay': '测试作文'*20, 'grade': app.rag.GRADES[4], 'focus': app.rag.FOCUSES[0]}
        def fake_polish(payload, emit):
            emit({'type':'stage','message':'working'})
            if not finish.wait(5):
                raise RuntimeError('test did not release worker')
            emit({'type':'result','result':{'title':'done'}})
        request = Request(self.base+'/api/polish', data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
        with patch.object(app.rag, 'polish', side_effect=fake_polish):
            try:
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(json.loads(response.readline())['type'], 'stage')
                    with urlopen(self.base+'/api/options', timeout=2) as options:
                        self.assertEqual(options.status, 200)
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=2)
                    self.assertEqual(caught.exception.code, 409)
                    finish.set()
                    self.assertEqual(json.loads(response.readline())['type'], 'result')
            finally:
                finish.set()

    def test_index_failure_releases_lock(self):
        with patch.object(app.rag, 'ensure_index', side_effect=app.rag.RagError('offline')):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.base+'/api/index', data=b'{}', headers={'Content-Type':'application/json'}))
        self.assertEqual(caught.exception.code, 502)
        self.assertFalse(app.MODEL_LOCK.locked())


if __name__ == '__main__':
    unittest.main()
