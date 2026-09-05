# Changelog

## 0.1.4 - 2026-09-05

- Updated release workflow linting to stage plugin code under `layer_file_list` and avoid false Ruff N999 failures from hyphenated repository folder names.

## 0.1.3 - 2026-09-05

- Fixed qgis-plugin-ci changelog path resolution during local Docker pre-release validation.
- Fixed GitHub Actions validation config so changelog detection uses the repository code path.

## 0.1.2 - 2026-09-05

- Added Qt6-compatible enum usage to address plugin checker compatibility findings.
- Updated release packaging process to produce QGIS repository compliant ZIP archives.

## 0.1.1 - 2026-09-05

- Improved cross-platform archive container path detection for non-Windows path forms.
- Aligned README terminology with current cross-platform open-location behaviour.

## 0.1.0 - 2026-09-04

- Initial public release.
- Shows loaded project layers in a non-blocking dock table.
- Supports filtering, sorting, and CSV export.
- Adds quick actions to activate, show/hide, remove, and inspect layer locations.
- Uses cross-platform location opening behaviour for Windows, macOS, and Linux.
