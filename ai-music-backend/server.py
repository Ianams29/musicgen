import os, uuid, time, threading
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, List
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import replicate

# ───── env ──────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

app = Flask(__name__, static_url_path="/static")
CORS(app, resources={r"/api/*": {"origins": "*"}})

PAPAGO_CLIENT_ID = os.getenv("PAPAGO_CLIENT_ID")
PAPAGO_CLIENT_SECRET = os.getenv("PAPAGO_CLIENT_SECRET")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
MODEL_SLUG = os.getenv("REPLICATE_MODEL", "meta/musicgen")

print("=== Replicate 디버깅 ===")
print(f"REPLICATE_TOKEN: {'***' + REPLICATE_TOKEN[-8:] if REPLICATE_TOKEN else 'NOT SET'}")
print(f"MODEL_SLUG: {MODEL_SLUG}")

client = None
if REPLICATE_TOKEN:
    try:
        client = replicate.Client(api_token=REPLICATE_TOKEN)
        print("Replicate 클라이언트 생성 성공")
        
        # 토큰 유효성 테스트
        try:
            # 간단한 API 호출로 토큰 검증
            models = client.models.list()
            print("Replicate API 토큰 유효성 확인됨")
        except Exception as token_error:
            print(f"Replicate 토큰 유효성 검증 실패: {token_error}")
            
    except Exception as e:
        print(f"Replicate 클라이언트 생성 실패: {e}")
        client = None
else:
    print("REPLICATE_API_TOKEN이 설정되지 않음")

print(f"최종 클라이언트 상태: {'생성됨' if client else '생성 실패'}")
print("=======================")

# ───── in-memory tasks ──────────────────────────────────────────────
TASKS: Dict[str, Dict[str, Any]] = {}

@app.route("/api/translate", methods=["POST"])
def translate_text():
    """
    NCP 기반 Papago Text Translation API를 사용한 번역 기능
    """
    # 환경변수 검증
    if not PAPAGO_CLIENT_ID or not PAPAGO_CLIENT_SECRET:
        return jsonify({"error": "API 키가 설정되지 않았습니다"}), 500
    
    print(f"=== PAPAGO API 디버그 ===")
    print(f"PAPAGO_CLIENT_ID: {PAPAGO_CLIENT_ID[:8]}...")
    print(f"PAPAGO_CLIENT_SECRET: {'***' + PAPAGO_CLIENT_SECRET[-4:] if len(PAPAGO_CLIENT_SECRET) > 4 else '***'}")
    
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "").strip()
    source = data.get("source", "ko")
    target = data.get("target", "en")

    print(f"Request data: text='{text}', source='{source}', target='{target}'")

    # 입력값 검증
    if not text or not target:
        return jsonify({"error": "텍스트와 목표 언어는 필수입니다"}), 400
    
    if len(text) > 5000:  # Papago 텍스트 길이 제한
        return jsonify({"error": "텍스트가 너무 깁니다 (최대 5000자)"}), 400

    # 지원되는 언어 코드 확인
    supported_langs = ['ko', 'en', 'ja', 'zh-CN', 'zh-TW', 'vi', 'id', 'th', 'de', 'ru', 'es', 'it', 'fr']
    if source not in supported_langs or target not in supported_langs:
        return jsonify({"error": f"지원되지 않는 언어입니다. 지원 언어: {supported_langs}"}), 400

    url = "https://papago.apigw.ntruss.com/nmt/v1/translation"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": PAPAGO_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": PAPAGO_CLIENT_SECRET,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    # URL 인코딩된 데이터로 전송
    import urllib.parse
    payload = urllib.parse.urlencode({
        "source": source,
        "target": target,
        "text": text
    })

    print(f"Request URL: {url}")
    print(f"Payload length: {len(payload)}")

    try:
        response = requests.post(
            url, 
            headers=headers, 
            data=payload,
            timeout=30  # 타임아웃 설정
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 403:
            print("403 오류 - API 키 또는 서비스 설정을 확인하세요")
            return jsonify({
                "error": "API 인증 실패. NCP 콘솔에서 Papago 서비스 활성화 및 API 키를 확인하세요"
            }), 403
        
        if response.status_code == 429:
            return jsonify({"error": "API 호출 한도를 초과했습니다"}), 429
        
        response.raise_for_status()
        result = response.json()
        
        # 응답 구조 확인
        if "message" not in result or "result" not in result["message"]:
            print(f"예상치 못한 응답 구조: {result}")
            return jsonify({"error": "예상치 못한 API 응답"}), 500
        
        message_result = result["message"]["result"]
        translated_text = message_result.get("translatedText", "")
        
        return jsonify({
            "success": True,
            "source": text,
            "translated": translated_text,
            "sourceLang": message_result.get("srcLangType", source),
            "targetLang": message_result.get("tarLangType", target)
        })
        
    except requests.exceptions.Timeout:
        return jsonify({"error": "API 요청 시간 초과"}), 408
    except requests.exceptions.RequestException as e:
        print(f"Request Exception: {str(e)}")
        return jsonify({"error": f"API 요청 실패: {str(e)}"}), 500
    except ValueError as e:  # JSON 디코딩 오류
        print(f"JSON decode error: {str(e)}")
        print(f"Response content: {response.text}")
        return jsonify({"error": "API 응답 파싱 실패"}), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"예상치 못한 오류: {str(e)}"}), 500
    
def _set_task_status(task_id: str, status: str, **kwargs):
    TASKS[task_id] = {"status": status, **kwargs}

def mk_result(audio_url: str, title="AI_Track",
              genres: Optional[List[str]] = None,
              moods: Optional[List[str]] = None,
              duration: int = 10, kind: str = "generated"):
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "genres": genres or [],
        "moods": moods or [],
        "duration": duration,
        "audioUrl": audio_url,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": kind,
    }

def _extract_audio_url(output: Any) -> Optional[str]:
    def as_url(v: Any) -> Optional[str]:
        if isinstance(v, str) and v.startswith("http"): return v
        try:
            u = getattr(v, "url", None)
            if isinstance(u, str) and u.startswith("http"): return u
        except Exception:
            pass
        return None

    u = as_url(output)
    if u: return u
    if isinstance(output, (list, tuple)):
        for item in output:
            u = as_url(item)
            if u: return u
    if isinstance(output, dict):
        for key in ("audioUrl", "audio_url", "url", "audio", "output"):
            if key in output:
                u = as_url(output[key])
                if u: return u
        files = output.get("files")
        if isinstance(files, list):
            for f in files:
                if isinstance(f, dict):
                    u = as_url(f.get("url"))
                    if u: return u
                else:
                    u = as_url(f)
                    if u: return u
        for parent in ("result", "data", "prediction"):
            if parent in output:
                u = _extract_audio_url(output[parent])
                if u: return u
    return None

def _run_replicate(input_dict: Dict[str, Any]) -> str:
    if not client:
        raise RuntimeError("Replicate 클라이언트가 초기화되지 않았습니다. REPLICATE_API_TOKEN을 확인하세요.")
    
    print(f"Replicate 실행 - 모델: {MODEL_SLUG}")
    print(f"입력 파라미터: {input_dict}")
    
    try:
        out = client.run(MODEL_SLUG, input=input_dict)
        print(f"Replicate 출력: {out}")
        
        url = _extract_audio_url(out)
        if not url:
            if isinstance(out, dict) and isinstance(out.get("output"), str):
                return out["output"]
            if isinstance(out, list) and out and isinstance(out[0], str):
                return out[0]
            raise RuntimeError(f"Replicate에서 오디오 URL을 추출할 수 없습니다. 원시 출력: {out}")
        return url
        
    except Exception as e:
        print(f"Replicate API 호출 중 오류: {e}")
        raise

# ───── worker ───────────────────────────────────────────────────────
def worker_generate(task_id: str, prompt: str, genres, moods, duration: int,
                    tmp_path: Optional[str]):
    """
    - prompt + (선택) input_audio 로 생성
    - 파일은 BytesIO로 읽어 전달해 'seek of closed file' 방지
    """
    try:
        _set_task_status(task_id, "running")

        inputs: Dict[str, Any] = {
            "prompt": prompt or "instrumental background music",
            "duration": duration,
            "output_format": "mp3",
            "normalization_strategy": "peak",
        }

        if tmp_path:
            with open(tmp_path, "rb") as f:
                data = f.read()
            bio = BytesIO(data)          # 메모리 스트림(닫히지 않음)
            # 일부 라이브러리는 name 확장자로 MIME 판단하므로 설정
            setattr(bio, "name", os.path.basename(tmp_path))
            bio.seek(0)
            inputs["input_audio"] = bio
            inputs["continuation"] = False

        audio_url = _run_replicate(inputs)
        res = mk_result(audio_url, "AI_Generated_Track", genres, moods, duration, "generated")
        _set_task_status(task_id, "succeeded", result=res, audioUrl=res["audioUrl"])
    except Exception as e:
        # 디버그에 바로 보이도록 로그
        print("[worker_generate] ERROR:", repr(e))
        _set_task_status(task_id, "failed", error=str(e))
    finally:
        if tmp_path:
            try: os.remove(tmp_path)
            except Exception: pass

# ───── endpoints ────────────────────────────────────────────────────
@app.route("/api/music/generate", methods=["POST"])
def generate_music():
    """
    JSON + multipart/form-data 둘 다 지원
    - JSON: {"description","genres","moods","duration"}
    - multipart: fields(description, genres(json), moods(json), duration, file=<audio>)
    """
    ct = (request.content_type or "")
    is_multipart = ct.startswith("multipart/form-data")

    if is_multipart:
        data = request.form
        up = request.files.get("file")
    else:
        data = request.get_json(force=True, silent=True) or {}
        up = None

    import json
    def as_list(v):
        if v is None: return []
        if isinstance(v, list): return v
        if isinstance(v, str):
            try: return json.loads(v)
            except Exception: return [v] if v else []
        return []

    prompt   = data.get("description") or "instrumental background music"
    genres   = as_list(data.get("genres"))
    moods    = as_list(data.get("moods"))
    try:
        duration = int(data.get("duration") or 10)
    except Exception:
        duration = 10

    tmp_path = None
    if up:
        os.makedirs("tmp", exist_ok=True)
        safe = secure_filename(up.filename or f"audio_{uuid.uuid4().hex}.wav")
        tmp_path = os.path.join("tmp", f"{uuid.uuid4().hex}_{safe}")
        up.save(tmp_path)

    task_id = uuid.uuid4().hex
    _set_task_status(task_id, "queued")
    threading.Thread(
        target=worker_generate,
        args=(task_id, prompt, genres, moods, duration, tmp_path),
        daemon=True
    ).start()
    return jsonify({"taskId": task_id})

@app.route("/api/music/task/status", methods=["GET"])
def task_status():
    task_id = request.args.get("task_id") or request.args.get("taskId")
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"status": "failed", "error": "Unknown task"}), 404
    return jsonify({
        "taskId": task_id,
        "status": task.get("status"),
        "audioUrl": task.get("audioUrl"),
        "result": task.get("result"),
        "error": task.get("error"),
    })

@app.route("/api/test", methods=["GET"])
def test_api():
    """API 키 설정 상태 확인용 테스트 엔드포인트"""
    return jsonify({
        "server_status": "running",
        "papago_client_id_exists": bool(PAPAGO_CLIENT_ID),
        "papago_client_secret_exists": bool(PAPAGO_CLIENT_SECRET),
        "papago_client_id_length": len(PAPAGO_CLIENT_ID) if PAPAGO_CLIENT_ID else 0,
        "papago_client_secret_length": len(PAPAGO_CLIENT_SECRET) if PAPAGO_CLIENT_SECRET else 0
    })

if __name__ == "__main__":
    # 프런트 기본값과 맞춰 5000포트
    print("Flask 서버를 시작합니다...")
    print("서버 주소: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)