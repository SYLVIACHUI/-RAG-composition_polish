"""FastAPI 服务：python app.py，或 python -m uvicorn app:app。"""
import argparse
import asyncio
import json
import logging
import threading
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
import uvicorn
import rag
import evaluation

MODEL_LOCK = threading.Lock()
app = FastAPI(title='语你一起', version='2.0.0', description='本地作文混合检索、润色与人工评价')

class PolishRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    essay: str = Field(min_length=40, max_length=2000)
    grade: str = Field(json_schema_extra={'enum': rag.GRADES})
    focus: str = Field(json_schema_extra={'enum': rag.FOCUSES})
    requirement: str = Field(default='', max_length=200)

class FeedbackRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    run_id: str
    reviewer: Literal['A', 'B']
    faithfulness: int = Field(ge=1, le=5)
    fluency: int = Field(ge=1, le=5)
    grade_fit: int = Field(ge=1, le=5)
    note: str = Field(default='', max_length=500)

@app.middleware('http')
async def local_requests(request: Request, call_next):
    if request.method == 'POST':
        port = request.url.port or 80
        origin = request.headers.get('origin')
        if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            return JSONResponse({'error': '不允许跨域请求。'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return JSONResponse({'error': '请使用 application/json。'}, status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 24000:
                return JSONResponse({'error': '请求大小不合法。'}, status_code=400)
        if not body:
            return JSONResponse({'error': '请求不能为空。'}, status_code=400)
        request._body = bytes(body)  # 缓存供 FastAPI 随后的 Pydantic 解析使用。
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': '请求参数不合法：' + exc.errors()[0]['msg']}, status_code=400)

@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error': str(exc.detail)}, status_code=exc.status_code)

@app.exception_handler(rag.RagError)
async def model_error(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=502)

@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=400)

@app.get('/', include_in_schema=False)
def home():
    return FileResponse(rag.ROOT / 'static' / 'index.html', media_type='text/html')

@app.get('/api/options')
def options():
    return {'grades': rag.GRADES, 'focuses': rag.FOCUSES, 'sample': rag.SAMPLE}

@app.get('/api/status')
def status():
    return rag.status()

@app.get('/api/corpus')
def corpus():
    return rag.read_corpus()

@app.post('/api/feedback')
def feedback(data: FeedbackRequest):
    return evaluation.save_feedback(data.model_dump(exclude_unset=True))

def acquire_model():
    if not MODEL_LOCK.acquire(blocking=False):
        raise HTTPException(409, '模型正在处理另一项任务，请稍后重试。')

@app.post('/api/index')
def reindex(data: dict):
    acquire_model()
    try:
        return rag.ensure_index(force=True)
    finally:
        MODEL_LOCK.release()

class ClientDisconnected(Exception):
    pass

@app.post('/api/polish', response_class=StreamingResponse,
          responses={200: {'content': {'application/x-ndjson': {}}}})
async def polish(data: PolishRequest):
    payload = data.model_dump()
    rag.validate_request(payload)
    acquire_model()
    loop = asyncio.get_running_loop()
    events = asyncio.Queue()
    stopped = threading.Event()

    def publish(event):
        if not loop.is_closed():
            try:
                loop.call_soon_threadsafe(events.put_nowait, event)
            except RuntimeError:
                pass

    def emit(event):
        if stopped.is_set():
            raise ClientDisconnected()
        publish(event)

    def work():
        try:
            rag.polish(payload, emit)
        except ClientDisconnected:
            pass
        except (rag.RagError, ValueError) as exc:
            if not stopped.is_set():
                publish({'type': 'error', 'message': str(exc)})
        except Exception:
            logging.exception('作文润色失败')
            if not stopped.is_set():
                publish({'type': 'error', 'message': '处理失败，请查看服务终端日志后重试。'})
        finally:
            # 即使浏览器断开，也等工作线程退出后再允许下一项计算。
            MODEL_LOCK.release()
            publish(None)

    async def stream():
        try:
            while True:
                event = await events.get()
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + '\n'
        finally:
            stopped.set()

    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        MODEL_LOCK.release()
        raise
    return StreamingResponse(stream(), media_type='application/x-ndjson',
                             headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='语你一起 · FastAPI + LangChain 本地 RAG')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--index', action='store_true', help='先建立向量库再启动')
    args = parser.parse_args()
    if args.index:
        print('索引已就绪：', rag.ensure_index(), flush=True)
    print(f'语你一起：http://127.0.0.1:{args.port}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)
