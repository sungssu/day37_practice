# day37_practice.py
# 주제: 캠퍼스 시설 안내 음성 도우미
#
# [실습 목표]
# 1) 녹음 → STT → 응답 생성 → TTS → 재생' 흐름을 하나의 실제 서비스 시나리오로 확장
# 2) Git Repository 생성
# 3) Render에 코드 배포
# 4) Neon에 데이터베이스 생성
# 5) End-point에서 테스트
#
# [완성 화면의 동작]
# 1) Streamlit에서 마이크로 음성을 녹음합니다.
# 2) 데모 STT 또는 실제 faster-whisper를 선택합니다.
# 3) 안내할 시설(도서관, 학생식당, 취업지원센터, 행정실)에 대한 한국어 질문을 인식합니다.
# 4) 사용자의 질문에서 시설명을 찾아 운영 안내를 반환합니다.
# 5) 생성한 답변을 비프음 데모 또는 실제 edge-tts로 출력합니다.
# 6) STT/응답/TTS/총 처리시간을 측정하고 막대그래프를 표시합니다.
# 7) 개인정보를 제외한 실행 이력을 JSONL에 저장합니다.
# 8) 최근 처리 이력을 표로 확인합니다.
#
# [파일]
# day37_practice.py: 통합 실습 완성 코드
# voice_runs_campus.jsonl: 실행 시 자동으로 생성되는 이력
#
# [구현 절차]
# 1) day37_ex.py에서 입력, 모델 호출, 메타데이터 저장 흐름을 확인합니다.
# 2) 시설 정보는 파이썬 딕셔너리로 정의합니다(운영시간은 연습용 예시).
# 3) 답변 생성 함수를 만들고 시설명이 들어간 질문에 대응합니다.
# 4) 인식되지 않은 질문은 선택 가능한 시설 목록을 안내합니다.
# 5) 음성 녹음 여부 및 10MBytes 용량 제한을 검사합니다.
# 6) 모델 실행 중 오류가 발생하면 원인을 표시하되 앱이 중단되지 않도록 합니다.
# 7) 각 단계 수행 시간을 perf_counter()로 측정합니다.
# 8) 요청 ID, 시각, 사용 모델, 오류 여부, 처리시간을 JSONL로 기록합니다.
# 9) Streamlit에서 음성 결과, 구간별 소요시간, 최근 이력을 확인합니다.
#
# [확인 시나리오]
# 예시 문장
# '도서관 운영시간 알려줘' → 도서관 안내
# '학생식당 어디야?' → 학생식당 안내
# '취업지원센터 이용하고 싶어' → 취업지원센터 안내
# '운동장에 대해서 알려줘' → 안내 가능한 시설 목록 표시
# 녹음을 하지 않고 실행 → 오류 메시지, 처리하지 않음
# 실제 TTS 사용 → 문장을 읽는 mp3 생성(인터넷 연결 필요)
# 실제 STT 사용 → 입력 WAV를 음성 인식(최초 모델 다운로드 필요)


# day37_practice.py
# day37_practice.py
import os
import time
import json
import uuid
import hashlib
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # .env 로딩

# 입력 파일 최대 크기를 10Mbytes로 제한 (정상 수정)
MAX_BYTES = 10 * 1024 * 1024

# 실행이력을 저장할 jsonl파일 경로
LOG_PATH = Path(__file__).with_name('voice_runs_campus.jsonl')

# 시설 정보 딕셔너리
FACILITIES = {
    "도서관": "도서관은 본관 옆 건물이며 평일 9시부터 18시까지 운영합니다.",
    "학생식당": "학생식당은 학생회관 1층이며 11시부터 14시까지 운영합니다.",
    "취업지원센터": "취업지원센터는 학생회관 2층이며 취업 상담을 제공합니다.",
    "행정실": "행정실은 본관 1층이며 각종 증명서 발급을 안내합니다.",
}


# 답변 생성 함수
def get_answer(text):
    for place, announcement in FACILITIES.items():
        if place in text:
            return announcement
    return '등록되지 않은 시설입니다. 도서관, 학생식당, 취업지원센터, 행정실 중에서 선택해 주세요.'


# 음성 녹음 여부 및 용량 제한 검사
def check_audio(audio_file):
    if audio_file is None:
        return False, '녹음된 음성이 없습니다.'

    if hasattr(audio_file, 'size') and audio_file.size > MAX_BYTES:
        return False, '용량이 너무 큽니다. (10MB 제한)'

    return True, '정상 음성입니다.'


# Edge TTS로 한국어 음성을 합성하여 MP3 bytes로 반환하는 함수
async def generate_tts_mp3(text, voice):
    import edge_tts
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        mp3_path = Path(f.name)
    try:
        await edge_tts.Communicate(text=text, voice=voice).save(str(mp3_path))
        return mp3_path.read_bytes()
    finally:
        mp3_path.unlink(missing_ok=True)


# 비동기 Edge TTS 함수를 동기코드에서 실행하는 함수
def synthesize_speech(text, voice_id):
    mp3_bytes = asyncio.run(generate_tts_mp3(text, voice_id))
    return mp3_bytes, 'audio/mpeg'


# 실행 정보 저장 함수 (JSONL 및 PostgreSQL)
def store_meta(meta):
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False) + '\n')

    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        st.warning('DATABASE_URL이 설정되지 않았습니다.')
        return

    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS voice_runs_campus (
                        request_id TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        status TEXT NOT NULL,
                        stt_ms DOUBLE PRECISION NOT NULL,
                        reply_ms DOUBLE PRECISION NOT NULL,
                        tts_ms DOUBLE PRECISION NOT NULL,
                        total_ms DOUBLE PRECISION NOT NULL,
                        model_version TEXT NOT NULL,
                        voice_id TEXT NOT NULL,
                        audio_sha256 TEXT NOT NULL
                    )
                ''')

                cur.execute('''
                    INSERT INTO voice_runs_campus
                    (request_id, created_at, status, stt_ms, reply_ms,
                     tts_ms, total_ms, model_version, voice_id, audio_sha256)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    meta['request_id'], meta['created_at'], meta['status'],
                    meta['stt_ms'], meta['reply_ms'], meta['tts_ms'],
                    meta['total_ms'], meta['model_version'], meta['voice_id'],
                    meta['audio_sha256']
                ))
    except Exception as e:
        st.warning(f'DB 실행 이력 저장 실패: {type(e).__name__}: {e}')


# 파이프라인
def run_pipeline(audio_file, model_size, voice_id):
    request_id = str(uuid.uuid4())

    audio_bytes_data = audio_file.read() if hasattr(audio_file, 'read') else b"dummy"
    digest = hashlib.sha256(audio_bytes_data).hexdigest()

    marks = {'stt_ms': 0.0, 'reply_ms': 0.0, 'tts_ms': 0.0}
    started = time.perf_counter()

    result = None
    error = None

    try:
        # STT 실행 단계 (실제 faster-whisper 연동)
        t0 = time.perf_counter()

        from faster_whisper import WhisperModel
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(audio_bytes_data)
            tmp_audio_path = tmp_audio.name

        try:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, info = model.transcribe(tmp_audio_path, language="ko")
            text = "".join([segment.text for segment in segments]).strip()
            if not text:
                text = "인식된 음성이 없습니다."
        finally:
            Path(tmp_audio_path).unlink(missing_ok=True)

        marks['stt_ms'] = (time.perf_counter() - t0) * 1000

        # 답변 생성 실행
        t0 = time.perf_counter()
        answer = get_answer(text)
        marks['reply_ms'] = (time.perf_counter() - t0) * 1000

        # TTS 실행
        t0 = time.perf_counter()
        output, mime = synthesize_speech(answer, voice_id)
        marks['tts_ms'] = (time.perf_counter() - t0) * 1000

        result = (text, answer, output, mime)

    except Exception as e:
        error = e

    total_ms = (time.perf_counter() - started) * 1000

    meta = {
        "request_id": request_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if not error else "error",
        "stt_ms": marks['stt_ms'],
        "reply_ms": marks['reply_ms'],
        "tts_ms": marks['tts_ms'],
        "total_ms": total_ms,
        "model_version": f"whisper-{model_size}",
        "voice_id": voice_id,
        "audio_sha256": digest
    }

    store_meta(meta)

    if error:
        raise error

    return result


# Streamlit UI 메인 함수
def main():
    st.set_page_config(
        page_title='캠퍼스 시설 안내 음성 도우미',
        page_icon='🏫',
        layout='centered'
    )

    st.title('🏫 캠퍼스 시설 안내 음성 도우미')
    st.markdown('마이크로 질문을 녹음하시면 캠퍼스 시설 정보를 음성과 텍스트로 안내해 드립니다.')

    with st.form('voice_form'):
        uploaded = st.audio_input('마이크로 한국어 음성을 녹음하세요')

        model_size = st.selectbox(
            'STT 모델',
            ['tiny', 'base', 'small', 'medium'],
            index=1
        )

        voice_id = st.selectbox(
            'TTS 목소리 선택',
            ['ko-KR-SunHiNeural', 'ko-KR-InJoonNeural'],
            index=0
        )

        submitted = st.form_submit_button('실행하기')

        if not submitted:
            return

        if uploaded is None:
            st.error('먼저 음성을 녹음해 주세요.')
            return

        audio = uploaded.getvalue()

        if not audio or len(audio) > MAX_BYTES:
            st.error(f'음성 파일 용량은 {MAX_BYTES / (1024 * 1024):.1f}MB 이하여야 합니다.')
            return

    if submitted:
        st.subheader('🎙️ 녹음된 음성')
        st.audio(uploaded)

        is_valid, msg = check_audio(uploaded)
        if not is_valid:
            st.error(msg)
            return

        with st.spinner('AI 파이프라인 실행 중... (STT ➔ 답변 ➔ TTS)'):
            try:
                text, answer, output, mime = run_pipeline(uploaded, model_size, voice_id)
            except Exception as e:
                st.error(f'오류가 발생했습니다: {e}')
                return

        st.success('처리 완료!')

        st.divider()
        st.subheader('📌 처리 결과')

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('**[STT] 인식된 텍스트**')
            st.info(text)

        with col2:
            st.markdown('**[답변] 시설 안내**')
            st.success(answer)

        st.markdown('**[TTS] 음성 안내 듣기**')
        st.audio(output, format=mime)

        st.divider()
        st.subheader('⏱️ 단계별 소요 시간 (ms)')

        if LOG_PATH.exists():
            with LOG_PATH.open('r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    last_log = json.loads(lines[-1].strip())
                    timing_data = {
                        "STT (ms)": last_log.get('stt_ms', 0),
                        "Reply (ms)": last_log.get('reply_ms', 0),
                        "TTS (ms)": last_log.get('tts_ms', 0)
                    }
                    st.bar_chart(timing_data)

        st.divider()
        st.subheader('📜 최근 실행 이력 (Log)')
        if LOG_PATH.exists():
            logs = []
            with LOG_PATH.open('r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line.strip()))

            if logs:
                st.dataframe(logs[-5:][::-1], use_container_width=True)
            else:
                st.info('아직 기록된 이력이 없습니다.')
        else:
            st.info('생성된 로그 파일이 없습니다.')


if __name__ == '__main__':
    main()