import os, uuid, time, threading, subprocess
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, List
from music21 import converter, note, chord, stream

from flask import Flask, request, jsonify, send_file
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
            bio = BytesIO(data)
            setattr(bio, "name", os.path.basename(tmp_path))
            bio.seek(0)
            inputs["input_audio"] = bio
            inputs["continuation"] = False

        audio_url = _run_replicate(inputs)
        res = mk_result(audio_url, "AI_Generated_Track", genres, moods, duration, "generated")
        _set_task_status(task_id, "succeeded", result=res, audioUrl=res["audioUrl"])
    except Exception as e:
        print("[worker_generate] ERROR:", repr(e))
        _set_task_status(task_id, "failed", error=str(e))
    finally:
        if tmp_path:
            try: os.remove(tmp_path)
            except Exception: pass

# PDF 악보 처리 및 MIDI 파일 생성 API 엔드포인트
@app.route('/api/process-score', methods=['POST'])
def process_score():
    if 'score' not in request.files:
        return jsonify({'message': '악보 파일이 없습니다.'}), 400
    
    uploaded_file = request.files['score']

    if uploaded_file.filename == '':
        return jsonify({'message': '파일이 선택되지 않았습니다.'}), 400

    if uploaded_file and uploaded_file.filename.endswith('.pdf'):
        # --- 1. 경로 설정 ---
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        upload_folder = os.path.join(backend_dir, 'temp_scores')
        midi_folder = os.path.join(backend_dir, 'generated_midi')
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(midi_folder, exist_ok=True)
        
        unique_filename = str(uuid.uuid4())
        pdf_path = os.path.join(upload_folder, f"{unique_filename}.pdf")
        uploaded_file.save(pdf_path)

        # --- 2. Audiveris 실행 경로 설정 ---
        audiveris_jar_path = r"C:\Program Files\Audiveris\app"
        java_executable = r"C:\Program Files\Audiveris\runtime\bin\java"

        try:
            # --- 3. Audiveris 실행 (PDF -> MusicXML) ---
            print(f"Audiveris 실행 시작: {pdf_path}")
            print(f"Audiveris jar 경로: {audiveris_jar_path}")
            
            # app 폴더의 모든 jar 파일을 클래스패스에 추가
            jar_files = []
            for file_name in os.listdir(audiveris_jar_path):
                if file_name.endswith('.jar'):
                    jar_files.append(os.path.join(audiveris_jar_path, file_name))
            
            classpath = ';'.join(jar_files)
            print(f"클래스패스에 {len(jar_files)}개 JAR 파일 추가")
            
            result = subprocess.run(
                [
                    java_executable,
                    '-cp', classpath,
                    '-Djava.awt.headless=true',
                    '-Xmx2g',
                    '-Duser.language=en',
                    '-Duser.country=US',
                    'org.audiveris.omr.Main',
                    '-batch',
                    '-export',
                    '-output', upload_folder,
                    pdf_path
                ],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=180
            )

            print("Audiveris 실행 완료")

            if result.returncode != 0:
                print("----- Audiveris Stderr -----")
                print(result.stderr)
                print("----- Audiveris Stdout -----")
                print(result.stdout)
                
                if "UnsupportedClassVersionError" in result.stderr or "Preview features" in result.stderr:
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
                elif "No installed OCR languages" in result.stdout:
                    print("OCR 언어 패키지가 없지만 악보 인식은 계속 진행합니다.")
                else:
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

            # --- 4. 변환된 MusicXML 파일 찾기 ---
            print(f"출력 폴더 내용 확인: {os.listdir(upload_folder)}")
            
            base_pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
            possible_extensions = ['.mxl', '.xml', '.musicxml']
            music_file_path = None
            
            for ext in possible_extensions:
                potential_path = os.path.join(upload_folder, f"{base_pdf_name}{ext}")
                if os.path.exists(potential_path):
                    music_file_path = potential_path
                    print(f"변환된 파일 발견: {music_file_path}")
                    break
            
            if not music_file_path:
                for file_item in os.listdir(upload_folder):
                    if any(file_item.endswith(ext) for ext in possible_extensions):
                        music_file_path = os.path.join(upload_folder, file_item)
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

        # --- 5. MusicXML -> MIDI 변환 ---
        try:
            print(f"Music21로 파일 파싱 시작: {music_file_path}")
            score = converter.parse(music_file_path)
            
            # MIDI 파일 생성
            midi_filename = f"{unique_filename}.mid"
            midi_path = os.path.join(midi_folder, midi_filename)
            
            print(f"MIDI 파일 생성 중: {midi_path}")
            score.write('midi', fp=midi_path)
            print(f"MIDI 파일 생성 완료: {midi_path}")
            
            # 곡 길이 계산
            duration = int(score.duration.quarterLength / score.metronomeMarkBoundaries()[0][-1].number * 60) if score.metronomeMarkBoundaries() else 180

            # MIDI 파일 URL 생성 (Flask에서 서빙)
            midi_url = f"http://127.0.0.1:5000/api/midi/{midi_filename}"
            
            # 결과 데이터 생성
            result_data = {
                "id": unique_filename,
                "title": f"악보 연주 - {uploaded_file.filename}",
                "audioUrl": midi_url,
                "midiPath": midi_path,
                "genres": ["Classical"],
                "moods": [],
                "duration": duration,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "type": "score-midi"
            }

            print(f"MIDI 파일 준비 완료: {result_data}")

        except Exception as e:
            print(f"MIDI 변환 오류: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'message': f'MIDI 변환 중 오류가 발생했습니다: {str(e)}'}), 500

        finally:
            # 임시 파일 정리
            try:
                os.remove(pdf_path)
                if music_file_path and os.path.exists(music_file_path):
                    os.remove(music_file_path)
                # 로그 및 OMR 파일 정리
                for file_item in os.listdir(upload_folder):
                    if file_item.endswith(('.log', '.omr')):
                        try:
                            os.remove(os.path.join(upload_folder, file_item))
                        except:
                            pass
            except Exception as cleanup_error:
                print(f"파일 정리 중 오류: {cleanup_error}")
        
        return jsonify({
            'success': True,
            'result': result_data
        })

    return jsonify({'message': '잘못된 파일 형식입니다.'}), 400

# MIDI 파일 서빙 엔드포인트
@app.route('/api/midi/<filename>', methods=['GET'])
def serve_midi(filename):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    midi_folder = os.path.join(backend_dir, 'generated_midi')
    midi_path = os.path.join(midi_folder, filename)
    
    if os.path.exists(midi_path):
        return send_file(midi_path, mimetype='audio/midi', as_attachment=False)
    else:
        return jsonify({'message': 'MIDI 파일을 찾을 수 없습니다.'}), 404

# ───── endpoints ────────────────────────────────────────────────────
@app.route("/api/music/generate", methods=["POST"])
def generate_music():
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
    app.run(host="127.0.0.1", port=5000, debug=True)