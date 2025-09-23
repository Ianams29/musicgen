import os, uuid, time, threading, subprocess
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, List
from music21 import converter, note, chord, stream

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import replicate

# ───── env ──────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

app = Flask(__name__, static_url_path="/static")
CORS(app, resources={r"/api/*": {"origins": "*"}})

REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
MODEL_SLUG = os.getenv("REPLICATE_MODEL", "meta/musicgen")
client = replicate.Client(api_token=REPLICATE_TOKEN) if REPLICATE_TOKEN else None

# ───── in-memory tasks ──────────────────────────────────────────────
TASKS: Dict[str, Dict[str, Any]] = {}

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
        raise RuntimeError("No Replicate token loaded from .env")
    out = client.run(MODEL_SLUG, input=input_dict)
    url = _extract_audio_url(out)
    if not url:
        if isinstance(out, dict) and isinstance(out.get("output"), str):
            return out["output"]
        if isinstance(out, list) and out and isinstance(out[0], str):
            return out[0]
        raise RuntimeError(f"Replicate returned no audio URL. raw={out}")
    return url

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

# PDF 악보 처리 및 음악 생성 API 엔드포인트
@app.route('/api/process-score', methods=['POST'])
def process_score():
    if 'score' not in request.files:
        return jsonify({'message': '악보 파일이 없습니다.'}), 400
    
    file = request.files['score']

    if file.filename == '':
        return jsonify({'message': '파일이 선택되지 않았습니다.'}), 400

    if file and file.filename.endswith('.pdf'):
        # --- 1. 경로 설정 ---
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        upload_folder = os.path.join(backend_dir, 'temp_scores')
        os.makedirs(upload_folder, exist_ok=True)
        
        unique_filename = str(uuid.uuid4())
        pdf_path = os.path.join(upload_folder, f"{unique_filename}.pdf")
        file.save(pdf_path)

        # --- 2. Audiveris 실행 경로 설정 ---
        audiveris_folder_name = 'app-5.7.1'
        audiveris_lib_path = os.path.join(backend_dir, audiveris_folder_name, 'lib', '*')
        main_class = 'org.audiveris.omr.Main'

        try:
            # --- 3. Audiveris 실행 (올바른 옵션으로 수정!) ---
            print(f"Audiveris 실행 시작: {pdf_path}")
            
            result = subprocess.run(
                [
                    'java',
                    '--enable-preview',  # Java 프리뷰 기능 활성화
                    '-cp', audiveris_lib_path,
                    '-Djava.awt.headless=true',
                    '-Xmx2g',           # 메모리를 2GB로 증가
                    '-Duser.language=en',  # 언어를 영어로 설정
                    '-Duser.country=US',
                    main_class,
                    '-batch',           # GUI 없이 실행
                    '-export',          # MusicXML 내보내기
                    '-output', upload_folder,  # 출력 폴더 지정
                    pdf_path           # 입력 파일
                ],
                capture_output=True,
                text=True,
                encoding='utf-8',   # UTF-8 인코딩 사용
                timeout=180         # 타임아웃을 3분으로 증가
            )

            print("Audiveris 실행 완료")

            if result.returncode != 0:
                print("----- Audiveris Stderr -----")
                print(result.stderr)
                print("----- Audiveris Stdout -----")
                print(result.stdout)
                
                # OCR 언어 경고는 무시하고 계속 진행
                if "UnsupportedClassVersionError" in result.stderr or "Preview features" in result.stderr:
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
                elif "No installed OCR languages" in result.stdout:
                    print("OCR 언어 패키지가 없지만 악보 인식은 계속 진행합니다.")
                else:
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

            # 4. 변환된 파일 이름 찾기
            print(f"출력 폴더 내용 확인: {os.listdir(upload_folder)}")
            
            base_pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
            
            # 가능한 출력 파일 형식들 확인 (.mxl 우선)
            possible_extensions = ['.mxl', '.xml', '.musicxml']
            music_file_path = None
            
            for ext in possible_extensions:
                potential_path = os.path.join(upload_folder, f"{base_pdf_name}{ext}")
                if os.path.exists(potential_path):
                    music_file_path = potential_path
                    print(f"변환된 파일 발견: {music_file_path}")
                    break
            
            # 직접적인 파일명으로 찾을 수 없으면 폴더에서 검색
            if not music_file_path:
                for file in os.listdir(upload_folder):
                    if any(file.endswith(ext) for ext in possible_extensions) and file != os.path.basename(pdf_path):
                        music_file_path = os.path.join(upload_folder, file)
                        print(f"폴더 검색으로 발견된 파일: {music_file_path}")
                        break
            
            if not music_file_path or not os.path.exists(music_file_path):
                raise FileNotFoundError("MusicXML 파일이 변환 후 생성되지 않았습니다.")

        except subprocess.TimeoutExpired:
            print("!!! Audiveris 실행 시간 초과 !!!")
            return jsonify({'message': '악보 변환 작업이 너무 오래 걸려 중단되었습니다.'}), 500
        except subprocess.CalledProcessError as e:
            return jsonify({'message': 'PDF를 MusicXML로 변환하는데 실패했습니다.'}), 500
        except FileNotFoundError as e:
            print(f"파일을 찾을 수 없습니다: {e}")
            return jsonify({'message': '변환된 MusicXML 파일을 찾을 수 없습니다.'}), 500

        # --- 5. MusicXML 파싱 및 음악 생성 ---
        try:
            print(f"Music21로 파일 파싱 시작: {music_file_path}")
            score = converter.parse(music_file_path)  # Music21은 MXL 파일을 직접 처리 가능
            
            # 악보에서 음표 추출
            notes_to_process = score.flat.notesAndRests[:12]  # 더 많은 음표 사용
            prompt_notes = []
            
            for element in notes_to_process:
                if isinstance(element, note.Note):
                    prompt_notes.append(str(element.pitch))
                elif isinstance(element, chord.Chord):
                    prompt_notes.append('.'.join(str(p) for p in element.pitches))
            
            # 악보 정보를 바탕으로 프롬프트 생성
            music_prompt = ' '.join(prompt_notes[:8])  # 처음 8개 음표만 사용
            if not music_prompt:
                music_prompt = "classical piano melody"
            else:
                music_prompt = f"classical music with notes: {music_prompt}"
            
            print(f"생성된 음악 프롬프트: {music_prompt}")

        except Exception as e:
            print(f"Music21 파싱 오류: {e}")
            print(f"기본 프롬프트로 대체합니다.")
            music_prompt = "gentle classical piano music"

        try:
            # 음악 생성을 위한 태스크 ID 생성
            task_id = uuid.uuid4().hex
            _set_task_status(task_id, "queued")
            
            # 음악 생성 워커 시작
            threading.Thread(
                target=worker_generate,
                args=(task_id, music_prompt, [], [], 10, None),
                daemon=True
            ).start()
            
            # 임시 파일 정리
            try:
                os.remove(pdf_path)
                if music_file_path and os.path.exists(music_file_path):
                    os.remove(music_file_path)
                # 로그 파일도 정리
                log_files = [f for f in os.listdir(upload_folder) if f.endswith('.log')]
                for log_file in log_files:
                    try:
                        os.remove(os.path.join(upload_folder, log_file))
                    except:
                        pass
                # OMR 파일도 정리
                omr_files = [f for f in os.listdir(upload_folder) if f.endswith('.omr')]
                for omr_file in omr_files:
                    try:
                        os.remove(os.path.join(upload_folder, omr_file))
                    except:
                        pass
            except Exception as cleanup_error:
                print(f"파일 정리 중 오류: {cleanup_error}")
            
            return jsonify({'taskId': task_id})

        except Exception as e:
            print(f"음악 생성 오류: {e}")
            return jsonify({'message': '음악 생성에 실패했습니다.'}), 500

    return jsonify({'message': '잘못된 파일 형식입니다.'}), 400

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

if __name__ == "__main__":
    # 프런트 기본값과 맞춰 5000포트
    app.run(host="127.0.0.1", port=5000, debug=True)