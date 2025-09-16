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
        audiveris_dist_path = os.path.join(backend_dir, audiveris_folder_name)
        audiveris_bin_path = os.path.join(audiveris_dist_path, 'bin')
        audiveris_executable = os.path.join(audiveris_bin_path, 'Audiveris.bat')

        if not os.path.isfile(audiveris_executable):
            return jsonify({'message': f"Audiveris 실행 파일을 찾을 수 없습니다: {audiveris_executable}"}), 500

        try:
            # --- 3. Audiveris 공식 실행 파일 호출 (메모리 및 시간 제한 추가) ---
            print(f"Audiveris 실행 시작: {pdf_path}")
            
            # Popen을 사용하여 프로세스를 시작하고, communicate로 시간제한을 겁니다.
            process = subprocess.Popen(
                [
                    audiveris_executable,
                    '-batch',
                    '-input', pdf_path,
                    '-output', upload_folder,
                    '-export',
                    # 자바에 최대 1GB 메모리를 할당하는 옵션 추가
                    '-J-Xmx1g' 
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='cp949',
                shell=True
            )
            
            # 2분 (120초) 안에 끝나지 않으면 TimeoutExpired 오류를 발생시킴
            stdout, stderr = process.communicate(timeout=120)

            print("Audiveris 실행 완료")

            if process.returncode != 0:
                print("----- Audiveris Stderr -----")
                print(stderr)
                print("----- Audiveris Stdout -----")
                print(stdout)
                raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)

            # 4. 변환된 파일 이름 찾기
            base_pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
            mxl_path = os.path.join(upload_folder, f"{base_pdf_name}.mxl")
            xml_path = os.path.join(upload_folder, f"{unique_filename}.xml")

            if os.path.exists(mxl_path):
                os.rename(mxl_path, xml_path)
            elif not os.path.exists(xml_path):
                raise FileNotFoundError("MusicXML 파일이 변환 후 생성되지 않았습니다.")

        except subprocess.TimeoutExpired:
            print("!!! Audiveris 실행 시간 초과 !!!")
            process.kill() # 프로세스 강제 종료
            return jsonify({'message': '악보 변환 작업이 너무 오래 걸려 중단되었습니다.'}), 500
        except subprocess.CalledProcessError as e:
            print("----- Audiveris Stderr -----")
            print(e.stderr)
            print("----- Audiveris Stdout -----")
            print(e.stdout)
            return jsonify({'message': 'PDF를 MusicXML로 변환하는데 실패했습니다.'}), 500
        except FileNotFoundError as e:
            print(f"파일을 찾을 수 없습니다: {e}")
            return jsonify({'message': '변환된 MusicXML 파일을 찾을 수 없습니다.'}), 500

        # --- (이하 MusicXML 파싱 및 음악 생성 로직은 이전과 동일합니다) ---
        try:
            score = converter.parse(xml_path)
            notes_to_process = score.flat.notesAndRests[:8] # 프롬프트 정확도를 위해 8개 음표로 늘림
            prompt_notes = []
            for element in notes_to_process:
                if isinstance(element, note.Note):
                    prompt_notes.append(str(element.pitch))
                elif isinstance(element, chord.Chord):
                    prompt_notes.append('.'.join(str(p) for p in element.pitches))
            
            music_prompt = ' '.join(prompt_notes)
            if not music_prompt:
                music_prompt = "classical piano"

        except Exception as e:
            print(f"Music21 오류: {e}")
            music_prompt = "gentle classical music"

        try:
            music_url = generate_music(music_prompt, 10) 
            
            os.remove(pdf_path)
            if os.path.exists(xml_path):
                os.remove(xml_path)
            
            return jsonify({'musicUrl': music_url})

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
