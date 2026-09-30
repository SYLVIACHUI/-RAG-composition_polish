"""运行 python app.py，然后访问 http://127.0.0.1:8000。"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlparse

import rag
import evaluation

MODEL_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data):
        encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            page = (rag.ROOT / 'static' / 'index.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif path == '/api/status':
            self.send_json(200, rag.status())
        elif path == '/api/corpus':
            self.send_json(200, rag.read_corpus())
        elif path == '/api/options':
            self.send_json(200, {'grades': rag.GRADES, 'focuses': rag.FOCUSES, 'sample': rag.SAMPLE})
        else:
            self.send_json(404, {'error': '页面不存在。'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/api/polish', '/api/index', '/api/feedback'):
            self.send_json(404, {'error': '接口不存在。'})
            return
        # 仅接受本机页面发出的 JSON 请求；不开放跨域访问。
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            self.send_json(403, {'error': '不允许跨域请求。'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.send_json(415, {'error': '请使用 application/json。'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 24000:
                raise ValueError('请求大小不合法。')
            data = json.loads(self.rfile.read(length))
            if path == '/api/polish':
                rag.validate_request(data)
            elif not isinstance(data, dict):
                raise ValueError('请求必须是 JSON 对象。')
        except (ValueError, UnicodeError) as exc:
            self.send_json(400, {'error': str(exc)})
            return
        if path == '/api/feedback':
            try:
                self.send_json(200, evaluation.save_feedback(data))
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)})
            return
        if not MODEL_LOCK.acquire(blocking=False):
            self.send_json(409, {'error': '模型正在处理另一项任务，请稍后重试。'})
            return
        try:
            if path == '/api/index':
                self.send_json(200, rag.ensure_index(force=True))
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

            def emit(event):
                self.wfile.write((json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8'))
                self.wfile.flush()

            try:
                rag.polish(data, emit)
            except (rag.RagError, ValueError) as exc:
                emit({'type': 'error', 'message': str(exc)})
            except Exception:
                import traceback
                traceback.print_exc()
                emit({'type': 'error', 'message': '处理失败，请查看服务终端日志后重试。'})
        except rag.RagError as exc:
            self.send_json(502, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            MODEL_LOCK.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='语你一起 · 中小学作文润色 · 本地 RAG')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--index', action='store_true', help='先建立向量库再启动')
    args = parser.parse_args()
    if args.index:
        print('索引已就绪：', rag.ensure_index(), flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'语你一起：http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止。')
    finally:
        server.server_close()
