# AutoByteus MCPs

Collection of Model Context Protocol (MCP) tools maintained in one workspace.

## Projects

| Project | Description | Origin |
| --- | --- | --- |
| `pdf_mcp` | MCP server for reading PDFs: metadata, text extraction, and page rendering. | AutoByteus (internal) |
| `video-audio-mcp` | Video/audio editing MCP server derived from Misbah Sy's project. | https://github.com/misbahsy/video-audio-mcp |
| `moss-ttsd-mcp` | MCP server for bilingual dialogue TTS using fnlp/MOSS-TTSD-v0.5. | https://huggingface.co/fnlp/MOSS-TTSD-v0.5 |

## Contributing

Each MCP project is maintained in its own folder. When adding a new project:

1. Copy the project into its own subdirectory at the repository root.
2. Document the original source in this README table.
3. Keep build artifacts, virtual environments, and editor state out of version control (see `.gitignore`).
4. Add and run tests for the new project when applicable.
