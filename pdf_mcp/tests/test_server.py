from __future__ import annotations

import anyio
import pytest
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from pdf_mcp.server import create_server


def _create_pdf(path, texts):
    writer = PdfWriter()

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)

    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        resources = DictionaryObject()
        resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_ref})
        page[NameObject("/Resources")] = resources

        content_stream = DecodedStreamObject()
        content_stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("utf-8"))
        stream_ref = writer._add_object(content_stream)
        page[NameObject("/Contents")] = stream_ref

    with path.open("wb") as handle:
        writer.write(handle)


async def _run_with_session(server, client_callable):
    client_to_server_send, server_read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    server_to_client_send, client_read_stream = anyio.create_memory_object_stream[SessionMessage](0)

    async def server_task():
        await server._mcp_server.run(  # type: ignore[attr-defined]
            server_read_stream,
            server_to_client_send,
            server._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            raise_exceptions=True,
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        async with ClientSession(client_read_stream, client_to_server_send) as session:
            await session.initialize()
            await client_callable(session)
        await client_to_server_send.aclose()
        await server_to_client_send.aclose()
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_read_pdf_selected_pages(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf(pdf_path, ["First page", "Second page", "Third page"])

    server = create_server()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "read_pdf_pages",
            {"file_path": str(pdf_path), "pages": [2]},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["total_pages"] == 3
        assert structured["pages"][0]["page"] == 2
        assert "Second page" in structured["pages"][0]["text"]

        range_result = await session.call_tool(
            "read_pdf_pages",
            {"file_path": str(pdf_path), "start_page": 1, "end_page": 2},
        )
        assert not range_result.isError
        assert range_result.structuredContent is not None
        assert [item["page"] for item in range_result.structuredContent["pages"]] == [1, 2]

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_pdf_metadata(tmp_path):
    pdf_path = tmp_path / "meta.pdf"
    _create_pdf(pdf_path, ["Only page"])

    server = create_server()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "pdf_metadata",
            {"file_path": str(pdf_path)},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["total_pages"] == 1
        assert structured["path"].endswith("meta.pdf")

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_merge_pdf_files(tmp_path):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    output_pdf = tmp_path / "merged.pdf"
    _create_pdf(first_pdf, ["First"])
    _create_pdf(second_pdf, ["Second", "Third"])

    server = create_server()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "merge_pdf_files",
            {
                "file_paths": [str(first_pdf), str(second_pdf)],
                "output_path": str(output_pdf),
            },
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["output_path"] == str(output_pdf)
        assert structured["total_pages"] == 3
        assert structured["sources"] == [
            {"path": str(first_pdf), "total_pages": 1},
            {"path": str(second_pdf), "total_pages": 2},
        ]
        assert output_pdf.is_file()

        reader = PdfReader(str(output_pdf))
        try:
            assert len(reader.pages) == 3
        finally:
            reader.close()

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_render_pdf_pages(tmp_path):
    pdf_path = tmp_path / "render.pdf"
    _create_pdf(pdf_path, ["First", "Second"])

    server = create_server()

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "render_pdf_pages",
            {
                "file_path": str(pdf_path),
                "pages": [2],
            },
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["format"] == "png"
        assert Path(structured["output_dir"]).resolve() == pdf_path.parent.resolve()
        images = structured["pages"]
        assert len(images) == 1
        image_path = Path(images[0]["image_path"])
        assert image_path.is_file()
        assert image_path.parent.resolve() == pdf_path.parent.resolve()
        assert image_path.suffix == ".png"
        assert image_path.stat().st_size > 0

    await _run_with_session(server, run_client)
