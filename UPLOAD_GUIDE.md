# TreadForm GitHub Upload Guide

이 폴더는 GitHub 업로드용으로 정리된 패키지입니다.

## 포함된 것

- `index.html`: GitHub Pages용 웹 프로토타입
- `server/`: FastAPI + MediaPipe 분석 백엔드 코드
- `docs/`: 프로젝트 문서
- `.gitignore`: 업로드하면 안 되는 파일 제외 규칙

## 제외된 것

- `server/venv/`: Python 가상환경
- `server/storage/`: 업로드 영상, 렌더링 영상, CSV 결과물
- `server/.models/`: MediaPipe 모델 파일. 서버 첫 실행 시 자동 다운로드됩니다.
- `__pycache__/`, `.pytest_cache/`: 캐시 파일
- `.env`: 비밀키/환경변수

## 실행 방법

```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

웹 프로토타입은 `index.html`을 GitHub Pages에 올리면 화면 공유용으로 사용할 수 있습니다.
실제 영상 분석은 FastAPI 서버가 별도로 실행되어 있어야 작동합니다.
