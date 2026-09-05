import csv
import os
import re
import subprocess
import sys
from functools import partial

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import Qgis, QgsMapLayerType, QgsProject


class LayerFileListPlugin:
    COLUMNS = (
        ("index", "#"),
        ("group_name", "Group name"),
        ("layer_name", "Layer name"),
        ("activate_button", "Activate"),
        ("visibility_button", "Visible"),
        ("show_groups_button", "Show groups"),
        ("remove_button", "Remove"),
        ("open_button", "Open"),
        ("file_location", "File location"),
        ("layer_type", "Type"),
        ("crs", "CRS"),
        ("saved", "Saved"),
        ("in_memory", "In memory"),
        ("provider", "Provider"),
    )

    FILTERABLE_COLUMN_KEYS = (
        "index",
        "group_name",
        "layer_name",
        "layer_type",
        "provider",
        "file_location",
        "in_memory",
        "saved",
        "crs",
    )

    EXPORT_COLUMN_KEYS = (
        "index",
        "group_name",
        "layer_name",
        "file_location",
        "layer_type",
        "crs",
        "saved",
        "in_memory",
        "provider",
    )

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock_widget = None
        self.table = None
        self.filter_column_combo = None
        self.filter_line_edit = None
        self._rows = []
        self._column_index = self._build_column_index()

    def _build_column_index(self):
        return {key: idx for idx, (key, _label) in enumerate(self.COLUMNS)}

    def _col(self, key):
        return self._column_index[key]

    def _label_for_key(self, key):
        for col_key, label in self.COLUMNS:
            if col_key == key:
                return label
        return key

    def initGui(self):
        self.action = QAction("Layer File List...", self.iface.mainWindow())
        self.action.setObjectName("LayerFileListAction")
        self.action.triggered.connect(self.open_dock)
        self.iface.pluginMenu().addAction(self.action)

    def unload(self):
        if self.action is not None:
            try:
                self.action.triggered.disconnect(self.open_dock)
            except TypeError:
                pass
            self.iface.pluginMenu().removeAction(self.action)
            self.action.deleteLater()
            self.action = None

        if self.dock_widget is not None:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None
            self.table = None

    def open_dock(self):
        if self.dock_widget is None:
            self._create_dock_widget()

        self.refresh_table()
        if self.dock_widget is not None:
            self.dock_widget.show()
            self.dock_widget.raise_()

    def _create_dock_widget(self):
        self.dock_widget = QDockWidget("Layer File List", self.iface.mainWindow())
        self.dock_widget.setObjectName("LayerFileListDock")

        container = QWidget(self.dock_widget)
        root_layout = QVBoxLayout(container)

        controls_layout = QHBoxLayout()
        refresh_button = QPushButton("Refresh", container)
        export_button = QPushButton("Export CSV...", container)
        controls_layout.addWidget(refresh_button)
        controls_layout.addWidget(export_button)
        controls_layout.addStretch(1)

        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter", container)
        self.filter_column_combo = QComboBox(container)
        self.filter_line_edit = QLineEdit(container)
        self.filter_line_edit.setPlaceholderText("Type to filter rows...")
        clear_filter_button = QPushButton("Clear", container)

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_column_combo)
        filter_layout.addWidget(self.filter_line_edit, 1)
        filter_layout.addWidget(clear_filter_button)

        self.table = QTableWidget(container)
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _key, label in self.COLUMNS])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setStyleSheet(
            "QTableWidget::item { padding: 1px 4px; }"
            "QHeaderView::section { padding: 2px 4px; }"
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setMinimumSectionSize(24)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        for col in range(len(self.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(self._col("index"), 70)
        self.table.setColumnWidth(self._col("group_name"), 180)
        self.table.setColumnWidth(self._col("layer_name"), 220)
        self.table.setColumnWidth(self._col("layer_type"), 120)
        self.table.setColumnWidth(self._col("provider"), 100)
        self.table.setColumnWidth(self._col("file_location"), 320)
        self.table.setColumnWidth(self._col("open_button"), 120)
        self.table.setColumnWidth(self._col("activate_button"), 110)
        self.table.setColumnWidth(self._col("visibility_button"), 90)
        self.table.setColumnWidth(self._col("show_groups_button"), 120)
        self.table.setColumnWidth(self._col("remove_button"), 95)
        self.table.setColumnWidth(self._col("in_memory"), 90)
        self.table.setColumnWidth(self._col("saved"), 80)
        self.table.setColumnWidth(self._col("crs"), 100)

        root_layout.addLayout(controls_layout)
        root_layout.addLayout(filter_layout)
        root_layout.addWidget(self.table)
        self.dock_widget.setWidget(container)

        self.filter_column_combo.addItem("All columns", -1)
        for key in self.FILTERABLE_COLUMN_KEYS:
            self.filter_column_combo.addItem(self._label_for_key(key), self._col(key))

        refresh_button.clicked.connect(self.refresh_table)
        export_button.clicked.connect(self.export_csv)
        self.filter_column_combo.currentIndexChanged.connect(self.apply_filter)
        self.filter_line_edit.textChanged.connect(self.apply_filter)
        clear_filter_button.clicked.connect(self._clear_filter)

        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)

    def refresh_table(self):
        if self.table is None:
            return

        view_state = self._capture_view_state()

        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        sort_col = max(sort_col, 0)

        self.table.setSortingEnabled(False)
        self._rows = self._collect_rows()
        self.table.clearContents()
        self.table.setRowCount(len(self._rows))

        for row_index, row in enumerate(self._rows):
            self._set_item(
                row_index,
                self._col("index"),
                row["index"],
                sort_value=row["index"],
            )
            self._set_item(row_index, self._col("group_name"), row["group_name"])
            self._set_item(row_index, self._col("layer_name"), row["layer_name"])
            self._set_item(row_index, self._col("layer_type"), row["layer_type"])
            self._set_item(row_index, self._col("provider"), row["provider"])
            self._set_item(
                row_index,
                self._col("file_location"),
                row["file_location"],
            )
            self._set_item(row_index, self._col("in_memory"), row["in_memory"])
            self._set_item(row_index, self._col("saved"), row["saved"])
            self._set_item(row_index, self._col("crs"), row["crs"])

            open_button = QPushButton("Open")
            has_location = bool(row["file_location"])
            open_button.setEnabled(has_location)
            open_button.clicked.connect(
                partial(self.open_in_explorer, row["file_location"])
            )
            self.table.setCellWidget(row_index, self._col("open_button"), open_button)

            activate_button = QPushButton("Activate")
            activate_button.setEnabled(bool(row["layer_id"]))
            activate_button.clicked.connect(
                partial(self.activate_layer, row["layer_id"])
            )
            self.table.setCellWidget(
                row_index,
                self._col("activate_button"),
                activate_button,
            )

            visible_button = QPushButton(row["visibility_button_text"])
            visible_button.setEnabled(bool(row["layer_id"]))
            visible_button.clicked.connect(
                partial(self.toggle_layer_visibility, row["layer_id"])
            )
            self.table.setCellWidget(
                row_index,
                self._col("visibility_button"),
                visible_button,
            )

            show_groups_button = QPushButton("Show")
            show_groups_button.setEnabled(
                bool(row["group_name"] and row["group_name"] != "(root)")
            )
            show_groups_button.clicked.connect(
                partial(self.set_parent_groups_visible, row["layer_id"])
            )
            self.table.setCellWidget(
                row_index,
                self._col("show_groups_button"),
                show_groups_button,
            )

            remove_button = QPushButton("Remove")
            remove_button.setEnabled(bool(row["layer_id"]))
            remove_button.clicked.connect(partial(self.remove_layer, row["layer_id"]))
            self.table.setCellWidget(
                row_index,
                self._col("remove_button"),
                remove_button,
            )

        for row_index in range(self.table.rowCount()):
            self.table.setRowHeight(row_index, 24)

        self._resize_columns_for_view()
        self.table.setSortingEnabled(True)
        self.table.sortItems(sort_col, sort_order)
        self.apply_filter()
        self._restore_view_state(view_state)

    def _capture_view_state(self):
        if self.table is None:
            return None

        vertical = self.table.verticalScrollBar().value()
        horizontal = self.table.horizontalScrollBar().value()

        current_row = self.table.currentRow()
        current_col = self.table.currentColumn()
        selected_layer_id = None
        if 0 <= current_row < len(self._rows):
            selected_layer_id = self._rows[current_row].get("layer_id")

        return {
            "vertical": vertical,
            "horizontal": horizontal,
            "current_row": current_row,
            "current_col": current_col,
            "selected_layer_id": selected_layer_id,
        }

    def _restore_view_state(self, view_state):
        if self.table is None or not view_state:
            return

        target_row = view_state.get("current_row", -1)
        layer_id = view_state.get("selected_layer_id")
        if layer_id:
            for idx, row in enumerate(self._rows):
                if row.get("layer_id") == layer_id:
                    target_row = idx
                    break

        current_col = view_state.get("current_col", 0)
        if (
            0 <= target_row < self.table.rowCount()
            and 0 <= current_col < self.table.columnCount()
        ):
            self.table.setCurrentCell(target_row, current_col)

        self.table.verticalScrollBar().setValue(int(view_state.get("vertical", 0)))
        self.table.horizontalScrollBar().setValue(int(view_state.get("horizontal", 0)))

    def _resize_columns_for_view(self):
        if self.table is None:
            return

        file_location_col = self._col("file_location")
        for col in range(self.table.columnCount()):
            if col == file_location_col:
                continue

            self.table.resizeColumnToContents(col)
            fitted_width = self.table.columnWidth(col)
            self.table.setColumnWidth(col, min(max(fitted_width, 56), 260))

        self.table.setColumnWidth(file_location_col, 320)

    def activate_layer(self, layer_id):
        if not layer_id:
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            self._show_message("Layer is no longer available.", Qgis.Warning, 5)
            return

        self.iface.setActiveLayer(layer)

        layer_tree_view = getattr(self.iface, "layerTreeView", None)
        if callable(layer_tree_view):
            tree_view = layer_tree_view()
            set_current_layer = getattr(tree_view, "setCurrentLayer", None)
            if callable(set_current_layer):
                set_current_layer(layer)

    def toggle_layer_visibility(self, layer_id):
        node = self._layer_tree_node(layer_id)
        if node is None:
            self._show_message("Layer is no longer available.", Qgis.Warning, 5)
            return

        node.setItemVisibilityChecked(not node.itemVisibilityChecked())
        self.refresh_table()

    def set_parent_groups_visible(self, layer_id):
        node = self._layer_tree_node(layer_id)
        if node is None:
            self._show_message("Layer is no longer available.", Qgis.Warning, 5)
            return

        parent = node.parent()
        while parent is not None:
            if hasattr(parent, "setItemVisibilityChecked"):
                parent.setItemVisibilityChecked(True)
            parent = parent.parent()

        self.refresh_table()

    def remove_layer(self, layer_id):
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            self._show_message("Layer is no longer available.", Qgis.Warning, 5)
            self.refresh_table()
            return

        layer_tree_view = getattr(self.iface, "layerTreeView", None)
        if callable(layer_tree_view):
            tree_view = layer_tree_view()
            set_current_layer = getattr(tree_view, "setCurrentLayer", None)
            if callable(set_current_layer):
                set_current_layer(layer)

            default_actions_factory = getattr(tree_view, "defaultActions", None)
            if callable(default_actions_factory):
                default_actions = default_actions_factory()
                remove_action_factory = getattr(
                    default_actions,
                    "actionRemoveGroupOrLayer",
                    None,
                )
                if callable(remove_action_factory):
                    remove_action = remove_action_factory()
                    trigger_action = getattr(remove_action, "trigger", None)
                    if callable(trigger_action):
                        trigger_action()
                        self.refresh_table()
                        return

        # Fallback when layer tree default actions are unavailable.
        QgsProject.instance().removeMapLayer(layer_id)
        self.refresh_table()

    def _layer_tree_node(self, layer_id):
        if not layer_id:
            return None
        return QgsProject.instance().layerTreeRoot().findLayer(layer_id)

    def export_csv(self):
        if not self._rows:
            self._show_message("No layers available to export.", Qgis.Warning, 5)
            return

        default_path = self._default_export_path()
        selected_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export layer file list",
            default_path,
            "CSV (*.csv)",
        )
        if not selected_path:
            return

        if not selected_path.lower().endswith(".csv"):
            selected_path = f"{selected_path}.csv"

        try:
            with open(selected_path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [self._label_for_key(key) for key in self.EXPORT_COLUMN_KEYS]
                )
                for row in self._rows:
                    csv_row = [row.get(key, "") for key in self.EXPORT_COLUMN_KEYS]
                    writer.writerow(csv_row)
        except OSError as exc:
            self._show_message(f"Failed to write CSV: {exc}", Qgis.Critical, 8)
            return

        self._show_message(
            f"Exported {len(self._rows)} layer row(s) to {selected_path}",
            Qgis.Success,
            6,
        )

    def open_in_explorer(self, location):
        if not location:
            return

        path = location
        if not os.path.exists(path):
            self._show_message(
                "Location does not exist on disk for this layer.",
                Qgis.Warning,
                5,
            )
            return

        try:
            if sys.platform.startswith("win") and os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                target = os.path.dirname(path) if os.path.isfile(path) else path
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(target)):
                    self._show_message(
                        "Failed to open the layer location.",
                        Qgis.Warning,
                        6,
                    )
        except OSError as exc:
            self._show_message(f"Failed to open location: {exc}", Qgis.Critical, 8)

    def _collect_rows(self):
        root = QgsProject.instance().layerTreeRoot()
        rows = []

        def walk(node, parents):
            from qgis.core import QgsLayerTreeGroup, QgsLayerTreeLayer

            if isinstance(node, QgsLayerTreeGroup):
                for child in node.children():
                    next_parents = parents + [node.name()] if node.name() else parents
                    walk(child, next_parents)
                return

            if isinstance(node, QgsLayerTreeLayer):
                layer = node.layer()
                if layer is None:
                    return

                provider = layer.providerType() or "-"
                file_location = self._layer_file_location(layer)
                rows.append(
                    {
                        "index": len(rows) + 1,
                        "group_name": self._group_name(parents),
                        "layer_name": layer.name(),
                        "layer_id": layer.id(),
                        "layer_type": self._layer_type_label(layer),
                        "provider": provider,
                        "file_location": file_location,
                        "open_hint": "Open location" if file_location else "",
                        "activate_hint": "Activate",
                        "visibility_button_text": "Hide"
                        if node.itemVisibilityChecked()
                        else "Show",
                        "show_groups_hint": "Show parent groups",
                        "remove_hint": "Remove layer",
                        "in_memory": "Yes" if self._is_memory_layer(layer) else "No",
                        "saved": "Yes" if self._is_saved_layer(layer) else "No",
                        "crs": layer.crs().authid() if layer.crs().isValid() else "-",
                    }
                )

        for child in root.children():
            walk(child, [])

        return rows

    def _default_export_path(self):
        project = QgsProject.instance()
        project_file = project.fileName()

        if project_file:
            folder = os.path.dirname(project_file)
            base_name = os.path.splitext(os.path.basename(project_file))[0]
            return os.path.join(folder, f"{base_name}_filelist.csv")

        fallback_folder = project.homePath() or os.path.expanduser("~")
        return os.path.join(fallback_folder, "unsaved_project_filelist.csv")

    def _group_name(self, parent_groups):
        names = [name for name in parent_groups if name]
        if not names:
            return "(root)"
        return " / ".join(names)

    def _layer_type_label(self, layer):
        layer_type = layer.type()
        provider = (layer.providerType() or "").lower()
        map_layer_type = QgsMapLayerType

        if provider in {"wms", "wfs", "xyz", "arcgismapserver", "arcgisfeatureserver"}:
            return provider.upper()

        if layer_type == map_layer_type.VectorLayer:
            return "Vector"
        if layer_type == map_layer_type.RasterLayer:
            return "Raster"
        if layer_type == map_layer_type.MeshLayer:
            return "Mesh"
        if hasattr(map_layer_type, "VectorTileLayer") and layer_type == getattr(
            map_layer_type, "VectorTileLayer"
        ):
            return "Vector tile"
        if hasattr(map_layer_type, "AnnotationLayer") and layer_type == getattr(
            map_layer_type, "AnnotationLayer"
        ):
            return "Annotation"
        if hasattr(map_layer_type, "PointCloudLayer") and layer_type == getattr(
            map_layer_type, "PointCloudLayer"
        ):
            return "Point cloud"
        if layer_type == map_layer_type.PluginLayer:
            return "Plugin"
        if hasattr(map_layer_type, "GroupLayer") and layer_type == getattr(
            map_layer_type, "GroupLayer"
        ):
            return "Group"

        return "Other"

    def _is_memory_layer(self, layer):
        source = (layer.source() or "").lower()
        provider = (layer.providerType() or "").lower()
        return provider == "memory" or source.startswith("memory:")

    def _is_saved_layer(self, layer):
        if self._is_memory_layer(layer):
            return False

        location = self._layer_file_location(layer)
        if location:
            return os.path.exists(location)

        return bool(layer.source())

    def _layer_file_location(self, layer):
        source = layer.source() or ""
        if not source:
            return ""

        archive_location = self._extract_archive_container_path(source)
        if archive_location:
            return archive_location

        if source.startswith("file://"):
            from qgis.PyQt.QtCore import QUrl

            local_path = QUrl(source).toLocalFile()
            if local_path and os.path.exists(local_path):
                return os.path.normpath(local_path)
            return ""

        before_pipe = source.split("|", 1)[0]
        if os.path.exists(before_pipe):
            return os.path.normpath(before_pipe)

        match = re.search(r"([A-Za-z]:[\\/][^|]+)", source)
        if match:
            path = match.group(1).strip().strip("'\"")
            archive_location = self._extract_archive_container_path(path)
            if archive_location:
                return archive_location

            cleaned_path = path.split("&", 1)[0].strip().strip("'\"")
            if os.path.exists(cleaned_path):
                return os.path.normpath(cleaned_path)
            return ""

        return ""

    def _extract_archive_container_path(self, source):
        # Handle GDAL virtual archive paths such as /vsizip/C:/data/archive.zip/layer.shp.
        lowered = source.lower()
        vsi_prefixes = ["/vsizip/", "\\vsizip\\"]
        for prefix in vsi_prefixes:
            idx = lowered.find(prefix)
            if idx >= 0:
                candidate = source[idx + len(prefix) :]
                if re.match(r"^/[A-Za-z]:[\\/]", candidate):
                    # Convert /C:/... (common in GDAL virtual paths) to C:/...
                    candidate = candidate[1:]
                elif not re.match(r"^([A-Za-z]:[\\/]|[\\/]{2}|[\\/])", candidate):
                    candidate = candidate.lstrip("/").lstrip("\\")
                archive_path = self._extract_archive_path_with_extension(candidate)
                if archive_path and os.path.exists(archive_path):
                    return os.path.normpath(archive_path)

        # Handle URI/query forms like zip://C:/data/archive.zip!folder/layer.shp.
        stripped = source.split("|", 1)[0].strip().strip("'\"")
        if stripped.lower().startswith("zip://"):
            stripped = stripped[6:]

        if stripped.lower().startswith("file://"):
            from qgis.PyQt.QtCore import QUrl

            stripped = QUrl(stripped).toLocalFile() or stripped

        stripped = stripped.replace("!", "/")
        archive_path = self._extract_archive_path_with_extension(stripped)
        if archive_path and os.path.exists(archive_path):
            return os.path.normpath(archive_path)

        return ""

    def _extract_archive_path_with_extension(self, value):
        # Capture the container path up to a known archive extension.
        cleaned = (value or "").split("|", 1)[0].split("?", 1)[0].strip().strip("'\"")
        lowered = cleaned.lower()
        extensions = (".tar.gz", ".zip", ".7z", ".tgz", ".tar")

        for ext in extensions:
            idx = lowered.find(ext)
            if idx < 0:
                continue

            end = idx + len(ext)
            path = cleaned[:end].replace("\\", "/")
            if re.match(r"^/[A-Za-z]:/", path):
                path = path[1:]

            return os.path.normpath(path.replace("/", os.sep))

        return ""

    def apply_filter(self):
        if self.table is None:
            return

        text = ""
        if self.filter_line_edit is not None:
            text = self.filter_line_edit.text().strip().lower()

        selected_col = -1
        if self.filter_column_combo is not None:
            selected_col = int(self.filter_column_combo.currentData())

        searchable_cols = [self._col(key) for key in self.FILTERABLE_COLUMN_KEYS]

        for row_index in range(self.table.rowCount()):
            if not text:
                self.table.setRowHidden(row_index, False)
                continue

            if selected_col == -1:
                row_values = []
                for col in searchable_cols:
                    item = self.table.item(row_index, col)
                    row_values.append(item.text().lower() if item is not None else "")
                matched = any(text in value for value in row_values)
            else:
                item = self.table.item(row_index, selected_col)
                matched = item is not None and text in item.text().lower()

            self.table.setRowHidden(row_index, not matched)

    def _clear_filter(self):
        if self.filter_line_edit is not None:
            self.filter_line_edit.clear()
        if self.filter_column_combo is not None:
            self.filter_column_combo.setCurrentIndex(0)
        self.apply_filter()

    def _set_item(self, row_index, column_index, value, sort_value=None):
        item = QTableWidgetItem()
        if isinstance(value, (int, float)):
            item.setData(Qt.DisplayRole, value)
        else:
            item.setText(str(value))

        if column_index == self._col("file_location") and value:
            item.setToolTip(str(value))

        if sort_value is not None:
            item.setData(Qt.EditRole, sort_value)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if self.table is not None:
            self.table.setItem(row_index, column_index, item)

    def _show_message(self, message, level, duration):
        self.iface.messageBar().pushMessage("Layer File List", message, level, duration)
