import json
import subprocess
import sys
from pathlib import Path

from schemaflight import SnapshotCatalog
from schemaflight.cli import main


FIXTURES = Path(__file__).parents[1] / "examples" / "ecommerce"


def test_cli_compiles_a_request_into_a_reproducible_artifact_directory(tmp_path: Path) -> None:
    output = tmp_path / "migration-bundle"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "schemaflight",
            "compile",
            "--catalog",
            str(FIXTURES / "catalog.json"),
            "--request",
            str(FIXTURES / "rename-email.json"),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary == {
        "assets_impacted": 2,
        "direct_rename_allowed": False,
        "output": str(output.resolve()),
        "risk": "high",
    }
    assert (output / "01_expand.sql").is_file()
    assert (output / "query_patches" / "retention-export.sql").is_file()
    manifest = json.loads((output / "impact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence"]["lineage_hops"] == 2


def test_live_cli_can_explicitly_publish_the_generated_decision(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    class RecordingCatalog(SnapshotCatalog):
        published: list[dict[str, str]] = []

        def publish_decision(self, **payload: str) -> str:
            self.published.append(payload)
            return "urn:li:document:schemaflight-demo"

    catalog = RecordingCatalog.from_file(FIXTURES / "catalog.json")
    monkeypatch.setattr(
        "schemaflight.cli.AgentContextCatalog.connect",
        lambda **kwargs: catalog,
    )
    output = tmp_path / "live-bundle"

    return_code = main(
        [
            "compile",
            "--datahub-server",
            "http://localhost:8080",
            "--request",
            str(FIXTURES / "rename-email.json"),
            "--output",
            str(output),
            "--write-back",
        ]
    )

    assert return_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["decision_document_urn"] == "urn:li:document:schemaflight-demo"
    assert catalog.published[0]["content"].startswith("# Migration decision")


def test_seed_datahub_command_reports_the_upserted_demo_graph(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "schemaflight.cli.seed_demo_catalog",
        lambda **kwargs: {
            "datasets_upserted": 3,
            "dataset_urns": ["source", "model", "consumer"],
        },
    )

    return_code = main(
        [
            "seed-datahub",
            "--datahub-server",
            "http://localhost:8080",
        ]
    )

    assert return_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "dataset_urns": ["source", "model", "consumer"],
        "datasets_upserted": 3,
    }
