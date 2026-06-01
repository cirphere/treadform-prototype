"""
PRD-4 Step 2: 영상 업로드 엔드포인트 테스트.

cv2 로 합성 영상을 만들어 정상 / 거부 케이스를 검증한다. mediapipe 호출은 mock 으로
대체해 빠르게 돈다 (~1초 미만).

TestClient 의 BackgroundTasks 는 with 블록(혹은 응답 직후)에서 동기적으로 실행되므로,
client.post() 가 반환되면 background task 도 이미 끝나있다 — 상태 전이 검증이 단순해짐.

테스트 후 ANALYSIS_STATUS 와 storage/uploads/ 정리는 tmp_path 기반 픽스처 + 명시적
unlink 로 처리. 실제 서버 디렉토리(`server/storage/uploads/`) 에 잔존 파일이 남지 않도록
각 테스트 후 cleanup.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import upload as upload_module
from api.members import MEMBER_HISTORY, MEMBERS
from api.upload import ANALYSIS_STATUS, _UPLOADS_DIR
from main import app
from models.analysis_result import AnalysisResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup_state():
    """매 테스트 종료 시 ANALYSIS_STATUS / MEMBERS / storage 의 잔존 정리."""
    before_aids = set(ANALYSIS_STATUS.keys())
    before_mids = set(MEMBERS.keys())
    yield
    for aid in set(ANALYSIS_STATUS.keys()) - before_aids:
        entry = ANALYSIS_STATUS.pop(aid, None)
        if entry and entry.get("video_path"):
            Path(entry["video_path"]).unlink(missing_ok=True)
    for mid in set(MEMBERS.keys()) - before_mids:
        MEMBERS.pop(mid, None)
        MEMBER_HISTORY.pop(mid, None)


@pytest.fixture(autouse=True)
def _mock_analysis(monkeypatch):
    """
    분석 호출(`run_full_analysis_with_output`) 을 mock 으로 대체.
    실제 mediapipe 호출 없이 background task 흐름만 검증한다.
    개별 테스트가 더 세밀한 mock 을 원하면 monkeypatch 를 다시 덮어쓰면 된다.
    """
    def _fake(video_path: str, output_dir: str) -> dict:
        return {
            "analysis_result": AnalysisResult(
                analysis_id="mock",
                summary={"total_strikes": 0, "fps": 30.0},
                metrics={
                    "knee_flexion": {"status_counts": {}, "per_strike": []},
                    "foot_strike": {"status_counts": {}, "per_strike": []},
                    "overstriding": {"status_counts": {}, "per_strike": []},
                    "vertical_oscillation": {"status": "good", "per_stride": []},
                },
                asymmetry={"is_warning": False},
                confidence="high",
            ),
            "rendered_video_path": f"{output_dir}/renders/mock.mp4",
            "csv_report_path": f"{output_dir}/reports/mock.csv",
            "coach_message": "오늘 러닝은 안정적입니다.",
        }

    monkeypatch.setattr(
        "analyzer.run_full_analysis_with_output", _fake, raising=False
    )


# ---------------------------------------------------------------------------
# 합성 영상 헬퍼
# ---------------------------------------------------------------------------


def _make_video(
    path: Path,
    width: int = 1280,
    height: int = 720,
    fps: int = 60,
    duration_sec: float = 5.5,
) -> Path:
    """cv2 로 단색 mp4 합성. 분석 내용은 무의미하지만 video_validator 통과용."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    assert writer.isOpened(), f"cv2 cannot create {path}"
    n_frames = int(round(fps * duration_sec))
    for i in range(n_frames):
        frame = np.full((height, width, 3), 30, dtype=np.uint8)
        # 프레임 번호 텍스트 (검증 시 의미 없음, just to make distinct frames).
        cv2.putText(
            frame, str(i), (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2,
        )
        writer.write(frame)
    writer.release()
    return path


# ---------------------------------------------------------------------------
# Health / root (Step 1 회귀)
# ---------------------------------------------------------------------------


def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_root_endpoint(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "TreadForm"
    assert body["status"] == "running"


def test_openapi_includes_upload(client: TestClient):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/upload" in paths
    assert "post" in paths["/api/upload"]


# ---------------------------------------------------------------------------
# 업로드: 정상 케이스
# ---------------------------------------------------------------------------


def test_upload_valid_video(client: TestClient, tmp_path: Path):
    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )

    assert r.status_code == 202, r.text
    body = r.json()
    assert "analysis_id" in body
    assert body["status"] == "processing"
    assert body["estimated_seconds"] == 30

    # 상태 등록 확인.
    aid = body["analysis_id"]
    assert aid in ANALYSIS_STATUS
    saved_path = Path(ANALYSIS_STATUS[aid]["video_path"])
    assert saved_path.exists()
    assert saved_path.parent == _UPLOADS_DIR


def test_upload_with_form_fields(client: TestClient, tmp_path: Path):
    """member_id / 키 / 체중 form field 도 함께 전송 가능."""
    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
            data={"member_id": "m-123", "user_height_cm": "175", "user_weight_kg": "68"},
        )

    assert r.status_code == 202
    aid = r.json()["analysis_id"]
    entry = ANALYSIS_STATUS[aid]
    assert entry["member_id"] == "m-123"
    assert entry["user_height_cm"] == 175
    assert entry["user_weight_kg"] == 68


# ---------------------------------------------------------------------------
# 업로드: 거부 케이스
# ---------------------------------------------------------------------------


def test_upload_rejects_invalid_extension(client: TestClient, tmp_path: Path):
    txt = tmp_path / "not_video.txt"
    txt.write_text("hello")
    with txt.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("not_video.txt", f, "text/plain")},
        )

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error_code"] == "INVALID_EXTENSION"
    assert "MP4" in detail["message_ko"]


def test_upload_rejects_low_resolution(client: TestClient, tmp_path: Path):
    video = _make_video(tmp_path / "small.mp4", width=320, height=240)
    with video.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("small.mp4", f, "video/mp4")},
        )

    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "RESOLUTION_TOO_LOW"


def test_upload_rejects_too_short(client: TestClient, tmp_path: Path):
    video = _make_video(tmp_path / "short.mp4", duration_sec=2.0)
    with video.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("short.mp4", f, "video/mp4")},
        )

    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "DURATION_TOO_SHORT"


def test_upload_rejects_portrait(client: TestClient, tmp_path: Path):
    video = _make_video(tmp_path / "portrait.mp4", width=720, height=1280)
    with video.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("portrait.mp4", f, "video/mp4")},
        )

    assert r.status_code == 400
    assert r.json()["detail"]["error_code"] == "PORTRAIT_NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# Background task (Step 3): 분석 호출 흐름
# ---------------------------------------------------------------------------


def test_background_task_completes_on_success(client: TestClient, tmp_path: Path):
    """TestClient 가 BackgroundTasks 를 동기 실행하므로, post() 반환 직후 'completed' 상태."""
    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )
    assert r.status_code == 202
    aid = r.json()["analysis_id"]

    entry = ANALYSIS_STATUS[aid]
    assert entry["status"] == "completed"
    assert "completed_at" in entry
    assert "elapsed_sec" in entry

    result = entry["result"]
    assert result["coach_message"] == "오늘 러닝은 안정적입니다."
    assert result["rendered_video_path"].endswith(".mp4")
    assert result["csv_report_path"].endswith(".csv")
    assert result["analysis_result"].confidence == "high"


def test_background_task_marks_failed_on_exception(
    client: TestClient, tmp_path: Path, monkeypatch
):
    """분석 함수가 예외를 던지면 상태가 'failed' 로 전이되어야 한다."""
    def _boom(video_path: str, output_dir: str):
        raise RuntimeError("simulated mediapipe crash")

    monkeypatch.setattr(
        "analyzer.run_full_analysis_with_output", _boom, raising=False
    )

    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )
    assert r.status_code == 202
    aid = r.json()["analysis_id"]

    entry = ANALYSIS_STATUS[aid]
    assert entry["status"] == "failed"
    assert entry["error_code"] == "ANALYSIS_FAILED"
    assert "분석" in entry["error_message_ko"]


def test_background_task_marks_failed_if_video_missing(client: TestClient, tmp_path: Path):
    """업로드 직후 video_path 가 사라진 비정상 케이스도 'failed' 처리."""
    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )
    aid = r.json()["analysis_id"]

    # 업로드된 파일을 인위적으로 제거하고 task 를 다시 호출 (직접 호출 시뮬레이션).
    Path(ANALYSIS_STATUS[aid]["video_path"]).unlink()
    upload_module._run_analysis_task(aid)

    entry = ANALYSIS_STATUS[aid]
    assert entry["status"] == "failed"
    assert entry["error_code"] == "VIDEO_NOT_FOUND"


def test_rejected_upload_does_not_leave_file(client: TestClient, tmp_path: Path):
    """거부된 영상은 storage/uploads/ 에 잔존하면 안 된다."""
    before = set(_UPLOADS_DIR.glob("*.mp4"))
    video = _make_video(tmp_path / "small.mp4", width=320, height=240)
    with video.open("rb") as f:
        r = client.post(
            "/api/upload",
            files={"video": ("small.mp4", f, "video/mp4")},
        )
    assert r.status_code == 400
    after = set(_UPLOADS_DIR.glob("*.mp4"))
    assert after == before, f"디스크 누수: {after - before}"


# ---------------------------------------------------------------------------
# GET /api/analysis/{id} (Step 4)
# ---------------------------------------------------------------------------


def test_get_analysis_not_found(client: TestClient):
    r = client.get("/api/analysis/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "ANALYSIS_NOT_FOUND"


def test_get_analysis_completed_after_upload(client: TestClient, tmp_path: Path):
    """TestClient 의 background task 동기 실행 덕분에 업로드 직후 completed 조회 가능."""
    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        upload_r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )
    aid = upload_r.json()["analysis_id"]

    r = client.get(f"/api/analysis/{aid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["coach_message"] == "오늘 러닝은 안정적입니다."
    # 정적 URL 변환 검증.
    assert body["rendered_video_url"].startswith("/storage/renders/")
    assert body["rendered_video_url"].endswith(".mp4")
    assert body["csv_report_url"].startswith("/storage/reports/")
    assert body["csv_report_url"].endswith(".csv")
    # AnalysisResult Pydantic 직렬화.
    assert body["analysis_result"]["confidence"] == "high"
    assert "metrics" in body["analysis_result"]


def test_get_analysis_processing_state(client: TestClient):
    """ANALYSIS_STATUS 에 processing 상태만 수동 등록 → 200 + processing 응답."""
    aid = "manual-processing-id"
    ANALYSIS_STATUS[aid] = {
        "status": "processing",
        "video_path": "irrelevant.mp4",
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        r = client.get(f"/api/analysis/{aid}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "processing"
        assert body["analysis_id"] == aid
        assert "estimated_seconds_remaining" in body
        assert "elapsed_sec" in body
    finally:
        ANALYSIS_STATUS.pop(aid, None)


def test_get_analysis_failed_state(client: TestClient, tmp_path: Path, monkeypatch):
    def _boom(video_path: str, output_dir: str):
        raise RuntimeError("simulated mediapipe crash")
    monkeypatch.setattr(
        "analyzer.run_full_analysis_with_output", _boom, raising=False
    )

    video_path = _make_video(tmp_path / "ok.mp4")
    with video_path.open("rb") as f:
        upload_r = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
        )
    aid = upload_r.json()["analysis_id"]

    r = client.get(f"/api/analysis/{aid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "ANALYSIS_FAILED"
    assert "분석" in body["error_message_ko"]


# ---------------------------------------------------------------------------
# Members (Step 5): 회원 / 트레이너 모드
# ---------------------------------------------------------------------------


def test_create_member(client: TestClient):
    r = client.post(
        "/api/members",
        json={"name": "홍길동", "trainer_id": "t-1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "홍길동"
    assert body["trainer_id"] == "t-1"
    assert "member_id" in body
    assert body["member_id"] in MEMBERS
    assert MEMBER_HISTORY[body["member_id"]] == []


def test_create_member_rejects_blank_name(client: TestClient):
    r = client.post(
        "/api/members",
        json={"name": "", "trainer_id": "t-1"},
    )
    assert r.status_code == 422  # Pydantic min_length=1


def test_list_members_by_trainer(client: TestClient):
    client.post("/api/members", json={"name": "A", "trainer_id": "t-1"})
    client.post("/api/members", json={"name": "B", "trainer_id": "t-1"})
    client.post("/api/members", json={"name": "C", "trainer_id": "t-2"})

    r = client.get("/api/members", params={"trainer_id": "t-1"})
    assert r.status_code == 200
    names = sorted(m["name"] for m in r.json())
    assert names == ["A", "B"]


def test_list_members_requires_trainer_id(client: TestClient):
    r = client.get("/api/members")
    assert r.status_code == 422  # trainer_id 누락


def test_get_member_not_found(client: TestClient):
    r = client.get("/api/members/no-such-id")
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "MEMBER_NOT_FOUND"


def test_get_member_history_empty(client: TestClient):
    mr = client.post("/api/members", json={"name": "홍길동", "trainer_id": "t-1"})
    mid = mr.json()["member_id"]

    r = client.get(f"/api/members/{mid}/history")
    assert r.status_code == 200
    body = r.json()
    assert body["member_id"] == mid
    assert body["history"] == []


def test_member_history_after_upload(client: TestClient, tmp_path: Path):
    """member_id 와 함께 업로드한 분석 결과가 회원 히스토리에 자동 등록되어야 한다."""
    mr = client.post("/api/members", json={"name": "홍길동", "trainer_id": "t-1"})
    mid = mr.json()["member_id"]

    video = _make_video(tmp_path / "ok.mp4")
    with video.open("rb") as f:
        up = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
            data={"member_id": mid},
        )
    assert up.status_code == 202
    aid = up.json()["analysis_id"]

    # TestClient 의 background task 가 동기 실행 → 이 시점에 history 등록 완료.
    r = client.get(f"/api/members/{mid}/history")
    assert r.status_code == 200
    body = r.json()
    assert len(body["history"]) == 1
    item = body["history"][0]
    assert item["analysis_id"] == aid
    assert item["confidence"] == "high"
    assert "summary" in item


def test_member_history_404_for_unknown_member(client: TestClient):
    r = client.get("/api/members/no-such-id/history")
    assert r.status_code == 404


def test_save_to_unknown_member_history_is_safe(client: TestClient, tmp_path: Path):
    """잘못된 member_id 로 업로드해도 분석은 진행되고, history 에 누수도 없어야 한다."""
    video = _make_video(tmp_path / "ok.mp4")
    with video.open("rb") as f:
        up = client.post(
            "/api/upload",
            files={"video": ("ok.mp4", f, "video/mp4")},
            data={"member_id": "non-existent-member"},
        )
    assert up.status_code == 202
    aid = up.json()["analysis_id"]
    assert ANALYSIS_STATUS[aid]["status"] == "completed"
    # 등록되지 않은 회원에 대해서는 history dict 가 새로 만들어지면 안 된다.
    assert "non-existent-member" not in MEMBER_HISTORY


def test_get_analysis_static_url_outside_storage_is_none(client: TestClient):
    """rendered_video_path 가 storage 밖이면 URL 변환은 None."""
    aid = "external-path-id"
    ANALYSIS_STATUS[aid] = {
        "status": "completed",
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": 1.0,
        "result": {
            "analysis_result": None,
            "rendered_video_path": "C:/elsewhere/foo.mp4",
            "csv_report_path": "C:/elsewhere/foo.csv",
            "coach_message": "test",
        },
    }
    try:
        r = client.get(f"/api/analysis/{aid}")
        assert r.status_code == 200
        body = r.json()
        assert body["rendered_video_url"] is None
        assert body["csv_report_url"] is None
    finally:
        ANALYSIS_STATUS.pop(aid, None)
