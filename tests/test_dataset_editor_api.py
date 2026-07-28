from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.application import app


ROOT = Path(__file__).resolve().parents[1]


def make_image(path: Path, color=(220, 80, 80)):
    image = Image.new("RGB", (24, 18), color)
    image.save(path)


def test_dataset_editor_scan_lists_images_and_captions(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("1girl, solo", encoding="utf-8")
    make_image(tmp_path / "beta.jpg", color=(80, 120, 220))

    client = TestClient(app)
    response = client.post("/api/dataset-editor/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["root"] == str(tmp_path.resolve()).replace("\\", "/")
    assert payload["data"]["total"] == 2
    assert payload["data"]["tags"] == [
        {"tag": "1girl", "count": 1},
        {"tag": "solo", "count": 1},
    ]
    assert payload["data"]["categories"] == [
        {"name": "根目录", "value": "", "count": 2}
    ]

    first = payload["data"]["items"][0]
    assert first["name"] == "alpha.png"
    assert first["caption"] == "1girl, solo"
    assert first["tags"] == ["1girl", "solo"]
    assert first["caption_exists"] is True
    assert first["image_url"].startswith("/api/dataset-editor/image?")
    assert "root=" in first["image_url"]
    assert "image=alpha.png" in first["image_url"]

    second = payload["data"]["items"][1]
    assert second["name"] == "beta.jpg"
    assert second["caption"] == ""
    assert second["caption_exists"] is False


def test_dataset_editor_scan_groups_first_level_subfolders(tmp_path):
    char_dir = tmp_path / "10_character"
    style_dir = tmp_path / "20_style"
    char_dir.mkdir()
    style_dir.mkdir()
    make_image(char_dir / "alpha.png")
    make_image(style_dir / "beta.png")

    client = TestClient(app)
    response = client.post("/api/dataset-editor/scan", json={"path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["categories"] == [
        {"name": "10_character", "value": "10_character", "count": 1},
        {"name": "20_style", "value": "20_style", "count": 1},
    ]
    assert data["items"][0]["category"] == "10_character"
    assert data["items"][1]["category"] == "20_style"


def test_dataset_editor_save_caption_creates_txt_caption(tmp_path):
    make_image(tmp_path / "alpha.png")

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/caption",
        json={
            "root": str(tmp_path),
            "image": "alpha.png",
            "caption": "cat ears, smile",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["caption"] == "cat ears, smile"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "cat ears, smile"


def test_dataset_editor_batch_replace_remove_append_and_sort(tmp_path):
    make_image(tmp_path / "alpha.png")
    make_image(tmp_path / "beta.png")
    (tmp_path / "alpha.txt").write_text("solo, 1girl, old tag", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("solo, blue eyes", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png", "beta.png"],
            "append": ["masterpiece"],
            "remove": ["solo"],
            "replace": [{"from": "old tag", "to": "new tag"}],
            "sort": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 2
    assert (tmp_path / "alpha.txt").read_text(
        encoding="utf-8"
    ) == "1girl, masterpiece, new tag"
    assert (tmp_path / "beta.txt").read_text(
        encoding="utf-8"
    ) == "blue eyes, masterpiece"


def test_dataset_editor_batch_cleans_obvious_caption_noise(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text(
        "white_background， 1girl, 1girl; basketball \\(object\\)\nsolo",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png"],
            "clean": True,
            "underscore_to_space": True,
            "strip_escape_chars": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["changed"] == 1
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == (
        "white background, 1girl, basketball (object), solo"
    )


def test_dataset_editor_undo_restores_single_caption_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("original tag", encoding="utf-8")

    client = TestClient(app)
    save = client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "changed tag"},
    )
    assert save.status_code == 200
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "changed tag"

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    payload = undo.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 1
    assert payload["data"]["items"][0]["caption"] == "original tag"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "original tag"


def test_dataset_editor_redo_reapplies_undone_caption_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("original tag", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "changed tag"},
    )
    client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    redo = client.post("/api/dataset-editor/redo", json={"root": str(tmp_path)})

    assert redo.status_code == 200
    payload = redo.json()
    assert payload["status"] == "success"
    assert payload["data"]["changed"] == 1
    assert payload["data"]["items"][0]["caption"] == "changed tag"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "changed tag"


def test_dataset_editor_history_lists_saved_transactions(tmp_path):
    make_image(tmp_path / "alpha.png")
    (tmp_path / "alpha.txt").write_text("before", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "after"},
    )

    history = client.post("/api/dataset-editor/history", json={"root": str(tmp_path)})

    assert history.status_code == 200
    data = history.json()["data"]
    assert data["can_undo"] is True
    assert data["can_redo"] is False
    assert data["changes"][0]["label"] == "保存当前 caption"
    assert data["changes"][0]["items"][0]["before"] == "before"
    assert data["changes"][0]["items"][0]["after"] == "after"


def test_dataset_editor_undo_restores_missing_caption_after_create(tmp_path):
    make_image(tmp_path / "alpha.png")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "alpha.png", "caption": "new tag"},
    )
    assert (tmp_path / "alpha.txt").is_file()

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    assert undo.json()["data"]["items"][0]["caption_exists"] is False
    assert not (tmp_path / "alpha.txt").exists()


def test_dataset_editor_undo_restores_batch_edit(tmp_path):
    make_image(tmp_path / "alpha.png")
    make_image(tmp_path / "beta.png")
    (tmp_path / "alpha.txt").write_text("solo, 1girl", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("solo, blue eyes", encoding="utf-8")

    client = TestClient(app)
    client.post(
        "/api/dataset-editor/batch",
        json={
            "root": str(tmp_path),
            "images": ["alpha.png", "beta.png"],
            "append": ["masterpiece"],
            "remove": ["solo"],
            "replace": [],
            "sort": False,
        },
    )

    undo = client.post("/api/dataset-editor/undo", json={"root": str(tmp_path)})

    assert undo.status_code == 200
    assert undo.json()["data"]["changed"] == 2
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "solo, 1girl"
    assert (tmp_path / "beta.txt").read_text(encoding="utf-8") == "solo, blue eyes"


def test_dataset_editor_rejects_path_escape(tmp_path):
    make_image(tmp_path / "alpha.png")
    outside = tmp_path.parent / "outside.png"
    make_image(outside)

    client = TestClient(app)
    response = client.post(
        "/api/dataset-editor/caption",
        json={"root": str(tmp_path), "image": "../outside.png", "caption": "bad"},
    )

    assert response.status_code == 400
    assert "outside dataset" in response.json()["detail"]


def test_legacy_gradio_tageditor_starts_by_default_for_existing_users():
    gui = (ROOT / "gui.py").read_text(encoding="utf-8")

    assert "--enable-legacy-tageditor" in gui
    assert "legacy_tageditor_enabled = not args.disable_tageditor" in gui
    assert "run_tag_editor(tageditor_port)" in gui


def test_dataset_editor_vue_source_exposes_enhanced_workflow():
    source = (ROOT / "frontend/src/pages/DatasetEditorPage.vue").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api/dataset.ts").read_text(encoding="utf-8")

    for marker in ("selectedPaths", "togglePageSelection", "quickTags", "pageSize", "replaceFrom", "sessionHistory"):
        assert marker in source
    for endpoint in ("/batch", "/undo", "/redo", "/history"):
        assert endpoint in api
