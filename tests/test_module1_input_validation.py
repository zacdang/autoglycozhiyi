from types import SimpleNamespace

from src.pipeline.load_documents import validate_input_metadata


def test_validate_input_metadata_accepts_existing_main_and_si_pdfs(tmp_path):
    main_pdf = tmp_path / "main.pdf"
    si_pdf = tmp_path / "supporting_information.pdf"
    main_pdf.write_bytes(b"%PDF-1.4\nmain")
    si_pdf.write_bytes(b"%PDF-1.4\nsi")

    paper = SimpleNamespace(
        paper_id="TEST_001",
        pdf_path=str(main_pdf),
        si_path=str(si_pdf),
    )

    report = validate_input_metadata(paper, check_files=True)

    assert report["valid"] is True
    assert report["errors"] == []
    assert report["checked_paths"]["pdf_path"] == str(main_pdf)
    assert report["checked_paths"]["si_path"] == str(si_pdf)


def test_validate_input_metadata_reports_missing_main_pdf(tmp_path):
    missing_pdf = tmp_path / "missing.pdf"
    paper = SimpleNamespace(
        paper_id="TEST_002",
        pdf_path=str(missing_pdf),
        si_path=None,
    )

    report = validate_input_metadata(paper, check_files=True)

    assert report["valid"] is False
    assert any("main PDF not found" in error for error in report["errors"])
    assert any("si_path" in warning for warning in report["warnings"])


def test_validate_input_metadata_can_require_si_path(tmp_path):
    main_pdf = tmp_path / "main.pdf"
    main_pdf.write_bytes(b"%PDF-1.4\nmain")

    paper = SimpleNamespace(
        paper_id="TEST_003",
        pdf_path=str(main_pdf),
        si_path=None,
    )

    report = validate_input_metadata(paper, check_files=True, require_si=True)

    assert report["valid"] is False
    assert any("si_path" in error for error in report["errors"])
